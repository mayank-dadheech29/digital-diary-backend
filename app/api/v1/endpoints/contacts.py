from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, cast, String, func, literal
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.contact import Contact
from app.models.transaction import Transaction
from app.models.entry import Entry
from app.models.entry_contact import EntryContact
from app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse, ContactSearchRequest
from app.core.auth import get_current_user

router = APIRouter()

async def attach_last_interactions(contacts: List[Contact], db: AsyncSession):
    if not contacts:
        return
    
    contact_ids = [c.id for c in contacts]
    
    # Latest Transactions
    stmt_tx = select(
        Transaction.contact_id,
        Transaction.title,
        Transaction.created_at,
        Transaction.amount,
        Transaction.currency,
        Transaction.category
    ).distinct(Transaction.contact_id).where(
        Transaction.contact_id.in_(contact_ids)
    ).order_by(
        Transaction.contact_id, Transaction.created_at.desc()
    )
    result_tx = await db.execute(stmt_tx)
    tx_map = {row.contact_id: row for row in result_tx.all()}
    
    # Latest Entries
    stmt_en = select(
        EntryContact.contact_id,
        Entry.title,
        Entry.content,
        Entry.created_at
    ).select_from(Entry).join(EntryContact).distinct(EntryContact.contact_id).where(
        EntryContact.contact_id.in_(contact_ids)
    ).order_by(
        EntryContact.contact_id, Entry.created_at.desc()
    )
    result_en = await db.execute(stmt_en)
    en_map = {row.contact_id: row for row in result_en.all()}
    
    for contact in contacts:
        tx = tx_map.get(contact.id)
        en = en_map.get(contact.id)
        
        last_date = None
        last_title = None
        last_type = None
        
        if tx:
            last_date = tx.created_at
            amount_str = f" {tx.currency or 'INR'} {tx.amount}" if tx.amount else ""
            desc = tx.title or tx.category.capitalize()
            last_title = f"{desc}{amount_str}".strip()
            last_type = "transaction"
            
        if en:
            if not last_date or en.created_at > last_date:
                last_title = en.title or (en.content[:40] + "..." if len(en.content) > 40 else en.content)
                last_type = "note"
                
        setattr(contact, "last_interaction_title", last_title)
        setattr(contact, "last_interaction_type", last_type)

@router.post("/", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    contact: ContactCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Generate Embedding if useful text is present
    details_str = " ".join([f"{k}: {v}" for k, v in (contact.dynamic_details or {}).items()])
    text_to_embed = f"{contact.full_name} {contact.primary_title or ''} {contact.primary_org or ''} {details_str}"
    embedding = await request.app.state.ai.get_embedding(text_to_embed)

    # 2. Create DB Object
    new_contact = Contact(
        user_id=user_id,
        full_name=contact.full_name,
        avatar_url=contact.avatar_url,
        primary_title=contact.primary_title,
        primary_org=contact.primary_org,
        dynamic_details=contact.dynamic_details,
        embedding=embedding if embedding else None
    )
    
    db.add(new_contact)
    await db.commit()
    await db.refresh(new_contact)
    return new_contact

@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: UUID, 
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    await attach_last_interactions([contact], db)
    return contact

@router.get("/", response_model=List[ContactResponse])
async def list_contacts(
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(select(Contact).where(Contact.user_id == user_id).offset(skip).limit(limit))
    contacts = result.scalars().all()
    await attach_last_interactions(contacts, db)
    return contacts

@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    contact_update: ContactUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Fetch existing
    result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
    db_contact = result.scalar_one_or_none()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # 2. Update fields
    update_data = contact_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_contact, key, value)
    
    # 3. Refresh embedding if needed
    if any(k in update_data for k in ['full_name', 'primary_title', 'primary_org', 'dynamic_details']):
        details_str = " ".join([f"{k}: {v}" for k, v in (db_contact.dynamic_details or {}).items()])
        text_to_embed = f"{db_contact.full_name} {db_contact.primary_title or ''} {db_contact.primary_org or ''} {details_str}"
        embedding = await request.app.state.ai.get_embedding(text_to_embed)
        db_contact.embedding = embedding

    await db.commit()
    await db.refresh(db_contact)
    return db_contact

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    await db.delete(contact)
    await db.commit()

@router.post("/search", response_model=List[ContactResponse])
async def search_contacts(
    search_request: ContactSearchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Generate Query Embedding
    query_embedding = await request.app.state.ai.get_embedding(search_request.query)
    term = f"%{search_request.query.strip()}%"
    ts_query = func.websearch_to_tsquery('simple', search_request.query.strip()) if search_request.query.strip() else None

    lexical_clauses = [
        Contact.full_name.ilike(term),
        Contact.primary_org.ilike(term),
        Contact.primary_title.ilike(term),
        cast(Contact.dynamic_details, String).ilike(term),
    ]
    if ts_query is not None:
        lexical_clauses.append(Contact.search_text.op("@@")(ts_query))

    # 2. Hybrid Search (Scoped to User)
    if query_embedding:
        stmt = select(Contact).where(
            Contact.user_id == user_id,
            or_(
                Contact.embedding.cosine_distance(query_embedding) < search_request.threshold,
                *lexical_clauses
            )
        ).order_by(
            func.ts_rank_cd(Contact.search_text, ts_query).desc() if ts_query is not None else literal(0.0),
            Contact.embedding.cosine_distance(query_embedding),
            Contact.created_at.desc()
        ).limit(search_request.limit)
    else:
        stmt = select(Contact).where(
            Contact.user_id == user_id,
            or_(*lexical_clauses)
        ).order_by(
            func.ts_rank_cd(Contact.search_text, ts_query).desc() if ts_query is not None else literal(0.0),
            Contact.created_at.desc()
        ).limit(search_request.limit)
        
    result = await db.execute(stmt)
    contacts = result.scalars().all()
    await attach_last_interactions(contacts, db)
    return contacts
