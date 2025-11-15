import yfinance as yf
import requests
import re
import sys
import os

# --- Import ML/Vector libraries ---
try:
    from sentence_transformers import SentenceTransformer
    import faiss
    import numpy as np
    import nltk
    from nltk.tokenize import sent_tokenize
except ImportError:
    print("Error: One or more required libraries (sentence_transformers, faiss-cpu, numpy, nltk) are not installed.")
    print("Please run: pip install sentence-transformers faiss-cpu numpy nltk")
    sys.exit(1)

# --- Download NLTK data (one-time) ---
# --- MODIFICATION ---
# We've moved the download logic into a function that api_server.py can call
# at startup.
def download_nltk_data():
    """
    Downloads the NLTK 'punkt' tokenizer if not found.
    """
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        print("NLTK 'punkt' tokenizer not found. Downloading...")
        nltk.download('punkt', quiet=True)
    
    # Also download the other resource you needed
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("NLTK 'punkt_tab' resource not found. Downloading...")
        nltk.download('punkt_tab', quiet=True)
# --- END MODIFICATION ---

# --- Global var to hold the embedding model ---
embedding_model = None

def load_embedding_model():
    """Loads the sentence transformer model into the global variable."""
    global embedding_model
    if embedding_model is None:
        print("Loading embedding model (this may take a moment)...")
        try:
            # Using a small, fast, and effective model
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("Embedding model loaded successfully.")
        except Exception as e:
            print(f"Error loading embedding model: {e}")
            print("Please ensure you have an internet connection, or try a different model.")
            sys.exit(1)

# --- 1. Data Fetching ---

def get_fundamentals(ticker_symbol):
    """
    Fetches fundamental stock data using yfinance.
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        # --- Grab more financial indicators ---
        fundamentals = {
            "Market Cap": info.get('marketCap', 'N/A'),
            "P/E Ratio (Trailing)": info.get('trailingPE', 'N/A'),
            "P/E Ratio (Forward)": info.get('forwardPE', 'N/A'),
            "Price-to-Book (P/B)": info.get('priceToBook', 'N/A'),
            "PEG Ratio": info.get('pegRatio', 'N/A'),
            "Dividend Yield": info.get('dividendYield', 'N/A'),
            "Earnings per Share (EPS)": info.get('trailingEps', 'N/A'),
            "Return on Equity (ROE)": info.get('returnOnEquity', 'N/A'),
            "Debt-to-Equity": info.get('debtToEquity', 'N/A'),
            "52 Week High": info.get('fiftyTwoWeekHigh', 'N/A'),
            "52 Week Low": info.get('fiftyTwoWeekLow', 'N/A'),
        }
        
        # Get the long business summary
        summary = info.get('longBusinessSummary', 'No summary available.')
        
        return fundamentals, summary
    except Exception as e:
        print(f"Error fetching fundamentals for {ticker_symbol} with yfinance: {e}")
        return None, None

def get_news(ticker_symbol, api_key, num_articles=20):
    """
    Fetches recent news articles from NewsAPI.org.
    """
    base_url = "https://newsapi.org/v2/everything"
    params = {
        'q': ticker_symbol,
        'apiKey': api_key,
        'language': 'en',
        'sortBy': 'publishedAt',
        'pageSize': num_articles
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
        data = response.json()
        
        if data.get('status') == 'ok':
            articles = data.get('articles', [])
            if not articles:
                print(f"No articles found for {ticker_symbol}.")
            return articles
        else:
            print(f"Error from NewsAPI: {data.get('message')}")
            return []
            
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error fetching news for {ticker_symbol}: {http_err}")
        if http_err.response.status_code == 401:
            print("Error 401: Unauthorized. Check your NewsAPI key.")
        elif http_err.response.status_code == 429:
            print("Error 429: Too Many Requests. You are rate-limited.")
    except Exception as e:
        print(f"Error fetching news for {ticker_symbol}: {e}")
        
    return []

# --- 2. RAG Processing ---

def process_and_embed(news_articles, summary_text, ticker=""):
    """
    Processes text into chunks, creates embeddings, and builds a FAISS index.
    """
    global embedding_model
    if embedding_model is None:
        load_embedding_model()
        
    text_chunks = []
    metadata = []
    
    # --- 1. Process the summary text ---
    if summary_text and summary_text != 'No summary available.':
        summary_sentences = sent_tokenize(summary_text)
        # Create chunks of 3 sentences
        for i in range(0, len(summary_sentences), 3):
            chunk = " ".join(summary_sentences[i:i+3])
            text_chunks.append(chunk)
            metadata.append({
                'source': f"{ticker} Business Summary",
                'date': 'N/A',
                'url': '#'  # --- FIX: Added a placeholder URL ---
            })

    # --- 2. Process news articles ---
    for article in news_articles:
        content = article.get('description', '') or article.get('content', '')
        if not content:
            continue
        
        # Clean up the text a bit
        content = re.sub(r'\[\+\d+ chars\]$', '', content)  # Remove "[+1234 chars]"
        content = re.sub(r'\s+', ' ', content).strip()
        
        if not content:
            continue
            
        sentences = sent_tokenize(content)
        # Create chunks of 3-5 sentences
        for i in range(0, len(sentences), 4):
            chunk = " ".join(sentences[i:i+4])
            text_chunks.append(chunk)
            metadata.append({
                'source': article.get('source', {}).get('name', 'Unknown'),
                'date': article.get('publishedAt', 'Unknown')[:10],
                'url': article.get('url', '#')
            })

    # --- 3. Create Embeddings & FAISS Index ---
    if not text_chunks:
        print("No text chunks to embed.")
        return None, [], []

    try:
        print(f"Created {len(text_chunks)} text chunks.")
        
        embeddings = embedding_model.encode(text_chunks, show_progress_bar=True)
        print(f"Created {len(embeddings)} embeddings.")
        
        # Ensure embeddings are float32
        if embeddings.dtype != 'float32':
            embeddings = embeddings.astype('float32')
            
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)
        
        print("FAISS index built successfully.")
        return index, text_chunks, metadata
        
    except Exception as e:
        print(f"Error creating FAISS index: {e}")
        import traceback
        traceback.print_exc()
        return None, [], []

# --- 3. Self-Test Block ---
if __name__ == "__main__":
    """
    This block runs ONLY when you execute data_fetcher.py directly.
    It's for testing this file's functions.
    """
    
    # --- !! IMPORTANT !! ---
    # PASTE YOUR NewsAPI.org KEY HERE FOR TESTING:
    YOUR_API_KEY = "" # e.g., "f0a123b456c789d0e12f3456a7b89c0d"
    
    if not YOUR_API_KEY:
        print("Error: YOUR_API_KEY is not set in the test block of data_fetcher.py.")
    else:
        TICKER = "MSFT"  # Test with a ticker
        
        print(f"--- Testing Phase 2 (Data Fetcher) for {TICKER} ---")
        
        # 1. Test yfinance
        print(f"Fetching fundamentals for {TICKER}...")
        fundamentals, summary = get_fundamentals(TICKER)
        if fundamentals:
            print("--- Fundamentals ---")
            for key, val in fundamentals.items():
                print(f"{key}: {val}")
            print("\n--- Summary (First 100 chars) ---")
            print(summary[:100] + "...")
        else:
            print("Failed to fetch fundamentals.")

        # 2. Test NewsAPI
        print(f"\nFetching news for {TICKER}...")
        news = get_news(TICKER, YOUR_API_KEY, num_articles=5)
        if news:
            print("\n--- News (Top 3) ---")
            for i, article in enumerate(news[:3]):
                print(f"[{article['source']['name']}] {article['title']}")
        else:
            print("Failed to fetch news.")

        # 3. Test RAG Processing
        print("\n--- Testing RAG Processing ---")
        if not news and not summary:
            print("No data to process. Skipping RAG test.")
        else:
            vector_index, chunks, meta = process_and_embed(news, summary, TICKER)
            if vector_index:
                print(f"Successfully created vector index with {vector_index.ntotal} items.")
                
                # 4. Test RAG Retrieval (using ai_logic's function)
                try:
                    from ai_logic import retrieve_relevant_chunks
                    print("\n--- Testing RAG Retrieval ---")
                    query = "What are the latest developments in AI?"
                    relevant_chunks, citations = retrieve_relevant_chunks(
                        query, vector_index, chunks, meta
                    )
                    if relevant_chunks:
                        print(f"Found {len(relevant_chunks)} relevant chunks for query: '{query}'")
                        print("\n--- Top Citation ---")
                        print(citations[0])
                    else:
                        print("Test retrieval failed to find chunks.")
                except ImportError:
                    print("\nSkipping RAG retrieval test (could not import ai_logic).")
                except Exception as e:
                    print(f"\nRAG retrieval test failed: {e}")
            else:
                print("Failed to create vector index.")
        
        print("\n--- Phase 2 (Data Fetcher) test complete! ---")
