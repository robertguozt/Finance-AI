import uvicorn
import sqlite3
import time
import sys
import os
import json
import uuid # For creating unique job IDs
import hashlib
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager

# --- Import from our other files ---
try:
    from data_fetcher import (
        get_fundamentals, 
        get_news, 
        process_and_embed, 
        load_embedding_model, 
        download_nltk_data  
    )
    from ai_logic import retrieve_relevant_chunks, build_prompt, get_analysis
    from stock_recommender import recommend_stocks
except ImportError as e:
    print(f"Error: Could not import from helper files: {e}")
    sys.exit(1)

# --- Load API keys ---
YOUR_API_KEY = os.environ.get("YOUR_API_KEY")
if not YOUR_API_KEY:
    print("Error: YOUR_API_KEY (for NewsAPI) is not set as an environment variable.")

# --- 1. Define API Models ---
class AnalysisRequest(BaseModel):
    ticker: str
    financialCondition: List[str]
    expectedReturn: int
    riskTolerance: str
    tradingPreferences: str

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
    print("--- Initializing database ---")
    init_db()
    print("--- Downloading NLTK data (if needed) ---")
    download_nltk_data()
    print("--- Pre-loading embedding model ---")
    load_embedding_model()
    print("--- Startup complete. Server is ready. ---")
    yield
    print("--- Server shutting down... ---")

# --- 3. Initialize FastAPI App ---
app = FastAPI(lifespan=lifespan) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- 4. Caching & Database Logic (UPDATED) ---
DB_NAME = os.environ.get("DB_NAME", "analysis_cache.db")
CACHE_DURATION = 3600  # 1 hour

def init_db():
    db_dir = os.path.dirname(DB_NAME)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Cache with composite key (ticker + user preferences)
    # Using cache_key as PRIMARY KEY to support user-specific caching
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache
        (cache_key TEXT PRIMARY KEY,
         ticker TEXT,
         analysis TEXT,
         timestamp REAL)
    ''')
    
    # Create index on ticker for faster lookups (optional, for cleanup purposes)
    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_ticker ON cache(ticker)
    ''')
    
    # --- NEW: Table to track job status ---
    c.execute('''
        CREATE TABLE IF NOT EXISTS jobs
        (job_id TEXT PRIMARY KEY,
         status TEXT,
         result TEXT,
         timestamp REAL)
    ''')
    conn.commit()
    conn.close()

# --- Job Status Functions ---
def create_job(job_id: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO jobs (job_id, status, result, timestamp) VALUES (?, ?, ?, ?)",
                  (job_id, "pending", None, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error creating job: {e}")

def update_job_complete(job_id: str, result: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE jobs SET status = ?, result = ? WHERE job_id = ?",
                  ("complete", result, job_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating job to complete: {e}")

def update_job_failed(job_id: str, error_message: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE jobs SET status = ?, result = ? WHERE job_id = ?",
                  ("failed", error_message, job_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating job to failed: {e}")

def get_job_status(job_id: str):
    try:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT status, result FROM jobs WHERE job_id = ?", (job_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return {"status": result[0], "result": result[1]}
    except Exception as e:
        print(f"Error getting job status: {e}")
    return {"status": "not_found", "result": None}

# --- Cache Key Generation ---
def generate_cache_key(ticker: str, trading_preferences: str, risk_tolerance: str, 
                       expected_return: int, financial_condition: List[str]) -> str:
    """
    Generate a unique cache key based on ticker and user preferences.
    This ensures recommendations are cached per user profile, not just per ticker.
    """
    # Create a string representation of all user preferences
    prefs_string = f"{ticker}|{trading_preferences}|{risk_tolerance}|{expected_return}|{','.join(sorted(financial_condition))}"
    # Generate a hash for the cache key
    cache_key = hashlib.md5(prefs_string.encode('utf-8')).hexdigest()
    return f"{ticker}_{cache_key}"

# --- Caching Functions (Updated to include user preferences) ---
def get_cached_analysis(ticker: str, trading_preferences: str, risk_tolerance: str,
                        expected_return: int, financial_condition: List[str]):
    """
    Get cached analysis for a specific ticker and user profile combination.
    """
    try:
        cache_key = generate_cache_key(ticker, trading_preferences, risk_tolerance, 
                                      expected_return, financial_condition)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT analysis, timestamp FROM cache WHERE cache_key = ?", (cache_key,))
        result = c.fetchone()
        conn.close()
        if result:
            analysis, timestamp = result
            if (time.time() - timestamp) < CACHE_DURATION:
                print(f"Cache hit for {ticker} with user preferences")
                return analysis
            else:
                print(f"Cache expired for {ticker} with user preferences")
    except sqlite3.OperationalError:
        print(f"Warning: Could not read from cache database at {DB_NAME}")
    except Exception as e:
        print(f"Error reading cache: {e}")
    return None

def set_cached_analysis(ticker: str, analysis: str, trading_preferences: str, 
                        risk_tolerance: str, expected_return: int, financial_condition: List[str]):
    """
    Cache analysis for a specific ticker and user profile combination.
    """
    try:
        cache_key = generate_cache_key(ticker, trading_preferences, risk_tolerance, 
                                      expected_return, financial_condition)
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("REPLACE INTO cache (cache_key, ticker, analysis, timestamp) VALUES (?, ?, ?, ?)",
                  (cache_key, ticker, analysis, time.time()))
        conn.commit()
        conn.close()
        print(f"Cached analysis for {ticker} with user preferences")
    except sqlite3.OperationalError:
        print(f"Warning: Could not write to cache database at {DB_NAME}")
    except Exception as e:
        print(f"Error writing cache: {e}")

# --- 5. The Long-Running Analysis Task (NEW) ---
def run_full_analysis_task(job_id: str, request: AnalysisRequest):
    """
    This is the long-running function that runs in the background.
    """
    try:
        ticker = request.ticker.upper()
        print(f"--- [Background Job: {job_id}] Starting analysis for {ticker} ---")
        
        # 1. Check cache first (with user preferences)
        cached_result = get_cached_analysis(
            ticker=ticker,
            trading_preferences=request.tradingPreferences,
            risk_tolerance=request.riskTolerance,
            expected_return=request.expectedReturn,
            financial_condition=request.financialCondition
        )
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
            raise Exception(f"Could not fetch fundamental data for ticker: {ticker}")

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
            citations=citations,
            user_profile=request  
        )
        
        ai_json_string = get_analysis(user_prompt)
        
        # --- TASK 2: Get Rule-Based Recommendations (THE SLOW PART) ---
        print(f"[Background Job: {job_id}] Running rule-based stock recommender...")
        recommendations_list = recommend_stocks(
            trading_history=request.tradingPreferences,
            financial_condition=request.financialCondition,
            expected_return=request.expectedReturn,
            risk_tolerance=request.riskTolerance
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
        set_cached_analysis(
            ticker=ticker,
            analysis=final_json_string,
            trading_preferences=request.tradingPreferences,
            risk_tolerance=request.riskTolerance,
            expected_return=request.expectedReturn,
            financial_condition=request.financialCondition
        )
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
        cached_result = get_cached_analysis(
            ticker=ticker,
            trading_preferences=request.tradingPreferences,
            risk_tolerance=request.riskTolerance,
            expected_return=request.expectedReturn,
            financial_condition=request.financialCondition
        )
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
            error_response = {
                "analysis": f"Error: Could not fetch fundamental data for ticker {ticker}.",
                "keyNews": "Please check if the ticker symbol is valid.",
                "forecastData": [],
                "investmentAdvice": {
                    "entryPoint": None,
                    "expectedReturn": None,
                    "stopLoss": None
                },
                "recommendedStocks": []
            }
            return {"analysis": json.dumps(error_response)}
        
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
            citations=citations,
            user_profile=request  
        )
        
        print(f"Calling AI model...")
        ai_json_string = get_analysis(user_prompt)
        
        # --- Get Rule-Based Recommendations ---
        print(f"Running rule-based stock recommender...")
        recommendations_list = recommend_stocks(
            trading_history=request.tradingPreferences,
            financial_condition=request.financialCondition,
            expected_return=request.expectedReturn,
            risk_tolerance=request.riskTolerance
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
        set_cached_analysis(
            ticker=ticker,
            analysis=final_json_string,
            trading_preferences=request.tradingPreferences,
            risk_tolerance=request.riskTolerance,
            expected_return=request.expectedReturn,
            financial_condition=request.financialCondition
        )
        
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
