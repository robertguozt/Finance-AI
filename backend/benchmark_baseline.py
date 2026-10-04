import time
import statistics
import data_fetcher
from data_fetcher import get_fundamentals, get_news, process_and_embed, load_embedding_model, download_nltk_data
from stock_recommender import recommend_stocks
import os

TICKER = "AAPL"
NEWS_KEY = os.environ.get("YOUR_API_KEY")

def one_run():
    stages = {}

    t = time.perf_counter()
    fundamentals, summary = get_fundamentals(TICKER)
    stages["fundamentals"] = time.perf_counter() - t

    t = time.perf_counter()
    news = get_news(TICKER, NEWS_KEY)
    stages["news"] = time.perf_counter() - t

    t = time.perf_counter()
    process_and_embed(news, summary, TICKER)
    stages["embed"] = time.perf_counter() - t

    t = time.perf_counter()
    recommend_stocks("I like tech growth stocks", ["stable income"], 15, "Medium")
    stages["recommend"] = time.perf_counter() - t

    return stages

if __name__ == "__main__":
    download_nltk_data()
    load_embedding_model()

    N = 5
    all_runs = []
    for i in range(N):
        data_fetcher.CALL_COUNTS = {"yfinance": 0, "newsapi": 0}
        print(f"\n--- Run {i+1}/{N} ---")
        stages = one_run()
        stages["_total"] = sum(stages.values())
        stages["_yf_calls"] = data_fetcher.CALL_COUNTS["yfinance"]
        stages["_news_calls"] = data_fetcher.CALL_COUNTS["newsapi"]
        all_runs.append(stages)
        print(stages)

    print("\n===== BASELINE (median of", N, "runs) =====")
    for key in ["fundamentals", "news", "embed", "recommend", "_total"]:
        vals = [r[key] for r in all_runs]
        print(f"{key:>14}: {statistics.median(vals):.3f}s")
    print(f"{'yf_calls':>14}: {all_runs[-1]['_yf_calls']}")
    print(f"{'news_calls':>14}: {all_runs[-1]['_news_calls']}")
