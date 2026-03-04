from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

class ContactBase(BaseModel):
    full_name: str = Field(..., description="Full name of the contact")
    avatar_url: Optional[str] = None
    primary_title: Optional[str] = None
    primary_org: Optional[str] = None
    job_title_category: Optional[str] = None
    dynamic_details: Dict[str, Any] = Field(default_factory=dict, description="Flexible fields like emails, phones, social_links")

class ContactCreate(ContactBase):
    pass

class ContactUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    primary_title: Optional[str] = None
    primary_org: Optional[str] = None
    job_title_category: Optional[str] = None
    dynamic_details: Optional[Dict[str, Any]] = None

class ContactResponse(ContactBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    
    last_interaction_title: Optional[str] = None
    last_interaction_type: Optional[str] = None

    class Config:
        from_attributes = True

class ContactSearchRequest(BaseModel):
    query: str
    limit: int = 10
    threshold: float = 0.5
