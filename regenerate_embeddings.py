import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.contact import Contact
from app.models.entry import Entry
from app.models.entry_contact import EntryContact  # noqa: F401  # Ensures secondary table is registered
from app.models.transaction import Transaction
from app.core.ai_service import DiaryIntelligence

async def main():
    engine = create_async_engine(os.environ.get("DATABASE_URL"))
    SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ai_service = DiaryIntelligence()
    
    async with SessionLocal() as db:
        print("Regenerating Contacts...")
        res = await db.execute(select(Contact))
        contacts = res.scalars().all()
        for c in contacts:
            if c.full_name:
                details_str = " ".join([f"{k}: {v}" for k, v in (c.dynamic_details or {}).items()])
                text = f"{c.full_name} {c.primary_title or ''} {c.primary_org or ''} {details_str}"
                emb = await ai_service.get_embedding(text)
                c.embedding = emb
        await db.commit()
        
        print("Regenerating Entries...")
        res = await db.execute(select(Entry))
        entries = res.scalars().all()
        for e in entries:
            text = f"{e.title or ''} {e.content or ''}"
            emb = await ai_service.get_embedding(text)
            e.embedding = emb
        await db.commit()
        
        print("Regenerating Transactions...")
        res = await db.execute(select(Transaction).options(selectinload(Transaction.contact)))
        transactions = res.scalars().all()
        for t in transactions:
            contact_name = t.contact.full_name if t.contact else ""
            contact_org = t.contact.primary_org if t.contact else ""
            text = f"{contact_name} {contact_org} {t.title or ''} {t.description or ''} {t.type} {t.category}"
            emb = await ai_service.get_embedding(text)
            t.embedding = emb
        await db.commit()
        
    print("Done regenerating all embeddings cleanly!")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
