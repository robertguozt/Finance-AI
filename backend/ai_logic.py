import sys
import os
import json
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

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
        genai.configure(api_key=GEMINI_API_KEY)
        
        # List of models to try in order of preference
        # We prioritize models that are generally more permissive or stable
        model_names = [
            'models/gemini-2.5-flash',
            'models/gemini-2.5-pro',
            'models/gemini-2.0-pro-exp',
            'models/gemini-2.0-flash-lite'
        ]
        
        for name in model_names:
            try:
                print(f"Attempting to load model: {name}...")
                model = genai.GenerativeModel(name)
                # Test the model
                model.generate_content("Test") 
                print(f"Success! Using model: {name}")
                return True
            except Exception as e:
                print(f"Failed to load {name}: {e}")
                continue
        
        print("Error: Could not load ANY valid Gemini model.")
        return False
        
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        return False

# Initialize on load
configure_genai()

# --- 1. RAG Retrieval ---
def retrieve_relevant_chunks(query, vector_index, text_chunks, metadata, k=5):
    if vector_index is None:
        print("Vector index is not available.")
        return [], []
    
    try:
        from data_fetcher import embedding_model
        if embedding_model is None:
            print("Error: Embedding model not loaded from data_fetcher.")
            return [], []
        query_embedding = embedding_model.encode([query])
    except Exception as e:
        print(f"Error encoding query: {e}")
        return [], []

    try:
        import numpy as np
        query_vector = np.array(query_embedding).astype('float32')
        D, I = vector_index.search(query_vector, k)
    except Exception as e:
        print(f"Error searching FAISS index: {e}")
        return [], []

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
**CRITICAL RULES:**
1.  **START DATE:** The forecast MUST start from next month ({next_months[0]}).
2.  **DURATION:** Provide exactly 12 data points for these months: {next_months_str}.
3.  **NO HISTORY:** Do NOT include historical data. Only include future predictions.
4.  **TREND:** Ensure the price curve is realistic based on the provided news and fundamentals.
5.  Output must be a SINGLE JSON object.
2.  Specific investment advice (entry point, return %, stop loss).

**CRITICAL RULES:**
1.  **START DATE:** The forecast MUST start from next month ({next_months[0]}).
2.  **DURATION:** Provide exactly 12 data points for these months: {next_months_str}.
3.  **NO HISTORY:** Do NOT include historical data. Only include future predictions.
4.  **TREND:** Ensure the price curve is realistic based on the provided news and fundamentals.
5.  **FULL CURVE:** Ensure you provide a price point for EVERY month listed above
6.  **INVESTMENT ADVICE:** You MUST provide REALISTIC and attainable values for 'entry point', 'expected return' and 'stop loss'. Make sure they are attainable.
7.  Output must be a SINGLE JSON object. Do not include markdown formatting. 

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "analysis": "...",
  "keyNews": "...",
  "forecastData": [
    {{"month": "{next_months[0]}", "price": 150.00, "type": "forecast"}},
    {{"month": "{next_months[1]}", "price": 155.50, "type": "forecast"}},
    ... (Continue for all 12 months) ...
    {{"month": "{next_months[11]}", "price": 205.00, "type": "forecast"}}
  ],
  "investmentAdvice": {{
    "entryPoint": 150.00,
    "expectedReturn": 15.5,
    "stopLoss": 140.00
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
    global model
    if not model:
        if not configure_genai():
            return json.dumps({
                "analysis": "Error: AI Model could not be loaded. Check API keys.",
                "keyNews": "System Error",
                "forecastData": [],
                "investmentAdvice": {"entryPoint": 0, "expectedReturn": 0, "stopLoss": 0}
            })
        
    try:
        print("Generating analysis with Gemini API...")
        
        # --- NEW: Explicitly Disable ALL Safety Filters ---
        # This is the key fix for "finish_reason 2"
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        generation_config = {"response_mime_type": "application/json"}
        
        response = model.generate_content(
            prompt_text,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        
        # Safety Check: Even with settings off, check if it was blocked
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"Request blocked! Reason: {response.prompt_feedback.block_reason}")
            return json.dumps({
                "analysis": f"Analysis blocked by safety filter: {response.prompt_feedback.block_reason}. Please try a different stock.",
                "keyNews": "Blocked",
                "forecastData": [],
                "investmentAdvice": {"entryPoint": 0, "expectedReturn": 0, "stopLoss": 0}
            })

        return response.text
        
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return json.dumps({
            "analysis": f"Error: {str(e)}",
            "keyNews": "API call failed",
            "forecastData": [],
            "investmentAdvice": {"entryPoint": 0, "expectedReturn": 0, "stopLoss": 0}
        })


