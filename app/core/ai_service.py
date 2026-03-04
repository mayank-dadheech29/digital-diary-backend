import dspy
import os

class DiaryIntelligence:
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "google").lower()
        self.api_key_google = os.getenv("GOOGLE_API_KEY")
        self.api_key_openai = os.getenv("OPENAI_API_KEY")
        self.embedding_dim = int(os.getenv("EMBEDDING_DIM", "3072"))
        self.google_embedding_model = os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001")
        self.openai_embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        self.lm = None
        self._configure_dspy()

    def _configure_dspy(self):
        if self.provider == "google":
            if not self.api_key_google:
                print("WARNING: GOOGLE_API_KEY not set. AI features will fail.")
                return
            
            # Configure Gemini using dspy.LM
            # Model string syntax: provider/model-name
            self.lm = dspy.LM('gemini/gemini-2.5-flash', api_key=self.api_key_google)
            dspy.configure(lm=self.lm)
            print("DSPy configured with Google Gemini.")

        elif self.provider == "openai":
            if not self.api_key_openai:
                print("WARNING: OPENAI_API_KEY not set. AI features will fail.")
                return
            
            # Configure OpenAI using dspy.LM
            self.lm = dspy.LM('openai/gpt-4o-mini', api_key=self.api_key_openai)
            dspy.configure(lm=self.lm)
            print("DSPy configured with OpenAI.")
        

    async def get_embedding(self, text: str) -> list[float]:
        """Generates a vector embedding for the given text."""
        if not text or not text.strip():
            return []
        
        # ─────────────────────────────────────────────────────────────────
        # For MVP using Gemini:
        # ─────────────────────────────────────────────────────────────────
        if self.provider == "google":
            try:
                # Lazy import
                from google import genai
                
                # 1. Initialize the client
                client = genai.Client(api_key=self.api_key_google)
                
                # 2. Use the 'aio' (async) module so we don't block FastAPI
                result = await client.aio.models.embed_content(
                    model=self.google_embedding_model,
                    contents=text
                )
                
                # 3. Correctly extract the array from the new SDK response object
                values = result.embeddings[0].values
                if self.embedding_dim and len(values) != self.embedding_dim:
                    print(
                        f"Embedding dimension mismatch (google): expected {self.embedding_dim}, got {len(values)}. "
                        "Returning empty embedding to avoid pgvector errors."
                    )
                    return []
                return values
                
            except Exception as e:
                print(f"Error generating Gemini embedding: {e}")
                return []
        
        # ─────────────────────────────────────────────────────────────────
        # For MVP using OpenAI:
        # ─────────────────────────────────────────────────────────────────
        elif self.provider == "openai":
            try:
                # Lazy import the ASYNC version of the OpenAI client
                from openai import AsyncOpenAI
                
                # 1. Initialize the async client
                client = AsyncOpenAI(api_key=self.api_key_openai)
                
                # 2. Await the response
                response = await client.embeddings.create(
                    input=text,
                    model=self.openai_embedding_model
                )
                
                values = response.data[0].embedding
                if self.embedding_dim and len(values) != self.embedding_dim:
                    print(
                        f"Embedding dimension mismatch (openai): expected {self.embedding_dim}, got {len(values)}. "
                        "Returning empty embedding to avoid pgvector errors."
                    )
                    return []
                return values
                
            except Exception as e:
                print(f"Error generating OpenAI embedding: {e}")
                return []
        
        return []

    def health_check(self):
        """Test if the LLM is reachable."""
        if not self.lm:
            return "AI Service not configured (missing keys or invalid provider)"
        
        # Simple DSPy prediction to test
        predict = dspy.Predict("question -> answer")
        result = predict(question="Say hello world in one word.")
        return result.answer
