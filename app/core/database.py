from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = None
AsyncSessionLocal = None

Base = declarative_base()

async def init_db():
    global engine, AsyncSessionLocal
    if not DATABASE_URL:
        # For build phase or testing without DB
        print("WARNING: DATABASE_URL not set. Database features will fail.")
        return

    try:
        # Create Async Engine
        engine = create_async_engine(
            DATABASE_URL,
            echo=True,
            future=True,
            pool_pre_ping=True  # vital for identifying stale connections
        )
        
        # Verify connection
        async with engine.begin() as conn:
            # Create extension if not exists
            await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS vector"))
            
        print("Database connection initialized.")

        # Create Session Factory
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
    except Exception as e:
        print(f"Error initializing database: {e}")

async def close_db():
    global engine
    if engine:
        await engine.dispose()
        print("Database connection closed.")

async def get_db():
    if AsyncSessionLocal is None:
        # Emergency initialization if for some reason lifespan didn't run (unlikely but safe)
        if DATABASE_URL:
            await init_db()
        else:
            raise Exception("Database not initialized and DATABASE_URL not set")
            
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

import sqlalchemy
