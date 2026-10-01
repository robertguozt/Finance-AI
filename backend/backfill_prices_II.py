import os
import time
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")
AV_KEY = os.environ.get("ALPHAVANTAGE_KEY")

TICKERS = ["AAPL", "MSFT", "GOOGL"]   # start with 3; free tier = 25 calls/day

def fetch_alphavantage(ticker):
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker,
        "outputsize": "compact",      # full history, not just latest 100 days
        "apikey": AV_KEY,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    # Alpha Vantage puts errors / rate-limit notes in the JSON body
    if "Time Series (Daily)" not in data:
        raise ValueError(f"no data returned: {str(data)[:200]}")

    return data["Time Series (Daily)"]

def backfill():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    total_rows = 0
    for ticker in TICKERS:
        print(f"Downloading {ticker} from Alpha Vantage ...")
        try:
            series = fetch_alphavantage(ticker)
        except Exception as e:
            print(f"  skipped {ticker}: {e}")
            continue

        rows = []
        for date_str, ohlcv in series.items():
            rows.append((
                ticker,
                date_str,                       # already "YYYY-MM-DD"
                float(ohlcv["1. open"]),
                float(ohlcv["2. high"]),
                float(ohlcv["3. low"]),
                float(ohlcv["4. close"]),
                int(ohlcv["5. volume"]),
            ))

        execute_values(cur, """
            INSERT INTO prices (ticker, trade_date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker, trade_date) DO NOTHING
        """, rows)
        conn.commit()

        total_rows += len(rows)
        print(f"  inserted ~{len(rows)} rows for {ticker}")
        time.sleep(15)   # free tier is ~5 calls/min; 15s spacing is safe

    cur.execute("SELECT COUNT(*) FROM prices;")
    print(f"\nDone. Total rows in prices table: {cur.fetchone()[0]}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    backfill()