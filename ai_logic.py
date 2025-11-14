import sys
import os

# --- Import AI/LLM libraries ---
try:
    import google.generativeai as genai
except ImportError:
    print("Error: The 'google-generativeai' library is not installed.")
    print("Please install it using: pip install google-generativeai")
    sys.exit(1)

# --- !! IMPORTANT !! ---
# PASTE YOUR Google Gemini API KEY HERE:
GEMINI_API_KEY = "AIzaSyA-PrHFsmnaoMKYrVjUnVabYc9qms4qVvo" # Get one from Google AI Studio

# --- Configure the Gemini API ---
try:
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    else:
        print("Error: GEMINI_API_KEY is not set in ai_logic.py. Please add it.")
        sys.exit(1)
        
    # NEW, STABLE LINE:
    model = genai.GenerativeModel('gemini-2.5-pro')
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    print("Please ensure your API key is correct and valid.")
    sys.exit(1)

# --- 1. RAG Retrieval ---

def retrieve_relevant_chunks(query, vector_index, text_chunks, metadata, k=5):
    """
    Searches the FAISS index for the top-k most relevant text chunks.
    """
    if vector_index is None:
        print("Vector index is not available.")
        return [], []
    
    # 1. Embed the query
    # We get the model from the 'data_fetcher' module's global scope
    # This is a bit of a hack, but avoids loading the model twice.
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
    # D = distances, I = indices of the chunks
    try:
        D, I = vector_index.search(query_embedding, k)
    except Exception as e:
        print(f"Error searching FAISS index: {e}")
        return [], []

    # 3. Format the results
    relevant_chunks = []
    citations = set()  # Use a set to avoid duplicate citations
    
    for i, chunk_index in enumerate(I[0]):
        # Ensure the index is valid
        if chunk_index < 0 or chunk_index >= len(text_chunks):
            continue
            
        chunk = text_chunks[chunk_index]
        meta = metadata[chunk_index]
        
        # --- FIX: Use .get() to provide default values and prevent KeyErrors ---
        source_name = meta.get('source', 'Unknown Source')
        source_url = meta.get('url', '#')
        source_date = meta.get('date', 'N/A')
        
        citation_str = f"[{source_name}]({source_url}) - {source_date}"
        
        relevant_chunks.append(f"Source: {citation_str}\nContent: {chunk}")
        citations.add(citation_str)

    return relevant_chunks, list(citations)

# --- 2. Prompt Engineering ---

def build_prompt(ticker, fundamentals, relevant_chunks, citations):
    """
    Builds the final prompt string to send to the LLM.
    """
    
    # --- System Prompt: The AI's "Instructions" ---
    system_prompt = """
You are a professional financial analyst. Your task is to provide a concise, data-driven analysis of a stock based *only* on the fundamentals and news articles provided.

**RULES:**
1.  Do NOT use any external knowledge.
2.  Do NOT make up information or specific price targets.
3.  Your analysis must be objective and balanced, mentioning both positive and negative points.
4.  Refer *explicitly* to the provided financial indicators in your reasoning.
5.  Base your "Forecast" on the *sentiment* and *facts* found in the provided news, combined with the fundamentals.
6.  The output must be formatted *exactly* as follows (use Markdown):

**Analysis:**
(Your overall analysis of the company's current situation, using the financial indicators.)

**Key News:**
(A summary of the most important points from the news articles provided.)

**Forecast:**
* **1 Week:** (Your short-term outlook. e.g., "Driven by recent earnings news..." or "Likely stable as news flow is light...")
* **1 Month:** (Your medium-term outlook. e.g., "Depends on follow-through from the recent product launch...")
* **6 Months:** (Your longer-term outlook. e.g., "Faces headwinds from... but has tailwinds from...")
* **12 Months:** (Your long-term outlook, focused on the major fundamental trends.)
"""
    
    # --- User Prompt: The "Data" ---
    
    # Format the fundamentals data
    fundamentals_str = "\n".join(f"- {key}: {value}" for key, value in fundamentals.items())
    
    # Format the news chunks
    if relevant_chunks:
        news_str = "\n\n---\n\n".join(relevant_chunks)
    else:
        news_str = "No recent news articles were found or provided."
        
    # Combine it all
    user_prompt = f"""
--- START OF DATA ---

**Stock Ticker:**
{ticker}

**Financial Indicators:**
{fundamentals_str}

**Recent News Articles:**
{news_str}

--- END OF DATA ---

Please provide your analysis based *only* on the data above, following all rules and the required format.
"""
    
    return system_prompt + user_prompt

# --- 3. AI Generation ---

def get_analysis(prompt_text):
    """
    Sends the prompt to the Gemini API and gets the response.
    """
    if not GEMINI_API_KEY:
        return "Error: Gemini API key is not configured."
        
    try:
        print("Generating analysis with Gemini API...")
        response = model.generate_content(prompt_text)
        return response.text
        
    except Exception as e:
        print(f"Error during Gemini API call: {e}")
        return f"Error: Could not get analysis from API. Details: {e}"
