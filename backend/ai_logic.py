import sys
import os
import json
import google.generativeai as genai

# --- !! IMPORTANT !! ---
# Load API key from environment variable (set in Render)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Configure the Gemini API ---
model = None

def configure_genai():
    global model
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set.")
        return False

    try:
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-pro')
        else:
            print("Warning: GEMINI_API_KEY is not set in environment.")
        
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")

# --- 1. RAG Retrieval ---
def retrieve_relevant_chunks(query, vector_index, text_chunks, metadata, k=5):
    """
    Searches the FAISS index for the top-k most relevant text chunks.
    """
    if vector_index is None:
        print("Vector index is not available.")
        return [], []
    
    # 1. Embed the query
    try:
        from data_fetcher import embedding_model
        if embedding_model is None:
            print("Error: Embedding model not loaded from data_fetcher.")
            return [], []
        query_embedding = embedding_model.encode([query])
    except Exception as e:
        print(f"Error encoding query: {e}")
        return [], []

    # 2. Search the FAISS index
    try:
        # FAISS expects float32
        import numpy as np
        query_vector = np.array(query_embedding).astype('float32')
        D, I = vector_index.search(query_vector, k)
    except Exception as e:
        print(f"Error searching FAISS index: {e}")
        return [], []

    # 3. Format the results
    relevant_chunks = []
    citations = set()
    
    for i, chunk_index in enumerate(I[0]):
        if chunk_index < 0 or chunk_index >= len(text_chunks):
            continue
            
        chunk = text_chunks[chunk_index]
        meta = metadata[chunk_index]
        
        source_name = meta.get('source', 'Unknown Source')
        source_url = meta.get('url', '#')
        source_date = meta.get('date', 'N/A')
        
        citation_str = f"[{source_name}]({source_url}) - {source_date}"
        
        relevant_chunks.append(f"Source: {citation_str}\nContent: {chunk}")
        citations.add(citation_str)

    return relevant_chunks, list(citations)

# --- 2. Prompt Engineering ---
def build_prompt(ticker, fundamentals, relevant_chunks, citations, user_profile):
    """
    Builds the final prompt string to send to the LLM.
    """
    system_prompt = """
You are an expert financial analyst. Your task is to provide a comprehensive analysis for a user.

**USER PROFILE:**
- **Financial Condition:** {user_profile.financialCondition}
- **Risk Tolerance:** {user_profile.riskTolerance}
- **Expected Return %:** {user_profile.expectedReturn}%
- **Trading Preferences:** {user_profile.tradingPreferences}

**YOUR TASK:**
Analyze the provided stock data and generate a report with:
1.  A 12-month price forecast (logical estimation based on data).
2.  Specific investment advice (entry point, return %, stop loss).

**RULES:**
1.  Base your analysis ONLY on the provided data.
2.  The output must be a SINGLE JSON object. Do not include markdown formatting.

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "analysis": "...",
  "keyNews": "...",
  "forecastData": [
    {{"month": "Jan", "price": 150, "type": "history"}},
    {{"month": "Feb", "price": 155, "type": "history"}},
    {{"month": "Mar", "price": 160, "type": "history"}},
    {{"month": "Apr", "price": 165, "type": "history"}},
    {{"month": "May", "price": 170, "type": "history"}},
    {{"month": "Jun", "price": 175, "type": "history"}},
    {{"month": "Jul", "price": 180, "type": "history"}},
    {{"month": "Aug", "price": 185, "type": "history"}},
    {{"month": "Sep", "price": 190, "type": "forecast"}},
    {{"month": "Oct", "price": 195, "type": "forecast"}},
    {{"month": "Nov", "price": 200, "type": "forecast"}},
    {{"month": "Dec", "price": 205, "type": "forecast"}}
  ],
  "investmentAdvice": {{
    "entryPoint": 175.50,
    "expectedReturn": 18.0,
    "stopLoss": 168.00
  }}
}}
"""
    fundamentals_str = "\n".join(f"- {key}: {value}" for key, value in fundamentals.items())
    
    if relevant_chunks:
        news_str = "\n\n---\n\n".join(relevant_chunks)
    else:
        news_str = "No recent news articles were found or provided."
        
    formatted_system_prompt = system_prompt.format(user_profile=user_profile)
    
    user_prompt_data = f"""
--- START OF DATA ---
**Stock Ticker:** {ticker}
**Financial Indicators:**
{fundamentals_str}
**Recent News Articles:**
{news_str}
--- END OF DATA ---
"""
    return formatted_system_prompt + user_prompt_data

# --- 3. AI Generation ---
def get_analysis(prompt_text):
    """
    Sends the prompt to the Gemini API and gets the response.
    """
    global model
    if not model:
        # Try to re-init if model is missing
        if not configure_genai():
            return json.dumps({
                "analysis": "Error: AI Model could not be loaded. Check API keys.",
                "keyNews": "System Error",
                "forecastData": [],
                "investmentAdvice": {"entryPoint": 0, "expectedReturn": 0, "stopLoss": 0}
            })
        
    try:
        print("Generating analysis with Gemini API...")
        generation_config = {"response_mime_type": "application/json"}
        
        response = model.generate_content(
            prompt_text,
            generation_config=generation_config
        )
        return response.text
        
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return json.dumps({
            "analysis": f"Error: Could not get analysis from API. Details: {e}",
            "keyNews": "API call failed",
            "forecastData": [],
            "investmentAdvice": {"entryPoint": 0, "expectedReturn": 0, "stopLoss": 0}
        })

