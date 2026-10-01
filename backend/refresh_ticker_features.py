import os

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

from stock_recommender_II import (
    HORIZON_DAYS,
    compute_features,
    get_candidate_tickers,
    load_price_history,
    load_sector_metadata,
)

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

CANDIDATE_LIMIT = 50
LOOKBACK_DAYS = 1825

UPSERT_FEATURES_SQL = """
INSERT INTO ticker_features (
    ticker,
    holding_horizon,
    annual_return,
    annual_volatility,
    max_drawdown,
    last_close,
    sector
)
VALUES %s
ON CONFLICT (ticker, holding_horizon)
DO UPDATE SET
    annual_return = EXCLUDED.annual_return,
    annual_volatility = EXCLUDED.annual_volatility,
    max_drawdown = EXCLUDED.max_drawdown,
    last_close = EXCLUDED.last_close,
    sector = EXCLUDED.sector,
    updated_at = NOW()
"""

def refresh_features():
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30)

    try:
        # Long-term features need at least 756 trading days of history.
        minimum_rows = HORIZON_DAYS["long"] + 1

        candidates = get_candidate_tickers(
            conn,
            min_rows=minimum_rows,
            limit=CANDIDATE_LIMIT,
        )

        print(f"Selected {len(candidates)} candidate tickers.")

        # This is slow, but it runs only during a refresh, not per user request.
        price_history = load_price_history(
            conn,
            candidates,
            lookback_days=LOOKBACK_DAYS,
        )

        print(f"Loaded {len(price_history)} price rows.")

        sector_by_ticker = load_sector_metadata(conn, candidates)

        cur = conn.cursor()

        for holding_horizon in HORIZON_DAYS:
            features = compute_features(
                price_history,
                holding_horizon=holding_horizon,
            )

            features["sector"] = (
                pd.Series(features.index, index=features.index)
                .map(sector_by_ticker)
                .fillna("Unknown")
            )

            rows = []

            for ticker, row in features.iterrows():
                rows.append(
                    (
                        ticker,
                        holding_horizon,
                        float(row["annual_return"]),
                        float(row["annual_volatility"]),
                        float(row["max_drawdown"]),
                        float(row["last_close"]),
                        row["sector"],
                    )
                )

            execute_values(
                cur,
                UPSERT_FEATURES_SQL,
                rows,
            )

            conn.commit()

            print(
                f"Saved {len(rows)} feature rows "
                f"for holding horizon: {holding_horizon}"
            )

        cur.close()

    finally:
        conn.close()


if __name__ == "__main__":
    refresh_features()