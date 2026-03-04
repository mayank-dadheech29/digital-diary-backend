import asyncio
import os
import json
from pydantic import BaseModel
from typing import List, Optional, Literal

# Use identical schemas for validation in test
class TransactionFilters(BaseModel):
    status: Optional[str] = None
    type: Optional[str] = None
    overdue: Optional[bool] = None
    contact_name: Optional[str] = None

class NL2SQLIntent(BaseModel):
    use_vector_search: bool
    optimized_query: Optional[str] = None
    target_tables: List[str]
    transaction_filters: Optional[TransactionFilters] = None

async def test_prompts():
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("GOOGLE_API_KEY not found")
        return
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")
    
    queries = [
        "Last 2 Promises pending",
        "People I met last week",
        "React developers",
        "Aman ko 500 diye"
    ]
    
    current_date = "2026-02-28T19:55:00" # Mock date
    
    schema_prompt = f"""
    You are a search query classifier for a personal digital diary and finance app.
    Current date (IST): {current_date}
    ## Tables: CONTACTS, ENTRIES, TRANSACTIONS, INTERACTIONS, TASKS
    Return ONLY JSON.
    """

    for q in queries:
        prompt = f"{schema_prompt}\n\nQuery: {q}"
        resp = model.generate_content(
            prompt, 
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.0
            )
        )
        print(f"Query: {q}")
        print(f"Result: {resp.text}\n")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_prompts())
