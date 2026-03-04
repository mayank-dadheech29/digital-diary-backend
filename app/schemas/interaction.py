from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime

class InteractionBase(BaseModel):
    type: str = Field(..., description="call, meeting, note, email, message, other")
    content: Optional[str] = None
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    images: List[str] = Field(default_factory=list)
    occurred_at: datetime
    contact_id: UUID

class InteractionResponse(InteractionBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
