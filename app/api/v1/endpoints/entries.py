from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.models.entry import Entry
from app.models.entry_contact import EntryContact
from app.models.contact import Contact
from app.schemas.entry import EntryCreate, EntryUpdate, EntryResponse
from app.core.auth import get_current_user

router = APIRouter()

@router.post("/", response_model=EntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    entry: EntryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Generate Embedding
    text_to_embed = f"{entry.title or ''} {entry.content}"
    embedding = await request.app.state.ai.get_embedding(text_to_embed)

    # 2. Create Entry
    new_entry = Entry(
        user_id=user_id,
        title=entry.title,
        content=entry.content,
        audio_url=entry.audio_url,
        images=entry.images,
        embedding=embedding if embedding else None
    )
    db.add(new_entry)
    await db.flush() # Get ID

    # 3. Link Contacts
    for contact_id in entry.contact_ids:
        # Verify contact belongs to user
        contact_result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
        if contact_result.scalar_one_or_none():
            link = EntryContact(entry_id=new_entry.id, contact_id=contact_id)
            db.add(link)

    await db.commit()
    
    # Fetch entry with eagerly loaded contacts to avoid MissingGreenlet error during model_validate
    stmt = select(Entry).options(selectinload(Entry.contacts)).where(Entry.id == new_entry.id)
    result = await db.execute(stmt)
    entry_with_contacts = result.scalar_one()

    return EntryResponse.model_validate(entry_with_contacts)

@router.get("/{entry_id}", response_model=EntryResponse)
async def get_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # Fetch entry with eagerly loaded contacts
    stmt = select(Entry).options(selectinload(Entry.contacts)).where(Entry.id == entry_id, Entry.user_id == user_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    return EntryResponse.model_validate(entry)
@router.get("/", response_model=List[EntryResponse])
async def list_entries(
    skip: int = 0,
    limit: int = 100,
    contact_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # Use selectinload to batch-load contacts in one query, avoiding the
    # N+1 lazy-load problem and the MissingGreenlet error in async context.
    query = select(Entry).options(selectinload(Entry.contacts)).where(Entry.user_id == user_id)
    
    if contact_id:
        query = query.join(EntryContact).where(EntryContact.contact_id == contact_id)
        
    result = await db.execute(query.order_by(Entry.created_at.desc()).offset(skip).limit(limit))
    entries = result.scalars().all()
    
    return [EntryResponse.model_validate(entry) for entry in entries]

@router.patch("/{entry_id}", response_model=EntryResponse)
async def update_entry(
    entry_id: int,
    entry_update: EntryUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    # 1. Fetch existing
    result = await db.execute(select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id))
    db_entry = result.scalar_one_or_none()
    if not db_entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # 2. Update fields
    update_data = entry_update.model_dump(exclude_unset=True)
    contact_ids_to_update = update_data.pop('contact_ids', None) # Handle contacts separately

    for key, value in update_data.items():
        setattr(db_entry, key, value)

    # 3. Refresh embedding if content/title changed
    if any(k in update_data for k in ['title', 'content']):
        text_to_embed = f"{db_entry.title or ''} {db_entry.content}"
        embedding = await request.app.state.ai.get_embedding(text_to_embed)
        db_entry.embedding = embedding

    # 4. Update Contacts if provided
    if contact_ids_to_update is not None:
        # Remove existing links
        await db.execute(select(EntryContact).where(EntryContact.entry_id == entry_id).execution_options(synchronize_session=False))
        # Note: Delete is a bit trickier with async, let's do delete statement
        from sqlalchemy import delete
        await db.execute(delete(EntryContact).where(EntryContact.entry_id == entry_id))
        
        # Add new links
        for contact_id in contact_ids_to_update:
             # Verify contact belongs to user
            contact_result = await db.execute(select(Contact).where(Contact.id == contact_id, Contact.user_id == user_id))
            if contact_result.scalar_one_or_none():
                link = EntryContact(entry_id=entry_id, contact_id=contact_id)
                db.add(link)

    await db.commit()
    
    # Fetch refreshed entry with contacts
    stmt = select(Entry).options(selectinload(Entry.contacts)).where(Entry.id == entry_id)
    result = await db.execute(stmt)
    updated_entry = result.scalar_one()

    return EntryResponse.model_validate(updated_entry)

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    result = await db.execute(select(Entry).where(Entry.id == entry_id, Entry.user_id == user_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    await db.delete(entry)
    await db.commit()
