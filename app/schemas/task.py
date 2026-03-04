from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class TaskBase(BaseModel):
    title: str = Field(..., description="The title of the task")
    description: Optional[str] = None
    status: str = Field("pending", description="pending, in_progress, completed, archived")
    priority: str = Field("medium", description="low, medium, high")
    due_date: Optional[datetime] = None
    linked_contact_id: Optional[UUID] = None
    source_entry_id: Optional[int] = None

class TaskResponse(TaskBase):
    id: int
    user_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
