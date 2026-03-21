from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from app.schemas.contact import ContactResponse

class EntryBase(BaseModel):
    title: Optional[str] = None
    content: str = Field(..., description="The main content/body of the note")
    audio_url: Optional[str] = None
    images: List[str] = Field(default_factory=list)

class EntryCreate(EntryBase):
    contact_ids: List[UUID] = Field(default_factory=list, description="List of contact IDs to link this note to")

class EntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    audio_url: Optional[str] = None
    images: Optional[List[str]] = None
    contact_ids: Optional[List[UUID]] = None

class EntryResponse(EntryBase):
    id: int
    user_id: UUID
    created_at: datetime
    sentiment_score: Optional[float] = None
    entry_type: str
    contacts: List[ContactResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True
