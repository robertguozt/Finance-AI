import requests
import re
import sys
import os
import psycopg2
from psycopg2.extras import Json
import time

# bench
CALL_COUNTS = {"yfinance": 0, "alpha_vantage": 0, "newsapi": 0}

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
FUNDAMENTALS_CACHE_DAYS = 7

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
    resources = [
        ("punkt", "tokenizers/punkt"),
        ("punkt_tab", "tokenizers/punkt_tab"),
    ]

    for package_name, resource_path in resources:
        try:
            nltk.data.find(resource_path)
        except (LookupError, OSError):
            print(f"NLTK '{package_name}' resource not found. Downloading...")
            success = nltk.download(package_name, quiet=True)

            if not success:
                raise RuntimeError(
                    f"Could not download NLTK resource: {package_name}"
                )

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
def _number_or_none(value):
    if value in (None, "", "None", "-", "N/A"):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_sector(raw_sector):
    if not raw_sector:
        return None

    sector_map = {
        "TECHNOLOGY": "Technology",
        "FINANCE": "Finance",
        "FINANCIAL SERVICES": "Finance",
        "HEALTHCARE": "Healthcare",
        "CONSUMER CYCLICAL": "Consumer",
        "CONSUMER DEFENSIVE": "Consumer",
        "ENERGY": "Energy",
        "INDUSTRIALS": "Industrial",
    }

    normalized_key = str(raw_sector).strip().upper()
    return sector_map.get(normalized_key, str(raw_sector).title())


def _load_cached_alpha_data(ticker_symbol):
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        return None, False, None

    conn = None

    try:
        conn = psycopg2.connect(database_url)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    provider_data,
                    updated_at >= NOW() - INTERVAL '7 days' AS is_fresh
                FROM fundamentals
                WHERE ticker = %s
                  AND provider = 'alpha_vantage'
                  AND provider_data IS NOT NULL
                """,
                (ticker_symbol,),
            )
            cache_row = cur.fetchone()

            cur.execute(
                """
                SELECT close
                FROM prices
                WHERE ticker = %s
                ORDER BY trade_date DESC
                LIMIT 1
                """,
                (ticker_symbol,),
            )
            price_row = cur.fetchone()

        cached_data = cache_row[0] if cache_row else None
        is_fresh = bool(cache_row[1]) if cache_row else False
        latest_price = float(price_row[0]) if price_row else None

        if latest_price is None and cached_data:
            latest_price = _number_or_none(
                cached_data.get("_CachedCurrentPrice")
            )

        return cached_data, is_fresh, latest_price

    except Exception as error:
        print(f"Error reading fundamentals cache: {error}")
        return None, False, None

    finally:
        if conn is not None:
            conn.close()


def _save_alpha_data(ticker_symbol, provider_data):
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("DATABASE_URL is not configured; skipping fundamentals cache.")
        return

    raw_market_cap = _number_or_none(
        provider_data.get("MarketCapitalization")
    )
    market_cap = int(raw_market_cap) if raw_market_cap is not None else None
    sector = _normalize_sector(provider_data.get("Sector"))

    conn = None

    try:
        conn = psycopg2.connect(database_url)

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fundamentals (
                    ticker,
                    sector,
                    market_cap,
                    provider,
                    provider_data,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (ticker)
                DO UPDATE SET
                    sector = COALESCE(
                        EXCLUDED.sector,
                        fundamentals.sector
                    ),
                    market_cap = COALESCE(
                        EXCLUDED.market_cap,
                        fundamentals.market_cap
                    ),
                    provider = EXCLUDED.provider,
                    provider_data = EXCLUDED.provider_data,
                    updated_at = NOW()
                """,
                (
                    ticker_symbol,
                    sector,
                    market_cap,
                    "alpha_vantage",
                    Json(provider_data),
                ),
            )

        conn.commit()
        print(f"Saved Alpha Vantage fundamentals for {ticker_symbol}.")

    except Exception as error:
        if conn is not None:
            conn.rollback()

        print(f"Error saving fundamentals cache: {error}")

    finally:
        if conn is not None:
            conn.close()


def _fetch_alpha_overview(ticker_symbol, api_key):
    CALL_COUNTS.setdefault("alpha_vantage", 0)
    CALL_COUNTS["alpha_vantage"] += 1
    time.sleep(1.2)

    response = requests.get(
        ALPHA_VANTAGE_URL,
        params={
            "function": "OVERVIEW",
            "symbol": ticker_symbol,
            "apikey": api_key,
        },
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()

    provider_error = (
        data.get("Error Message")
        or data.get("Information")
        or data.get("Note")
    )

    if provider_error:
        raise RuntimeError(provider_error)

    if data.get("Symbol", "").upper() != ticker_symbol:
        raise RuntimeError(
            f"Alpha Vantage returned no overview for {ticker_symbol}."
        )

    return data


def _fetch_alpha_price(ticker_symbol, api_key):
    CALL_COUNTS.setdefault("alpha_vantage", 0)
    CALL_COUNTS["alpha_vantage"] += 1
    time.sleep(1.2)

    response = requests.get(
        ALPHA_VANTAGE_URL,
        params={
            "function": "GLOBAL_QUOTE",
            "symbol": ticker_symbol,
            "apikey": api_key,
        },
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()

    provider_error = (
        data.get("Error Message")
        or data.get("Information")
        or data.get("Note")
    )

    if provider_error:
        raise RuntimeError(provider_error)

    quote = data.get("Global Quote", {})
    return _number_or_none(quote.get("05. price"))


def _build_fundamentals(provider_data, current_price):
    fundamentals = {}

    if current_price is not None:
        fundamentals["Current Price"] = current_price

    field_map = {
        "Market Cap": "MarketCapitalization",
        "P/E Ratio (Trailing)": "TrailingPE",
        "P/E Ratio (Forward)": "ForwardPE",
        "Price-to-Book (P/B)": "PriceToBookRatio",
        "PEG Ratio": "PEGRatio",
        "Dividend Yield": "DividendYield",
        "Earnings per Share (EPS)": "EPS",
        "Return on Equity (ROE)": "ReturnOnEquityTTM",
        "52 Week High": "52WeekHigh",
        "52 Week Low": "52WeekLow",
    }

    for display_name, provider_name in field_map.items():
        value = _number_or_none(provider_data.get(provider_name))

        if value is not None:
            if display_name == "Market Cap":
                fundamentals[display_name] = int(value)
            else:
                fundamentals[display_name] = value

    sector = _normalize_sector(provider_data.get("Sector"))

    if sector:
        fundamentals["Sector"] = sector

    return fundamentals


def get_fundamentals(ticker_symbol):
    ticker_symbol = ticker_symbol.strip().upper()

    cached_data, cache_is_fresh, current_price = (
        _load_cached_alpha_data(ticker_symbol)
    )

    if cached_data and cache_is_fresh:
        print(f"Using cached Alpha Vantage data for {ticker_symbol}.")
        fundamentals = _build_fundamentals(cached_data,current_price)
        summary = (
            cached_data.get("Description")
            or "No company summary was provided."
        )
        return fundamentals, summary

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")

    if not api_key:
        print("Error: ALPHA_VANTAGE_API_KEY is not configured.")

        if cached_data:
            print(f"Using stale cached data for {ticker_symbol}.")
            return (
                _build_fundamentals(cached_data, current_price),
                cached_data.get("Description")
                or "No company summary was provided.",
            )

        return {}, "Error fetching company summary."

    try:
        print(
            f"Fetching Alpha Vantage fundamentals for "
            f"{ticker_symbol}..."
        )
        provider_data = _fetch_alpha_overview(ticker_symbol, api_key)

        if current_price is None:
            current_price = _fetch_alpha_price(ticker_symbol, api_key)

            if current_price is not None:
                provider_data["_CachedCurrentPrice"] = current_price

        _save_alpha_data(ticker_symbol, provider_data)

        fundamentals = _build_fundamentals(provider_data, current_price)
        summary = (
            provider_data.get("Description")
            or "No company summary was provided."
        )

        return fundamentals, summary

    except Exception as error:
        print(f"Error fetching Alpha Vantage fundamentals: {error}")
        if cached_data:
            print(f"Using stale cached data for {ticker_symbol}.")
            return (
                _build_fundamentals(cached_data, current_price),
                cached_data.get("Description")
                or "No company summary was provided.",
            )

        return {}, "Error fetching company summary."

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
        CALL_COUNTS["newsapi"] += 1
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
