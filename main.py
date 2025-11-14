import argparse
import sqlite3
import time
import sys
import os

# --- Import from our other files ---
# --- Import from our other files ---
try:
    from data_fetcher import get_fundamentals, get_news, process_and_embed
    from ai_logic import retrieve_relevant_chunks, build_prompt, get_analysis
except ImportError as e:  # <-- We capture the error as 'e'
    print("\n" + "="*50)
    print("FATAL ERROR: A required library is missing or failed to import.")
    print(f"The original error was: {e}") # <-- We print the REAL error
    print("\nPlease check that all libraries are installed in your virtual environment:")
    print("pip install yfinance requests sentence-transformers faiss-cpu nltk numpy")
    print("="*50 + "\n")
    sys.exit(1)

# --- !! IMPORTANT !! ---
# PASTE YOUR NewsAPI.org KEY HERE:
# This is used for the main application flow.
YOUR_API_KEY = "73a2fbdfc56949b6ae149b56651507c8" # e.g., "f0a123b456c789d0e12f3456a7b89c0d"

# --- 1. Database Setup ---
DB_NAME = 'analysis_cache.db'
CACHE_DURATION = 3600  # 1 hour in seconds

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache
        (ticker TEXT PRIMARY KEY,
         analysis TEXT,
         timestamp REAL)
    ''')
    conn.commit()
    conn.close()

def get_cached_analysis(ticker):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT analysis, timestamp FROM cache WHERE ticker = ?", (ticker,))
    result = c.fetchone()
    conn.close()
    
    if result:
        analysis, timestamp = result
        if (time.time() - timestamp) < CACHE_DURATION:
            return analysis
    return None

def set_cached_analysis(ticker, analysis):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("REPLACE INTO cache (ticker, analysis, timestamp) VALUES (?, ?, ?)",
              (ticker, analysis, time.time()))
    conn.commit()
    conn.close()
    
# --- 2. Main Application Flow ---

def run_full_analysis(ticker, api_key):
    """
    Runs the complete data-to-analysis pipeline.
    """
    print(f"--- Starting new analysis for {ticker} ---")
    
    # --- Step 1: Fetch Data ---
    print(f"Fetching fundamentals for {ticker}...")
    fundamentals, summary = get_fundamentals(ticker)
    
    print(f"Fetching news for {ticker}...")
    news = get_news(ticker, api_key)
    
    if not fundamentals:
        return "Error: Could not fetch fundamental data for ticker."

    # --- [DEBUG] ADD THIS BLOCK ---
    if not news:
        print("[DEBUG] get_news() returned an EMPTY list. No articles found.")
    else:
        print(f"[DEBUG] get_news() found {len(news)} articles.")
    # --- [END DEBUG BLOCK] ---

    # --- Step 2: Process & Embed Data (RAG) ---
    print("Processing and embedding data...")
    vector_index, text_chunks, metadata = process_and_embed(news, summary)

    # --- [DEBUG] ADD THIS BLOCK ---
    if vector_index is None:
        print("[DEBUG] process_and_embed() returned a 'None' vector_index.")
    else:
        print(f"[DEBUG] process_and_embed() created an index with {vector_index.ntotal} items.")
    # --- [END DEBUG BLOCK] ---

    # --- Step 3: Retrieve Relevant Chunks ---
    query = f"Recent news and developments for {ticker}"
    relevant_chunks, citations = retrieve_relevant_chunks(
        query, vector_index, text_chunks, metadata
    )
    
    # --- Step 4: Build Prompt & Get Analysis ---
    print("Building prompt...")
    user_prompt = build_prompt(ticker, fundamentals, relevant_chunks, citations)
    
    analysis = get_analysis(user_prompt)
    
    # --- Step 5: Add Citations to Analysis ---
    if citations:
        citation_header = "\n\n--- Sources ---\n"
        citation_list = "\n".join(citations)
        analysis += citation_header + citation_list
        
    return analysis

# --- 3. Main execution ---

def main():
    if not YOUR_API_KEY:
        print("Error: YOUR_API_KEY is not set in main.py. Please add it.")
        sys.exit(1)

    # Setup command-line argument parsing
    parser = argparse.ArgumentParser(description="AI Stock Analyst CLI")
    parser.add_argument(
        '-t', '--ticker', 
        type=str, 
        required=True,
        help="The stock ticker symbol to analyze (e.g., AAPL, MSFT)."
    )
    args = parser.parse_args()
    ticker = args.ticker.upper()
    
    print(f"Analyzing {ticker}...")
    
    # --- Step 1: Check Cache ---
    cached_result = get_cached_analysis(ticker)
    if cached_result:
        print(f"Loading analysis for {ticker} from cache...")
        print("="*40)
        print(cached_result)
        print("="*40)
        print("\nNote: This is a cached result. To force a new analysis, delete 'analysis_cache.db' and run again.")
        return

    # --- Step 2: Run Full Pipeline ---
    try:
        analysis = run_full_analysis(ticker, YOUR_API_KEY)
        
        # --- Step 3: Print & Cache Result ---
        print("\n" + "="*40)
        print(f"ANALYSIS FOR {ticker}")
        print("="*40)
        print(analysis)
        print("="*40)
        
        set_cached_analysis(ticker, analysis)
        
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    init_db()  # Ensure the database table exists
    main()
