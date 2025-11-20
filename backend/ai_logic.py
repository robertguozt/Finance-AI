import sys
import os
import json

# --- Import AI/LLM libraries ---
try:
    import google.generativeai as genai
except ImportError:
    print("Error: The 'google-generativeai' library is not installed.")
    print("Please install it using: pip install google-generativeai")
    sys.exit(1)

# --- !! IMPORTANT !! ---
# Load API key from environment variable (set in Render)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize model as None initially
model = None

# --- Configure the Gemini API ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        try:
            model = genai.GenerativeModel("models/gemini-2.5-pro")
            print("Successfully initialized Gemini model: gemini-pro")
        except Exception as model_error:
            print(f"Error initializing Gemini model 'gemini-pro': {model_error}")
            print("Trying alternative model names...")
            # Try alternative model names
            model_names = ['gemini-1.5-flash', 'models/gemini-pro', 'models/gemini-1.5-flash']
            model = None
            for model_name in model_names:
                try:
                    model = genai.GenerativeModel(model_name)
                    print(f"Successfully initialized Gemini model: {model_name}")
                    break
                except Exception as e:
                    print(f"Failed to initialize {model_name}: {e}")
                    continue
            
            if model is None:
                print("ERROR: Could not initialize any Gemini model. Please check your API key and model availability.")
    else:
        print("Warning: GEMINI_API_KEY is not set in environment.")
        
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    model = None

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
        D, I = vector_index.search(query_embedding, k)
    except Exception as e:
        print(f"Error searching FAISS index: {e}")
        return [], []

    # 3. Format the results
    relevant_chunks = []
    citations = set()  # Use a set to avoid duplicate citations
    
    for i, chunk_index in enumerate(I[0]):
        if chunk_index < 0 or chunk_index >= len(text_chunks):
            continue
            
        chunk = text_chunks[chunk_index]
        meta = metadata[chunk_index]
        
        # Use .get() to provide default values
        source_name = meta.get('source', 'Unknown Source')
        source_url = meta.get('url', '#')
        source_date = meta.get('date', 'N/A')
        
        citation_str = f"[{source_name}]({source_url}) - {source_date}"
        
        relevant_chunks.append(f"Source: {citation_str}\nContent: {chunk}")
        citations.add(citation_str)

    return relevant_chunks, list(citations)

# --- 2. Prompt Engineering (UPDATED) ---

def build_prompt(ticker, fundamentals, relevant_chunks, citations, user_profile):
    """
    Builds the final prompt string to send to the LLM.
    """
    
    # --- System Prompt: The AI's "Instructions" ---
    system_prompt = """
You are an expert financial analyst and portfolio manager. Your task is to provide a comprehensive, data-driven analysis for a *specific user* based on their profile and the provided data.

**USER PROFILE:**
- **Financial Condition:** {user_profile_financialCondition}
- **Risk Tolerance:** {user_profile_riskTolerance}
- **Expected Return %:** {user_profile_expectedReturn}%
- **Trading Preferences:** {user_profile_tradingPreferences}

**YOUR TASK:**
Analyze the provided stock data and generate a personalized report. The user is asking for:
1.  A 12-month price forecast with historical and forecasted months.
2.  Specific investment advice with numerical values: entry point (dollar price), expected return (percentage), and stop loss (dollar price).

**RULES:**
1.  Do NOT use any external knowledge. Base your *entire* analysis on the provided data.
2.  **CRITICAL:** You *must* generate the 12-month forecast and investment advice, even if the data is limited. Use the fundamentals and news sentiment to make logical estimations.
3.  The user's profile is the most important context. All advice *must* be tailored to their risk tolerance.
4.  The output must be formatted *exactly* as a single JSON object. Do not include markdown formatting (```json) or any text outside the curly braces.

**REQUIRED JSON OUTPUT FORMAT:**
{{
  "analysis": "Detailed analysis text here...",
  "keyNews": "Summary of key news here...",
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
    "entryPoint": 150.00,
    "expectedReturn": 15.5,
    "stopLoss": 140.00
  }}

**IMPORTANT NOTES:**
- "entryPoint" must be a number (the recommended buy price in dollars)
- "expectedReturn" must be a number (the expected return percentage, e.g., 15.5 means 15.5%)
- "stopLoss" must be a number (the recommended stop loss price in dollars)
- "forecastData" must include at least 8 months marked as "history" and at least 4 months marked as "forecast"
- Use abbreviated month names (Jan, Feb, Mar, etc.)
}}
"""
    # Format the system prompt with user profile data
    formatted_system_prompt = system_prompt.format(
        user_profile_financialCondition=", ".join(user_profile.financialCondition),
        user_profile_riskTolerance=user_profile.riskTolerance,
        user_profile_expectedReturn=user_profile.expectedReturn,
        user_profile_tradingPreferences=user_profile.tradingPreferences
    )
    
    # Format the fundamentals data
    fundamentals_str = "\n".join(f"- {key}: {value}" for key, value in fundamentals.items())
    
    # Format the news chunks
    if relevant_chunks:
        news_str = "\n\n---\n\n".join(relevant_chunks)
    else:
        news_str = "No recent news articles were found or provided."
        
    # Combine it all
    user_prompt_data = f"""
--- START OF DATA ---

**Stock Ticker:**
{ticker}

**Financial Indicators:**
{fundamentals_str}

**Recent News Articles:**
{news_str}

--- END OF DATA ---

Please provide your analysis based *only* on the data above, following all rules and the required JSON format.
"""
    
    return formatted_system_prompt + user_prompt_data

# --- 3. AI Generation (UPDATED) ---

def get_analysis(prompt_text):
    """
    Sends the prompt to the Gemini API and gets the response.
    """
    if not GEMINI_API_KEY:
        return json.dumps({
            "analysis": "Error: Gemini API key is not configured.",
            "keyNews": "Please check backend configuration.",
            "forecastData": [],
            "investmentAdvice": {
                "entryPoint": None,
                "expectedReturn": None,
                "stopLoss": None
            }
        })
        
    if model is None:
        return json.dumps({
            "analysis": "Error: Gemini model not initialized.",
            "keyNews": "Please check backend configuration.",
            "forecastData": [],
            "investmentAdvice": {
                "entryPoint": None,
                "expectedReturn": None,
                "stopLoss": None
            }
        })
        
    try:
        print("Generating analysis with Gemini API...")
        
        # Configure for JSON response
        generation_config = {
            "temperature": 0.1,  # Lower temperature for more consistent results
            "max_output_tokens": 2048,
        }
        
        response = model.generate_content(
            prompt_text,
            generation_config=generation_config
        )
        
        # Try to parse the response as JSON
        try:
            # Clean the response text
            cleaned_response = response.text.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            # Parse to validate it's proper JSON
            parsed_json = json.loads(cleaned_response)
            return cleaned_response
            
        except json.JSONDecodeError:
            # If response isn't valid JSON, create a fallback response
            print("Warning: Gemini response was not valid JSON, creating fallback")
            fallback_response = {
                "analysis": f"AI Analysis: {response.text[:500]}...",
                "keyNews": "News analysis available in main analysis",
                "forecastData": [
                    {"month": "Jan", "price": 150, "type": "forecast"},
                    {"month": "Feb", "price": 155, "type": "forecast"},
                    {"month": "Mar", "price": 160, "type": "forecast"}
                ],
                "investmentAdvice": {
                    "entryPoint": None,
                    "expectedReturn": None,
                    "stopLoss": None
                }
            }
            return json.dumps(fallback_response)
    except Exception as e:
        error_msg = str(e)
        print(f"Error during Gemini API call: {error_msg}")
        
        # Check for specific error types
        if "API key" in error_msg or "authentication" in error_msg.lower():
            detailed_error = "AI Model could not be loaded. Check API keys. Please verify your GEMINI_API_KEY is set correctly in the environment variables."
        elif "404" in error_msg or "not found" in error_msg.lower():
            detailed_error = f"AI Model error: Model not found. Details: {error_msg}"
        elif "403" in error_msg or "permission" in error_msg.lower():
            detailed_error = f"AI Model error: Permission denied. Please check your API key permissions. Details: {error_msg}"
        else:
            detailed_error = f"Error: Could not get analysis from API. Details: {error_msg}"
            
        error_response = {
            "analysis": detailed_error,
            "keyNews": "API call failed - please check backend logs for details",
            "forecastData": [],
            "investmentAdvice": {
                "entryPoint": None,
                "expectedReturn": None,
                "stopLoss": None
            }
        }
        return json.dumps(error_response)
    


