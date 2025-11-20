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
    print("Error: One or more required libraries are not installed.")
    pass 

# --- Download NLTK data ---
def download_nltk_data():
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        print("NLTK 'punkt' tokenizer not found. Downloading...")
        nltk.download('punkt', quiet=True)
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("NLTK 'punkt_tab' resource not found. Downloading...")
        nltk.download('punkt_tab', quiet=True)

# --- Global var ---
embedding_model = None

def load_embedding_model():
    global embedding_model
    if embedding_model is None:
        print("Loading embedding model...")
        try:
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("Embedding model loaded.")
        except Exception as e:
            print(f"Error loading embedding model: {e}")

# --- 1. Data Fetching ---
def get_fundamentals(ticker_symbol):
    try:
        print(f"Fetching fundamentals for {ticker_symbol}...")
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Basic error check
        if not info or 'regularMarketPrice' not in info:
             # yfinance sometimes returns partial data even on failure
             pass

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
        summary = info.get('longBusinessSummary', 'No summary available.')
        return fundamentals, summary
    except Exception as e:
        print(f"Error fetching fundamentals: {e}")
        return {}, "Error fetching summary."

def get_news(ticker_symbol, api_key, num_articles=20):
    if not api_key:
        print("Error: No NewsAPI key provided.")
        return []

    base_url = "https://newsapi.org/v2/everything"
    params = {
        'q': ticker_symbol,
        'apiKey': api_key,
        'language': 'en',
        'sortBy': 'publishedAt',
        'pageSize': num_articles
    }
    
    try:
        print(f"Fetching news for {ticker_symbol}...")
        response = requests.get(base_url, params=params, timeout=10) # Add timeout
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'ok':
            articles = data.get('articles', [])
            return articles
        else:
            print(f"Error from NewsAPI: {data.get('message')}")
            return []
            
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []
        
    return []

# --- 2. RAG Processing ---
def process_and_embed(news_articles, summary_text, ticker=""):
    global embedding_model
    if embedding_model is None:
        load_embedding_model()
        
    if embedding_model is None:
        print("Embedding model not loaded. Skipping RAG.")
        return None, [], []

    text_chunks = []
    metadata = []
    
    # Process Summary
    if summary_text and summary_text != 'No summary available.':
        try:
            summary_sentences = sent_tokenize(summary_text)
            for i in range(0, len(summary_sentences), 3):
                chunk = " ".join(summary_sentences[i:i+3])
                text_chunks.append(chunk)
                metadata.append({
                    'source': f"{ticker} Business Summary",
                    'date': 'N/A',
                    'url': '#' 
                })
        except Exception as e:
             print(f"Error tokenizing summary: {e}")

    # Process News
    for article in news_articles:
        content = article.get('description', '') or article.get('content', '')
        if not content:
            continue
        
        content = re.sub(r'\[\+\d+ chars\]$', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        if not content:
            continue
        
        try:
            sentences = sent_tokenize(content)
            for i in range(0, len(sentences), 4):
                chunk = " ".join(sentences[i:i+4])
                text_chunks.append(chunk)
                metadata.append({
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'date': article.get('publishedAt', 'Unknown')[:10],
                    'url': article.get('url', '#')
                })
        except Exception as e:
             # print(f"Error processing article: {e}") 
             pass

    if not text_chunks:
        return None, [], []

    try:
        embeddings = embedding_model.encode(text_chunks, show_progress_bar=False)
        
        if embeddings.dtype != 'float32':
            embeddings = embeddings.astype('float32')
            
        dimension = embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)
        
        return index, text_chunks, metadata
        
    except Exception as e:
        print(f"Error creating FAISS index: {e}")
        return None, [], []
