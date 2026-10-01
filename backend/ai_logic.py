import sys
import os
import json
import datetime 
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, RequestOptions

# --- Load API key ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Configure Gemini ---
model = None

def configure_genai():
    global model

    if model is not None:
        return True

    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not set.")
        return False

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        model = genai.GenerativeModel("models/gemini-3.5-flash-lite")
        print("Gemini model configured: models/gemini-3.5-flash-lite")
        return True

    except Exception as error:
        model = None
        print(f"Error configuring Gemini API: {error}")
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
def build_prompt(ticker, fundamentals, relevant_chunks, citations):
    
    # 1. Calculate Dates
    current_date = datetime.datetime.now()
    current_month_str = current_date.strftime("%B %Y")
    
    next_months = []
    for i in range(1, 13):
        future_date = current_date + datetime.timedelta(days=30*i)
        next_months.append(future_date.strftime("%b"))

    # Build the required month structure without suggesting a price trend.
    forecast_rows = []

    for month in next_months:
        row = f'    {{ "month": "{month}", "price": null, "type": "forecast" }}'
        forecast_rows.append(row)

    forecast_data_str = ",\n".join(forecast_rows)
    
    # 3. Prepare Data Strings
    fundamentals_str = "\n".join(f"- {k}: {v}" for k, v in fundamentals.items())
    news_str = "\n\n---\n\n".join(relevant_chunks) if relevant_chunks else "No recent news."
    
    # 4. Construct the COMPLETE Prompt
    # We use one single f-string to avoid variable confusion
    final_prompt = f"""
You are an expert financial analyst. Your task is to provide a comprehensive analysis.

**CURRENT DATE:** {current_month_str}

**DATA-QUALITY RULE:**
- If any fundamental field is marked as unavailable, do not invent or estimate it.
- Clearly state that the data source is temporarily unavailable.

**YOUR TASK:**
1. Generate a **12-month price forecast** starting from NEXT MONTH ({next_months[0]}).
2. Provide **Specific Investment Advice**.

**CRITICAL RULES:**
1. Base the analysis ONLY on the provided data.
2. Provide exactly 12 forecast data points for the required future months.
3. Replace every null price placeholder with a positive JSON number.
4. Generate the forecast independently of all user preferences,
   suitability settings, and recommendation criteria.
5. Monthly prices may rise or fall when supported by the available evidence.
6. Avoid mechanically linear or automatically monotonic price sequences.
7. Do not add artificial price changes merely to make the chart look realistic.
8. Output a single valid JSON object.
9. Replace the investmentAdvice null placeholders with numeric values.
10. entryPoint and stopLoss must be positive numbers.
11. expectedReturn must be derived from the supplied current price and
    the final forecast price; it may be positive or negative.
12. The investmentAdvice values must describe the analyzed stock only
    and must not represent personalized financial advice.

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "analysis": "Detailed market analysis text...",
  "keyNews": "Summary of key news...",
  "forecastData": [
{forecast_data_str}
  ],
  "investmentAdvice": {{
    "entryPoint": null,
    "expectedReturn": null,
    "stopLoss": null
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
            safety_settings=safety_settings,
            request_options=RequestOptions(timeout=180)
        )
        
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            return json.dumps({"analysis": "Analysis blocked by safety filter.", "forecastData": [], "investmentAdvice": {}})

        return response.text

    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        raise RuntimeError("Gemini request failed") from e

