import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

CREATE_PRICES = """
CREATE TABLE IF NOT EXISTS prices (
    ticker      VARCHAR(10)   NOT NULL,
    trade_date  DATE          NOT NULL,
    open        NUMERIC(12,4),
    high        NUMERIC(12,4),
    low         NUMERIC(12,4),
    close       NUMERIC(12,4),
    volume      BIGINT,
    PRIMARY KEY (ticker, trade_date)
);
"""

CREATE_FUNDAMENTALS = """
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker        VARCHAR(10) PRIMARY KEY,
    sector        VARCHAR(100),
    market_cap    BIGINT,
    volatility    NUMERIC(8,4),
    updated_at    TIMESTAMP DEFAULT NOW()
);
"""

ALTER_FUNDAMENTALS_ALPHA_COLUMNS = """
ALTER TABLE fundamentals
ADD COLUMN IF NOT EXISTS provider VARCHAR(50);

ALTER TABLE fundamentals
ADD COLUMN IF NOT EXISTS provider_data JSONB;
"""

CREATE_TICKER_FEATURES = """
CREATE TABLE IF NOT EXISTS ticker_features (
    ticker            VARCHAR(10) NOT NULL,
    holding_horizon   VARCHAR(10) NOT NULL,
    annual_return     NUMERIC(12, 6) NOT NULL,
    annual_volatility NUMERIC(12, 6) NOT NULL,
    max_drawdown      NUMERIC(12, 6) NOT NULL,
    last_close        NUMERIC(12, 4) NOT NULL,
    sector            VARCHAR(100),
    updated_at        TIMESTAMP NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, holding_horizon),

    CHECK (holding_horizon IN ('short', 'medium', 'long'))
);
"""

CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      UUID PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    result      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN ('pending', 'complete', 'failed'))
);
"""

CREATE_TICKER_FEATURES_HORIZON_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ticker_features_horizon
ON ticker_features (holding_horizon);
"""

conn = psycopg2.connect(DATABASE_URL) # Connect to the Postgres in the cloud, conn represents
                                      # this entire channel to the database
cur = conn.cursor() # The hand that truly executes SQL and receives the results

cur.execute(CREATE_PRICES)
cur.execute(CREATE_FUNDAMENTALS)
cur.execute(ALTER_FUNDAMENTALS_ALPHA_COLUMNS)
cur.execute(CREATE_TICKER_FEATURES)
cur.execute(CREATE_TICKER_FEATURES_HORIZON_INDEX)
cur.execute(CREATE_JOBS)

conn.commit()   # Like 'save'

print("The table creation is completed. Existing table:")
cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'public';
""")
for row in cur.fetchall():
    print("  -", row[0])

cur.close()
conn.close()