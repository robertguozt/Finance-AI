# benchmark_compare.py
import time
import statistics

from stock_recommender import recommend_stocks as recommend_old
from stock_recommender_II import recommend_stocks as recommend_new

ARGS = ("I like tech growth stocks", ["stable income"], 15, "Medium")
N = 3  

def time_engine(func, label, runs=N):
    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        try:
            result = func(*ARGS)
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            print(f"  [{label}] run {i+1}: {elapsed:.2f}s ({len(result)} recs)")
        except Exception as e:
            print(f"  [{label}] run {i+1}: FAILED - {e}")
    if times:
        print(f"  [{label}] median: {statistics.median(times):.2f}s\n")
    return times

if __name__ == "__main__":
    print("=== NEW engine (Postgres + vectorized) ===")
    time_engine(recommend_new, "NEW")

    print("=== OLD engine (live yfinance loop) ===")
    time_engine(recommend_old, "OLD")
