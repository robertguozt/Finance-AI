import sys
import os
import json
import datetime 
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# --- Load API key ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Configure Gemini ---
model = None

def configure_genai():
    global model
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set.")
        return False

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model_names = ['models/gemini-2.5-flash', 'models/gemini-2.5-pro', 'models/gemini-2.0-pro', 'models/gemini-pro']
        for name in model_names:
            try:
                print(f"Attempting to load model: {name}...")
                model = genai.GenerativeModel(name)
                model.generate_content("Test") 
                print(f"Success! Using model: {name}")
                return True
            except Exception as e:
                print(f"Failed to load {name}: {e}")
                continue
        return False
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        return False

configure_genai()

# --- 1. RAG Retrieval ---
def retrieve_relevant_chunks(query, vector_index, text_chunks, metadata, k=5):
    if vector_index is None: return [], []
    try:
        from data_fetcher import embedding_model
        if embedding_model is None: return [], []
        query_embedding = embedding_model.encode([query])
        import numpy as np
        query_vector = np.array(query_embedding).astype('float32')
        D, I = vector_index.search(query_vector, k)
    except Exception:
        return [], []

    relevant_chunks = []
    citations = set()
    for i, chunk_index in enumerate(I[0]):
        if chunk_index < 0 or chunk_index >= len(text_chunks): continue
        chunk = text_chunks[chunk_index]
        meta = metadata[chunk_index]
        source = meta.get('source', 'Unknown')
        url = meta.get('url', '#')
        date = meta.get('date', 'N/A')
        citation = f"[{source}]({url}) - {date}"
        relevant_chunks.append(f"Source: {citation}\nContent: {chunk}")
        citations.add(citation)

    return relevant_chunks, list(citations)

# --- 2. Prompt Engineering ---
def build_prompt(ticker, fundamentals, relevant_chunks, citations, user_profile):
    
    # 1. Calculate Dates
    current_date = datetime.datetime.now()
    current_month_str = current_date.strftime("%B %Y")
    
    next_months = []
    for i in range(1, 13):
        future_date = current_date + datetime.timedelta(days=30*i)
        next_months.append(future_date.strftime("%b")) 
    
    # 2. Build Forecast Example String (Manual Construction)
    forecast_rows = []
    start_price = 150.0
    for i, month in enumerate(next_months):
        price = start_price + (i * 2.5)
        # Note: double curly braces {{ }} are NOT needed here because this is a standard string, not an f-string
        row = f'    {{ "month": "{month}", "price": {price:.2f}, "type": "forecast" }}'
        forecast_rows.append(row)
    
    forecast_data_str = ",\n".join(forecast_rows)
    
    # 3. Prepare Data Strings
    financial_condition_str = ", ".join(user_profile.financialCondition)
    fundamentals_str = "\n".join(f"- {k}: {v}" for k, v in fundamentals.items())
    news_str = "\n\n---\n\n".join(relevant_chunks) if relevant_chunks else "No recent news."
    
    # 4. Construct the COMPLETE Prompt
    # We use one single f-string to avoid variable confusion
    final_prompt = f"""
You are an expert financial analyst. Your task is to provide a comprehensive analysis.

**USER PROFILE:**
- Financial Condition: {financial_condition_str}
- Risk Tolerance: {user_profile.riskTolerance}
- Expected Return: {user_profile.expectedReturn}%
- Preferences: {user_profile.tradingPreferences}

**CURRENT DATE:** {current_month_str}

**YOUR TASK:**
1. Generate a **12-month price forecast** starting from NEXT MONTH ({next_months[0]}).
2. Provide **Specific Investment Advice**.

**CRITICAL RULES:**
1. Base analysis ONLY on provided data.
2. **Forecast Data:** Provide exactly 12 data points for the future months. NO historical data.
3. Output a SINGLE JSON object.

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "analysis": "Detailed market analysis text...",
  "keyNews": "Summary of key news...",
  "forecastData": [
{forecast_data_str}
  ],
  "investmentAdvice": {{
    "entryPoint": 150.00,
    "expectedReturn": 15.5,
    "stopLoss": 140.00
  }}
}}

--- START OF DATA ---
**Stock Ticker:** {ticker}
**Financial Indicators:**
{fundamentals_str}
**Recent News Articles:**
{news_str}
--- END OF DATA ---
"""
    return final_prompt

# --- 3. AI Generation ---
def get_analysis(prompt_text):
    global model
    if not model:
        if not configure_genai():
             return json.dumps({"analysis": "Error: AI Model not loaded.", "forecastData": [], "investmentAdvice": {}})
        
    try:
        print("Generating analysis with Gemini API...")
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
        
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            return json.dumps({"analysis": "Analysis blocked by safety filter.", "forecastData": [], "investmentAdvice": {}})

        return response.text
        
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return json.dumps({"analysis": f"Error: {str(e)}", "forecastData": [], "investmentAdvice": {}})

