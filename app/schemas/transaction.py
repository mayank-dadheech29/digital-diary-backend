from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from uuid import UUID
from datetime import datetime
from app.schemas.contact import ContactResponse

class CommitmentCategory(str, Enum):
    FINANCIAL = "FINANCIAL"
    ITEM = "ITEM"
    TASK = "TASK"
    OTHER = "OTHER"

class TransactionBase(BaseModel):
    title: Optional[str] = Field(None, description="Short title for the transaction/reminder")
    type: str = Field(..., description="PAYABLE (I owe) or RECEIVABLE (They owe)")
    
    # NEW: Category Field
    category: CommitmentCategory = Field(CommitmentCategory.FINANCIAL, description="Type of commitment")
    
    # MODIFIED: Both are now Optional
    amount: Optional[float] = Field(None, gt=0, description="Amount in specified currency (Optional for ITEMS/TASKS)")
    currency: Optional[str] = Field("INR", description="Currency code (Optional for ITEMS/TASKS)")
    
    due_date: datetime = Field(..., description="The deadline for payment")
    reminder_at: Optional[datetime] = Field(None, description="Optional reminder date")
    description: Optional[str] = None
    contact_id: UUID

class TransactionCreate(TransactionBase):
    related_entry_id: Optional[int] = None

class TransactionUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[CommitmentCategory] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    reminder_at: Optional[datetime] = None
    status: Optional[str] = Field(None, description="PENDING, COMPLETED, CANCELLED")
    description: Optional[str] = None
    related_entry_id: Optional[int] = None

class TransactionResponse(TransactionBase):
    id: UUID
    user_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    related_entry_id: Optional[int] = None
    contact: Optional[ContactResponse] = None

    class Config:
        from_attributes = True

class LenDenSummary(BaseModel):
    total_payable: float
    total_receivable: float
    net_balance: float
