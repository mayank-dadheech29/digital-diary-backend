from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

class ActionExtractedData(BaseModel):
    contact_name: Optional[str] = Field(None, description="The name of the person mentioned, if any")
    title: Optional[str] = Field(None, description="A short summary or title of the action")
    amount: Optional[float] = Field(None, description="Any financial amount mentioned")
    currency: Optional[str] = Field(None, description="The currency of the amount, e.g., USD, INR")
    due_date: Optional[datetime] = Field(None, description="The deadline or scheduled date mentioned in ISO format")
    category: Optional[Literal["FINANCIAL", "ITEM", "TASK", "OTHER"]] = Field(None, description="Category of the commitment")
    type: Optional[Literal["PAYABLE", "RECEIVABLE"]] = Field(None, description="PAYABLE (I owe them) or RECEIVABLE (they owe me)")
    content: Optional[str] = Field(None, description="The detailed content or notes for a diary entry")
    phone: Optional[str] = Field(None, description="The phone number mentioned, if any")
    email: Optional[str] = Field(None, description="The email address mentioned, if any")
    organization: Optional[str] = Field(None, description="The organization or company mentioned, if any")
    job_title: Optional[str] = Field(None, description="The job title or role mentioned, if any")
    address: Optional[str] = Field(None, description="The location or address mentioned, if any")
    custom_fields: Optional[dict[str, str]] = Field(None, description="Any other key-value pair details mentioned (like IPS Batch, Interests, Met At, etc)")

class ActionParseResponse(BaseModel):
    intent: Literal["CREATE_CONTACT", "CREATE_ENTRY", "CREATE_TRANSACTION", "UNKNOWN"] = Field(
        ..., description="The classified intent of the user's natural language command"
    )
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0")
    extracted_data: ActionExtractedData
    resolved_contact_id: Optional[UUID] = Field(None, description="The UUID of the resolved contact from the database")

class ActionParseRequest(BaseModel):
    text: str = Field(..., description="The natural language command from the user")
