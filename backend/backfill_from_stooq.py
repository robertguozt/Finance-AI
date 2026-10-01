import os
import glob
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

# ====== CONFIG: adjust these ======
# Path to the UNZIPPED Stooq folder. Point it at the top-level 'us' folder
# (or higher). The script searches all subfolders for *.txt files.
STOOQ_DIR = r"D:\Pycharm-Community\Python Projects\Stock Recommender\data_US_Stock_Stooq\data\daily\us\nasdaq stocks"   # <-- CHANGE THIS

MAX_TICKERS = 100      # only load the first N tickers (set None to load all)
MIN_ROWS = 200      # skip files with fewer than this many rows (too thin)

def parse_stooq_file(filepath):
    """Read one Stooq .txt file, return a list of DB rows."""
    rows = []
    with open(filepath, "r") as f:
        header = f.readline()            # first line is the column header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 9:
                continue
            # Stooq columns: TICKER,PER,DATE,TIME,OPEN,HIGH,LOW,CLOSE,VOL,OPENINT
            raw_ticker = parts[0]                     # e.g. "AAPL.US"
            ticker = raw_ticker.split(".")[0]         # -> "AAPL"
            date_raw = parts[2]                       # e.g. "20250102"
            try:
                trade_date = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
                o = float(parts[4])
                h = float(parts[5])
                l = float(parts[6])
                c = float(parts[7])
                v = int(float(parts[8]))
            except (ValueError, IndexError):
                continue
            rows.append((ticker, trade_date, o, h, l, c, v))
    return rows

def backfill():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Find every .txt file under STOOQ_DIR, recursively
    pattern = os.path.join(STOOQ_DIR, "**", "*.txt")
    all_files = glob.glob(pattern, recursive=True)
    print(f"Found {len(all_files)} .txt files under {STOOQ_DIR}")

    loaded = 0
    total_rows = 0

    for filepath in all_files:
        if MAX_TICKERS is not None and loaded >= MAX_TICKERS:
            break

        rows = parse_stooq_file(filepath)
        if len(rows) < MIN_ROWS:
            continue  # skip thin files

        execute_values(cur, """
                INSERT INTO prices (ticker, trade_date, open, high, low, close, volume)
                VALUES %s
                ON CONFLICT (ticker, trade_date) DO NOTHING
            """, rows)
        conn.commit()

        loaded += 1
        total_rows += len(rows)
        print(f"  [{loaded}] {os.path.basename(filepath)}: {len(rows)} rows")

    cur.execute("SELECT COUNT(*) FROM prices;")
    print(f"\nDone. Loaded {loaded} tickers. Total rows in prices table: {cur.fetchone()[0]}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    backfill()