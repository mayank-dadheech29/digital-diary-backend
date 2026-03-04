from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db, close_db
from app.core.ai_service import DiaryIntelligence
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up Digital Diary API...")
    await init_db()
    
    # Initialize AI Service
    app.state.ai = DiaryIntelligence()
    
    yield
    
    # Shutdown
    print("Shutting down Digital Diary API...")
    await close_db()

app = FastAPI(
    title="Digital Diary API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # TODO: Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Digital Diary API"}

# Include Routers
from app.api.v1.endpoints import contacts
app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["contacts"])
from app.api.v1.endpoints import entries
app.include_router(entries.router, prefix="/api/v1/entries", tags=["entries"])
from app.api.v1.endpoints import transactions
app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])
from app.api.v1.endpoints import search
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
from app.api.v1.endpoints import ai
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
from app.api.v1.endpoints import insights
app.include_router(insights.router, prefix="/api/v1/insights", tags=["insights"])


@app.get("/ai-health")
async def ai_health_check():
    """Verify AI provider is configured and working."""
    try:
        response = app.state.ai.health_check()
        return {"status": "ok", "ai_response": response}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
