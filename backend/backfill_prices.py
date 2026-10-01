import os
import time
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

# Start small to validate the pipeline, then expand this list later.
TICKERS = [
    "AAPL", "MSFT", "GOOGL"
]
YEARS = 10

def backfill():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    total_rows = 0
    for ticker in TICKERS:
        print(f"Downloading {ticker} ...")
        df = yf.download(ticker, period=f"{YEARS}y", interval="1d", auto_adjust=False,
                         progress=False)

        if df.empty:
            print(f"  skipped {ticker} (no data)")
            continue

        # Build a list of rows: (ticker, date, open, high, low, close, volume)
        rows = []
        for date, r in df.iterrows():
            rows.append((
                ticker,
                date.date(),
                float(r["Open"]),
                float(r["High"]),
                float(r["Low"]),
                float(r["Close"]),
                int(r["Volume"]),
            ))

        # Bulk insert; skip rows that already exist (idempotent).
        execute_values(cur, """
            INSERT INTO prices (ticker, trade_date, open, high, low, close, volume)
            VALUES %s
            ON CONFLICT (ticker, trade_date) DO NOTHING
        """, rows)
        conn.commit()

        total_rows += len(rows)
        print(f"  inserted ~{len(rows)} rows for {ticker}")
        time.sleep(6)  # be polite to yfinance, avoid rate limiting

    # Verify total row count.
    cur.execute("SELECT COUNT(*) FROM prices;")
    print(f"\nDone. Total rows in prices table: {cur.fetchone()[0]}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    backfill()