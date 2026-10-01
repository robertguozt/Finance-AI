import uvicorn
import psycopg2
import sys
import os
import json
import uuid # For creating unique job IDs
import hashlib
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from contextlib import asynccontextmanager
import redis
from redis.exceptions import RedisError
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

# --- Import from our other files ---
try:
    from data_fetcher import (
        get_fundamentals,
        get_news,
        process_and_embed,
        load_embedding_model,
        download_nltk_data,
    )
    from ai_logic import retrieve_relevant_chunks, build_prompt, get_analysis
    from stock_recommender_II import recommend_stocks
except ImportError as e:
    print(f"Error: Could not import from helper files: {e}")
    sys.exit(1)

#BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

# --- Load API keys ---
YOUR_API_KEY = os.environ.get("YOUR_API_KEY")
if not YOUR_API_KEY:
    print("Error: YOUR_API_KEY (for NewsAPI) is not set as an environment variable.")

# --- 1. Define API Models ---
class AnalysisRequest(BaseModel):
    ticker: str
    financialCondition: List[
        Literal["stable_income", "variable_income", "high_debt", "emergency_fund"]
    ] = Field(default_factory=list)
    hasOtherFinancialCondition: bool = False
    financialConditionOther: str = Field(default="", max_length=300)
    expectedReturn: int = Field(ge=0, le=100)
    riskTolerance: Literal["Low", "Medium", "High"]
    preferredSectors: List[
        Literal["Technology", "Finance", "Healthcare", "Consumer", "Energy", "Industrial"]
    ] = Field(default_factory=list)
    investmentStyle: Literal["growth", "balanced"] = "balanced"
    holdingHorizon: Literal["short", "medium", "long"] = "medium"
    tradingPreferences: str = ""

class AnalysisResponse(BaseModel):
    jobId: str

class StatusResponse(BaseModel):
    status: str
    result: Optional[str] = None # Will contain the JSON string when complete

# --- 2. FastAPI Lifespan Event ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """ Runs on server startup """
    print("--- Server starting up... ---")
    print("--- Initializing PostgreSQL job storage ---")
    init_postgres()
    connect_redis()
    print("--- Downloading NLTK data (if needed) ---")
    download_nltk_data()
    print("--- Pre-loading embedding model ---")
    load_embedding_model()
    print("--- Startup complete. Server is ready. ---")
    yield
    if redis_client is not None:
        redis_client.close()
    print("--- Server shutting down... ---")

# --- 3. Initialize FastAPI App ---
app = FastAPI(lifespan=lifespan) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- 4. Caching & Database Logic (UPDATED) ---
DATABASE_URL = os.environ.get("DATABASE_URL")
CACHE_DURATION = 3600 # 1 hour
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHE_PREFIX = "analysis:v3"
redis_client: Optional[redis.Redis] = None
CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      UUID PRIMARY KEY,
    status      VARCHAR(20) NOT NULL,
    result      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (status IN ('pending', 'complete', 'failed'))
);
"""

def connect_redis():
    global redis_client

    try:
        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        redis_client = client
        print("Redis cache connected.")
    except RedisError as error:
        redis_client = None
        print(f"Warning: Redis is unavailable; cache is disabled. {error}")

def extract_financial_conditions(other_text: str) -> set[str]:
    text = other_text.lower()
    conditions = set()

    if any(word in text for word in [
        "irregular income",
        "variable income",
        "freelance",
        "student",
    ]):
        conditions.add("variable_income")

    if any(word in text for word in [
        "debt",
        "loan",
        "mortgage",
        "credit card",
    ]):
        conditions.add("high_debt")

    if any(word in text for word in [
        "emergency fund",
        "savings buffer",
    ]):
        conditions.add("emergency_fund")

    return conditions

def build_unavailable_fundamentals(ticker: str) -> tuple[dict, str]:
    """
    Provide transparent fallback data when the fundamentals provider is unavailable.
    """
    fundamentals = {
        "Ticker": ticker,
        "Data availability": (
            "Fundamental data is temporarily unavailable because the "
            "upstream provider rate-limited the request."
        ),
    }

    summary = (
        "Company summary is temporarily unavailable because the "
        "upstream fundamentals provider rate-limited the request."
    )

    return fundamentals, summary

def connect_postgres():
    """
    Create a short-lived PostgreSQL connection.

    Each job operation opens and closes its own connection so that
    connections are not accidentally shared between background tasks.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg2.connect(
        DATABASE_URL,
        connect_timeout=30,
    )


def init_postgres():
    """
    Ensure that the PostgreSQL jobs table exists.
    """
    conn = connect_postgres()

    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_JOBS_TABLE)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_job(job_id: str):
    """
    Create a pending job before starting background analysis.
    """
    conn = connect_postgres()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jobs (job_id, status, result)
                VALUES (%s, %s, %s)
                """,(job_id, "pending", None),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_job_complete(job_id: str, result: str):
    """
    Store the completed analysis and mark the job complete.
    """
    conn = connect_postgres()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET
                    status = %s,
                    result = %s,
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (
                    "complete",
                    result,
                    job_id,
                ),
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def update_job_failed(job_id: str, error_message: str):
    """
    Store a safe error message and mark the job failed.
    """
    conn = connect_postgres()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET
                    status = %s,
                    result = %s,
                    updated_at = NOW()
                WHERE job_id = %s
                """,
                (
                    "failed",
                    error_message,
                    job_id,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_job_status(job_id: str):
    """
    Read the latest job state from PostgreSQL.
    """
    conn = connect_postgres()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, result
                FROM jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {
                "status": "not_found",
                "result": None,
            }
        return {
            "status": row[0],
            "result": row[1],
        }
    finally:
        conn.close()

# --- Cache Key Generation ---
def generate_cache_key(ticker: str, request: AnalysisRequest) -> str:
    """
    Create a deterministic Redis key for one complete user profile.
    """
    profile = {
        "ticker": ticker.upper(),
        "tradingPreferences": request.tradingPreferences.strip(),
        "riskTolerance": request.riskTolerance,
        "expectedReturn": request.expectedReturn,
        "financialCondition": sorted(request.financialCondition),
        "preferredSectors": sorted(request.preferredSectors),
        "investmentStyle": request.investmentStyle,
        "holdingHorizon": request.holdingHorizon,
    }

    canonical_profile = json.dumps(
        profile,
        sort_keys=True,
        separators=(",", ":"),
    )
    profile_hash = hashlib.sha256(
        canonical_profile.encode("utf-8")
    ).hexdigest()

    return f"{CACHE_PREFIX}:{ticker.upper()}:{profile_hash}"


def get_cached_analysis(ticker: str, request: AnalysisRequest):
    """
    Read a completed analysis from Redis. Return None on a cache miss
    or when Redis is unavailable, so analysis can continue normally.
    """
    if redis_client is None:
        return None

    try:
        cache_key = generate_cache_key(ticker, request)
        cached_analysis = redis_client.get(cache_key)

        if cached_analysis is not None:
            print(f"Redis cache hit for {ticker}")
            return cached_analysis

        print(f"Redis cache miss for {ticker}")
    except RedisError as error:
        print(f"Warning: Redis cache read failed: {error}")

    return None


def set_cached_analysis(ticker: str, analysis: str, request: AnalysisRequest):
    """
    Store a completed analysis in Redis with a one-hour TTL.
    """
    if redis_client is None:
        return

    try:
        cache_key = generate_cache_key(ticker, request)
        redis_client.set(cache_key, analysis, ex=CACHE_DURATION)
        print(f"Stored Redis cache for {ticker}; TTL={CACHE_DURATION}s")
    except RedisError as error:
        print(f"Warning: Redis cache write failed: {error}")

# --- 5. The Long-Running Analysis Task (NEW) ---
def run_full_analysis_task(job_id: str, request: AnalysisRequest):
    """
    This is the long-running function that runs in the background.
    """
    try:
        ticker = request.ticker.upper()
        print(f"--- [Background Job: {job_id}] Starting analysis for {ticker} ---")
        
        # 1. Check cache first (with user preferences)
        cached_result = get_cached_analysis(ticker, request)
        if cached_result:
            print(f"[Background Job: {job_id}] Found cached result.")
            update_job_complete(job_id, cached_result)
            return

        if not YOUR_API_KEY:
            raise Exception("Server Configuration Error: NewsAPI key is not set.")

        # --- TASK 1: Get AI Analysis (Forecast, Advice) ---
        print(f"[Background Job: {job_id}] Fetching fundamentals...")
        fundamentals, summary = get_fundamentals(ticker)
        if not fundamentals:
            print(
                f"Fundamentals unavailable for {ticker}; "
                "continuing with transparent fallback data."
            )
            fundamentals, summary = build_unavailable_fundamentals(ticker)

        print(f"[Background Job: {job_id}] Fetching news...")
        news = get_news(ticker, YOUR_API_KEY)
        
        print(f"[Background Job: {job_id}] Processing and embedding data...")
        vector_index, text_chunks, metadata = process_and_embed(news, summary, ticker)
        
        query = f"Recent news, developments, and user context for {ticker}"
        relevant_chunks, citations = retrieve_relevant_chunks(
            query, vector_index, text_chunks, metadata
        )
        
        print(f"[Background Job: {job_id}] Building AI prompt...")
        user_prompt = build_prompt(
            ticker=request.ticker,
            fundamentals=fundamentals,
            relevant_chunks=relevant_chunks,
            citations=citations
        )
        
        ai_json_string = get_analysis(user_prompt)
        
        # --- TASK 2: Get Rule-Based Recommendations (THE SLOW PART) ---
        print(f"[Background Job: {job_id}] Running rule-based stock recommender...")
        effective_financial_condition = set(request.financialCondition)

        if request.hasOtherFinancialCondition:
            effective_financial_condition.update(
                extract_financial_conditions(
                    request.financialConditionOther
                )
            )
        recommendations_list = recommend_stocks(
            trading_history=request.tradingPreferences,
            financial_condition=list(effective_financial_condition),
            expected_return=request.expectedReturn,
            risk_tolerance=request.riskTolerance,
            preferred_sectors=request.preferredSectors,
            investment_style=request.investmentStyle,
            holding_horizon=request.holdingHorizon
        )
        
        # --- TASK 3: Combine Results ---
        print(f"[Background Job: {job_id}] Combining results...")
        
        ai_data = json.loads(ai_json_string)
        ai_data['recommendedStocks'] = recommendations_list
        
        if citations:
            citation_header = "\n\n--- Sources ---\n"
            citation_list = "\n".join(citations)
            ai_data['analysis'] += citation_header + citation_list
        
        final_json_string = json.dumps(ai_data)
        
        # --- TASK 4: Cache and Update Job Status ---
        set_cached_analysis(ticker, final_json_string, request)
        update_job_complete(job_id, final_json_string)
        print(f"--- [Background Job: {job_id}] Analysis for {ticker} complete. ---")

    except Exception as e:
        print(f"--- [Background Job: {job_id}] FAILED ---")
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        update_job_failed(job_id, str(e))

# --- 6. API Endpoints (UPDATED) ---

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Finance AI Backend is running!"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.post("/api/analyze")
async def analyze_direct(request: AnalysisRequest):
    """
    Real analysis endpoint that processes user inputs synchronously
    and returns complete results immediately.
    """
    try:
        print(f"=== Starting Real Analysis ===")
        print(f"Ticker: {request.ticker}")
        print(f"Risk: {request.riskTolerance}")
        print(f"Expected Return: {request.expectedReturn}%")
        ticker = request.ticker.upper()
        
        # Check cache first (with user preferences)
        cached_result = get_cached_analysis(ticker, request)
        if cached_result:
            print("Returning cached result")
            return {"analysis": cached_result}
        
        if not YOUR_API_KEY:
            error_response = {
                "analysis": "Error: NewsAPI key is not configured on the server.",
                "keyNews": "Please check backend configuration.",
                "forecastData": [],
                "investmentAdvice": {
                    "entryPoint": None,
                    "expectedReturn": None,
                    "stopLoss": None
                },
                "recommendedStocks": []
            }
            return {"analysis": json.dumps(error_response)}
        
        # --- Run the full analysis synchronously ---
        print(f"Fetching fundamentals for {ticker}...")
        fundamentals, summary = get_fundamentals(ticker)

        if not fundamentals:
            print(
                f"Fundamentals unavailable for {ticker}; "
                "continuing with transparent fallback data."
            )
            fundamentals, summary = build_unavailable_fundamentals(ticker)
        
        print(f"Fetching news for {ticker}...")
        news = get_news(ticker, YOUR_API_KEY)
        
        print(f"Processing and embedding data...")
        vector_index, text_chunks, metadata = process_and_embed(news, summary, ticker)
        
        query = f"Recent news, developments, and user context for {ticker}"
        relevant_chunks, citations = retrieve_relevant_chunks(
            query, vector_index, text_chunks, metadata
        )
        
        print(f"Building AI prompt...")
        user_prompt = build_prompt(
            ticker=request.ticker,
            fundamentals=fundamentals,
            relevant_chunks=relevant_chunks,
            citations=citations
        )
        
        print(f"Calling AI model...")
        ai_json_string = get_analysis(user_prompt)
        
        # --- Get Rule-Based Recommendations ---
        print(f"Running rule-based stock recommender...")
        effective_financial_condition = set(request.financialCondition)

        if request.hasOtherFinancialCondition:
            effective_financial_condition.update(
                extract_financial_conditions(
                    request.financialConditionOther
                )
            )
        recommendations_list = recommend_stocks(
            trading_history=request.tradingPreferences,
            financial_condition=list(effective_financial_condition),
            expected_return=request.expectedReturn,
            risk_tolerance=request.riskTolerance,
            preferred_sectors=request.preferredSectors,
            investment_style=request.investmentStyle,
            holding_horizon=request.holdingHorizon
        )
        
        # --- Combine Results ---
        print(f"Combining results...")
        ai_data = json.loads(ai_json_string)
        ai_data['recommendedStocks'] = recommendations_list
        
        if citations:
            citation_header = "\n\n--- Sources ---\n"
            citation_list = "\n".join(citations)
            ai_data['analysis'] += citation_header + citation_list
        
        final_json_string = json.dumps(ai_data)
        
        # --- Cache the result (with user preferences) ---
        set_cached_analysis(ticker, final_json_string, request)
        
        print(f"=== Analysis Complete ===")
        return {"analysis": final_json_string}
        
    except Exception as e:
        print(f"Error in analyze_direct: {e}")
        import traceback
        traceback.print_exc()
        error_response = {
            "analysis": f"Error: An unexpected error occurred: {str(e)}",
            "keyNews": "Please try again later or contact support.",
            "forecastData": [],
            "investmentAdvice": {
                "entryPoint": None,
                "expectedReturn": None,
                "stopLoss": None
            },
            "recommendedStocks": []
        }
        return {"analysis": json.dumps(error_response)}

@app.post("/api/start-analysis", response_model=AnalysisResponse)
async def start_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """
    This endpoint creates a new job, starts it in the background,
    and *immediately* returns a job ID to the frontend.
    """
    job_id = str(uuid.uuid4())
    print(f"--- Received new request. Creating Job ID: {job_id} ---")
    
    # Create the job in the DB
    create_job(job_id)
    
    # Add the long-running task to the background
    background_tasks.add_task(run_full_analysis_task, job_id, request)
    
    # Return the Job ID to the frontend
    return {"jobId": job_id}

@app.get("/api/status/{job_id}", response_model=StatusResponse)
async def get_analysis_status(job_id: str):
    """
    This endpoint is polled by the frontend every few seconds
    to check if the job is "pending", "complete", or "failed".
    """
    print(f"--- Received status check for Job ID: {job_id} ---")
    status = get_job_status(job_id)
    return status

# --- 7. Run the Server ---
if __name__ == "__main__":
    print("--- Starting FastAPI server ---")
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0") 
    print(f"--- Running on http://{host}:{port} ---")
    uvicorn.run("api_server:app", host=host, port=port, reload=False)
