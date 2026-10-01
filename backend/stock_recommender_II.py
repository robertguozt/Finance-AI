import os
import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

TRADING_DAYS = 252

RISK_PENALTY = {
    "Low": 3.0,      # low tolerance -> penalize volatility hard
    "Medium": 1.0,
    "High": 0.3,     # high tolerance -> barely penalize
}

HORIZON_DAYS = {
    "short": 63,
    "medium": 252,
    "long": 756,
}

FINANCIAL_RISK_ADJUSTMENT = {
    "stable_income": -0.25,
    "emergency_fund": -0.25,
    "variable_income": 0.50,
    "high_debt": 1.00,
}


def get_candidate_tickers(conn, min_rows=500, limit=50):
    """Pull tickers with enough history, using an existing connection."""
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker FROM prices
        GROUP BY ticker
        HAVING COUNT(*) >= %s
        ORDER BY ticker
        LIMIT %s
    """, (min_rows, limit))
    tickers = [row[0] for row in cur.fetchall()]
    cur.close()
    return tickers


def load_price_history(conn, tickers, lookback_days=1825):
    """Load recent history via psycopg2 directly (fast), build DataFrame manually.
    Critically converts NUMERIC->float so numpy can vectorize the math."""
    placeholders = ",".join(["%s"] * len(tickers))
    query = f"""
        SELECT ticker, trade_date, close, volume
        FROM prices
        WHERE ticker IN ({placeholders})
          AND trade_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
        ORDER BY ticker, trade_date
    """
    cur = conn.cursor()
    cur.execute(query, tickers)
    rows = cur.fetchall()
    cur.close()

    df = pd.DataFrame(rows, columns=["ticker", "trade_date", "close", "volume"])
    df["close"] = df["close"].astype(float)     # Decimal -> float (huge speedup)
    df["volume"] = df["volume"].astype(float)
    return df

def load_sector_metadata(conn, tickers):
    if not tickers:
        return {}

    cur = conn.cursor()

    cur.execute(
        """
        SELECT ticker, sector
        FROM fundamentals
        WHERE ticker = ANY(%s)
        """,
        (tickers,),
    )

    sector_by_ticker = {
        ticker: sector
        for ticker, sector in cur.fetchall()
        if sector
    }

    cur.close()
    return sector_by_ticker

def load_precomputed_features(conn, holding_horizon):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            ticker,
            annual_return,
            annual_volatility,
            max_drawdown,
            last_close,
            COALESCE(sector, 'Unknown') AS sector
        FROM ticker_features
        WHERE holding_horizon = %s
        ORDER BY ticker
        """,
        (holding_horizon,),
    )

    rows = cur.fetchall()
    cur.close()

    columns = [
        "ticker",
        "annual_return",
        "annual_volatility",
        "max_drawdown",
        "last_close",
        "sector",
    ]

    features = pd.DataFrame(rows, columns=columns)

    if features.empty:
        return features.set_index("ticker")

    numeric_columns = [
        "annual_return",
        "annual_volatility",
        "max_drawdown",
        "last_close",
    ]

    for column in numeric_columns:
        features[column] = features[column].astype(float)

    return features.set_index("ticker")

def compute_features(df, holding_horizon, min_rows=500):
    required_days = HORIZON_DAYS[holding_horizon]
    recent = (
        df.groupby("ticker", group_keys=False)
        .tail(required_days + 1)
        .copy()
    )

    counts = recent.groupby("ticker")["close"].transform("count")
    recent = recent[counts >= required_days + 1].copy()

    recent["daily_return"] = recent.groupby("ticker")["close"].pct_change()
    recent["running_max"] = recent.groupby("ticker")["close"].cummax()
    recent["drawdown"] = recent["close"] / recent["running_max"] - 1

    grouped = recent.groupby("ticker")
    first_close = grouped["close"].first()
    last_close = grouped["close"].last()
    observations = grouped["close"].count()

    return pd.DataFrame({
        "annual_return": (last_close / first_close) ** (
            TRADING_DAYS / (observations - 1)
        ) - 1,
        "annual_volatility": grouped["daily_return"].std() * np.sqrt(TRADING_DAYS),
        "max_drawdown": grouped["drawdown"].min().abs(),
        "last_close": last_close,
    }).dropna()


def score_stocks(
    features,
    expected_return,
    risk_tolerance,
    financial_condition,
    preferred_sectors,
    investment_style
):
    df = features.copy()

    # The user's financial situation adjusts the risk penalty.
    financial_adjustment = sum(
        FINANCIAL_RISK_ADJUSTMENT.get(item, 0)
        for item in financial_condition
    )

    # Prevent stable_income + emergency_fund from making the
    # risk penalty negative, which would accidentally reward risk.
    effective_penalty = max(
        0.1,
        RISK_PENALTY.get(risk_tolerance, 1.0) + financial_adjustment,
    )

    # Convert a percentage such as 15 into a decimal value: 0.15.
    target_return = expected_return / 100.0

    # The closer the historical annual return is to the target,
    # the closer return_match is to 1.
    return_match = 1 - ((df["annual_return"] - target_return).abs() / max(target_return, 0.05)).clip(upper=1)

    # Add a bonus when a stock belongs to one of the user's
    # preferred sectors.
    sector_bonus = (
        df["sector"].isin(preferred_sectors).astype(float) * 0.20
    )

    style_bonus = 0.0
    if investment_style == "growth":
        style_bonus = df["annual_return"].rank(pct=True) * 0.10

    # Final score:
    # return fit + sector fit - volatility risk - drawdown risk.
    df["score"] = (
        0.60 * return_match
        + sector_bonus
        - effective_penalty * 0.15 * df["annual_volatility"]
        - effective_penalty * 0.10 * df["max_drawdown"]
        + style_bonus
    )

    return df.sort_values("score", ascending=False)


def _build_reason(
    row,
    expected_return,
    risk_tolerance,
    preferred_sectors,
    holding_horizon,
):
    annual_return = row["annual_return"] * 100
    annual_volatility = row["annual_volatility"] * 100
    max_drawdown = row["max_drawdown"] * 100
    sector = row["sector"]

    reasons = [
        (
            f"{holding_horizon.title()}-horizon annualized return "
            f"~{annual_return:.0f}% "
            f"(your target: {expected_return}%)."
        ),
        (
            f"Historical volatility ~{annual_volatility:.0f}% "
            f"and maximum drawdown ~{max_drawdown:.0f}% "
            f"for your {risk_tolerance} risk profile."
        ),
    ]

    if sector in preferred_sectors:
        reasons.append(
            f"Matches your preferred {sector} sector."
        )
    elif sector == "Unknown":
        reasons.append(
            "Sector metadata is not available yet."
        )

    return " ".join(reasons)

def recommend_stocks(trading_history: str,
    financial_condition: List[str],
    expected_return: int,
    risk_tolerance: str,
    preferred_sectors: Optional[List[str]] = None,
    investment_style: str = "balanced",
    holding_horizon: str = "medium",
    num_recommendations: int = 5,) -> List[Dict]:
    preferred_sectors = preferred_sectors or []
    import time
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=30)

    try:
        t = time.perf_counter()
        features = load_precomputed_features(conn, holding_horizon=holding_horizon)
        print(
            f"  load_features: {time.perf_counter() - t:.2f}s "
            f"({len(features)} rows)"
        )
    finally:
        conn.close()

    if features.empty:
        raise RuntimeError(
            f"No precomputed features found for horizon: {holding_horizon}. "
            "Run refresh_ticker_features.py first."
        )
    
    t = time.perf_counter()
    scored = score_stocks(
        features=features,
        expected_return=expected_return,
        risk_tolerance=risk_tolerance,
        financial_condition=financial_condition,
        preferred_sectors=preferred_sectors,
        investment_style=investment_style,
    )
    print(f"  score:      {time.perf_counter() - t:.2f}s")

    top = scored.head(num_recommendations)
    results = []
    for ticker, row in top.iterrows():
        results.append({
            "ticker": ticker,
            "score": round(float(row["score"]), 4),
            "sector": row["sector"],
            "reason": _build_reason(row, expected_return, risk_tolerance, preferred_sectors, holding_horizon),
            "current_price": round(float(row["last_close"]), 2),
            "pe_ratio": None,
        })
    return results


if __name__ == "__main__":
    import time
    t0 = time.perf_counter()
    recs = recommend_stocks(
        trading_history="I like tech and travel stocks",
        financial_condition=["stable_income"],
        expected_return=15,
        risk_tolerance="Medium",
        preferred_sectors=["Technology"],
        investment_style="growth",
        holding_horizon="long",
        num_recommendations=5,
    )
    print(f"Total: {time.perf_counter()-t0:.2f}s\n")
    for r in recs:
        print(r)