import os
import time
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

TICKER_LIMIT = 50
DELAY_SECONDS = 1.0


def backfill_fundamentals():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT DISTINCT ticker
        FROM prices
        ORDER BY ticker
        LIMIT %s
        """,
        (TICKER_LIMIT,),
    )

    tickers = [row[0] for row in cur.fetchall()]
    print(f"Found {len(tickers)} tickers to enrich.")

    for ticker in tickers:
        try:
            print(f"Fetching fundamentals for {ticker}...")

            info = yf.Ticker(ticker).info

            sector = info.get("sector")
            market_cap = info.get("marketCap")

            if not sector:
                print(f"  Skipped {ticker}: no sector returned.")
                continue

            cur.execute(
                """
                INSERT INTO fundamentals (
                    ticker,
                    sector,
                    market_cap,
                    volatility,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (ticker)
                DO UPDATE SET
                    sector = EXCLUDED.sector,
                    market_cap = EXCLUDED.market_cap,
                    updated_at = NOW()
                """,
                (
                    ticker,
                    sector,
                    int(market_cap) if market_cap else None,
                    None,
                ),
            )

            conn.commit()
            print(f"  Saved {ticker}: {sector}")

        except Exception as error:
            conn.rollback()
            print(f"  Failed {ticker}: {error}")

        time.sleep(DELAY_SECONDS)

    cur.close()
    conn.close()


if __name__ == "__main__":
    backfill_fundamentals()