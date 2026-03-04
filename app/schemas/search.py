from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
from app.schemas.contact import ContactResponse
from app.schemas.entry import EntryResponse
from app.schemas.transaction import TransactionResponse
from app.schemas.interaction import InteractionResponse
from app.schemas.task import TaskResponse

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5
    threshold: Optional[float] = Field(default=0.40, description="Maximum cosine distance allowed. Lower is stricter.")

class CurrencyTotal(BaseModel):
    currency: str
    amount: float

class SearchSummary(BaseModel):
    metric: Optional[str] = None
    explanation: Optional[str] = None
    contact_ids: List[UUID] = Field(default_factory=list)
    transaction_count: int = 0
    currency_totals: List[CurrencyTotal] = Field(default_factory=list)

class SearchResponse(BaseModel):
    contacts: List[ContactResponse] = Field(default_factory=list)
    entries: List[EntryResponse] = Field(default_factory=list)
    transactions: List[TransactionResponse] = Field(default_factory=list)
    interactions: List[InteractionResponse] = Field(default_factory=list)
    tasks: List[TaskResponse] = Field(default_factory=list)
    summary: Optional[SearchSummary] = None
