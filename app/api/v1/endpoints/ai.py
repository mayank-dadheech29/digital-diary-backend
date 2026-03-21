from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
import dspy
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.contact import Contact
from app.schemas.ai import ActionParseRequest, ActionParseResponse, ActionExtractedData
from app.core.auth import get_current_user

router = APIRouter()

class LLMParsedAction(BaseModel):
    intent: str = Field(description="Must be exactly one of: CREATE_CONTACT, CREATE_ENTRY, CREATE_TRANSACTION, or UNKNOWN")
    confidence: float = Field(description="Float from 0.0 to 1.0 indicating confidence")
    contact_name: str = Field(default="", description="Extracted person name, or empty string")
    title: str = Field(default="", description="Short summary title, or empty string")
    amount: float = Field(default=0.0, description="Numeric amount if any, or 0.0")
    currency: str = Field(default="", description="Currency code (e.g. USD) if any, or empty string")
    due_date: str = Field(default="", description="ISO date string if any time mentioned, or empty string")
    category: str = Field(default="", description="One of: FINANCIAL, ITEM, TASK, OTHER. Default to FINANCIAL if money involved, else deduce. Or empty string")
    transaction_type: str = Field(default="", description="One of: PAYABLE (I owe them), RECEIVABLE (they owe me). Empty string if not applicable.")
    content: str = Field(default="", description="Longer description or meeting notes if any, else empty string")
    phone: str = Field(default="", description="The phone number mentioned, or empty string")
    email: str = Field(default="", description="The email address mentioned, or empty string")
    organization: str = Field(default="", description="The organization or company mentioned, or empty string")
    job_title: str = Field(default="", description="The job title or role mentioned, or empty string")
    address: str = Field(default="", description="The location or address mentioned, or empty string")
    custom_fields: dict[str, str] = Field(default_factory=dict, description="A dictionary of any other dynamic or custom details mentioned (e.g. {'IPS Batch': '2001', 'Interests': 'Golf', 'Met At': 'Conference'})")

class ActionExtractionSignature(dspy.Signature):
    """Parse a natural language command into structured intent and entities for a personal CRM app.
    
    Rules for Intents:
    - CREATE_TRANSACTION: For len-den (commitments), ledgers, debts, lending items, assigning tasks. Example: "Remind me to pay John 50 dollars tomorrow" or "Lent a book to Sarah"
    - CREATE_ENTRY: For diary entries, meeting notes, generic thoughts. Example: "Met with Alex today about the new project"
    - CREATE_CONTACT: For explicitly adding a new person. Example: "Add my new plumber Mike to contacts"
    
    Extract specific values deeply if possible. Due dates should be returned in ISO string format if a relative time like "tomorrow" is mentioned.
    """
    command: str = dspy.InputField(desc="The user's natural language string")
    parsed: LLMParsedAction = dspy.OutputField()

@router.post("/parse-action", response_model=ActionParseResponse)
async def parse_action(
    payload: ActionParseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    ai_service = request.app.state.ai
    if not ai_service.lm:
        raise Exception("AI provider not configured")
        
    try:
        with dspy.settings.context(lm=ai_service.lm):
            predictor = dspy.Predict(ActionExtractionSignature)
            result = predictor(command=payload.text)
            parsed: LLMParsedAction = result.parsed
            
            extracted_data = ActionExtractedData(
                contact_name=parsed.contact_name if parsed.contact_name else None,
                title=parsed.title if parsed.title else None,
                amount=parsed.amount if parsed.amount > 0 else None,
                currency=parsed.currency if parsed.currency else None,
                due_date=None, # In a robust system, parse the ISO string back to datetime
                category=parsed.category if parsed.category in ["FINANCIAL", "ITEM", "TASK", "OTHER"] else None,
                type=parsed.transaction_type if parsed.transaction_type in ["PAYABLE", "RECEIVABLE"] else None,
                content=parsed.content if parsed.content else None,
                phone=parsed.phone if parsed.phone else None,
                email=parsed.email if parsed.email else None,
                organization=parsed.organization if parsed.organization else None,
                job_title=parsed.job_title if parsed.job_title else None,
                address=parsed.address if parsed.address else None,
                custom_fields=parsed.custom_fields if parsed.custom_fields else None,
            )
            
            intent_val = parsed.intent if parsed.intent in ["CREATE_CONTACT", "CREATE_ENTRY", "CREATE_TRANSACTION"] else "UNKNOWN"
            confidence_val = parsed.confidence
            
    except Exception as e:
        print(f"DSPy TypedPredictor parsing error: {e}")
        intent_val = "UNKNOWN"
        confidence_val = 0.0
        extracted_data = ActionExtractedData()
        
    resolved_id = None
    if extracted_data.contact_name:
        # Search db for this contact
        idx = extracted_data.contact_name
        stmt = select(Contact.id).where(
            Contact.user_id == user_id,
            Contact.full_name.ilike(f"%{idx}%")
        ).limit(1)
        db_res = await db.execute(stmt)
        resolved_id = db_res.scalar_one_or_none()

    return ActionParseResponse(
        intent=intent_val,
        confidence=confidence_val,
        extracted_data=extracted_data,
        resolved_contact_id=resolved_id
    )

from fastapi import UploadFile, File, Form, HTTPException
import httpx
import os
from app.models.meeting_chunk import MeetingChunk
from app.models.entry import Entry
from app.models.entry_contact import EntryContact
from app.models.transaction import Transaction

async def transcribe_with_groq(file_bytes: bytes, filename: str) -> str:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise Exception("GROQ_API_KEY not set. Cannot transcribe audio.")
    
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}"
    }
    
    files = {
        "file": (filename, file_bytes, "audio/m4a")
    }
    data = {
        "model": "whisper-large-v3",
        "response_format": "json",
        "prompt": "यह हिंदी और English में है। (This is in Hindi and English)"
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, files=files, data=data)
        if response.status_code != 200:
            raise Exception(f"Groq transcription failed: {response.text}")
        return response.json().get("text", "")

@router.post("/transcribe-chunk")
async def transcribe_chunk(
    session_id: UUID = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    audio_bytes = await file.read()
    try:
        transcript = await transcribe_with_groq(audio_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    chunk = MeetingChunk(
        user_id=user_id,
        session_id=session_id,
        chunk_index=chunk_index,
        transcript_text=transcript
    )
    db.add(chunk)
    await db.commit()
    
    return {"status": "success", "transcript": transcript}

class ExtractedTask(BaseModel):
    title: str = Field(description="Title of the task or commitment")
    type: str = Field(description="PAYABLE (I owe them) or RECEIVABLE (They owe me)")
    category: str = Field(description="FINANCIAL, ITEM, TASK, or OTHER")
    amount: float = Field(default=0.0)

class MeetingSummaryAction(BaseModel):
    executive_summary: str = Field(description="A concise 3-bullet recap of the meeting")
    extracted_tasks: list[ExtractedTask] = Field(default_factory=list, description="List of promises, tasks, or financial debts mentioned. Leave empty if none.")

class MeetingSummarizationSignature(dspy.Signature):
    """Summarize a meeting transcript and extract len-den actionable commitments from it."""
    transcript: str = dspy.InputField(desc="The raw audio transcript")
    parsed: MeetingSummaryAction = dspy.OutputField()

class SummarizeMeetingRequest(BaseModel):
    session_id: UUID
    contact_id: UUID

class MeetingSummaryResponse(BaseModel):
    entry_id: int
    summary: str

@router.post("/summarize-meeting", response_model=MeetingSummaryResponse)
async def summarize_meeting(
    payload: SummarizeMeetingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    stmt = select(MeetingChunk).where(
        MeetingChunk.session_id == payload.session_id,
        MeetingChunk.user_id == user_id
    ).order_by(MeetingChunk.chunk_index.asc())
    
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    
    if not chunks:
        raise HTTPException(status_code=404, detail="No audio chunks found for this session")
        
    full_transcript = " ".join([c.transcript_text for c in chunks])
    
    ai_service = request.app.state.ai
    if not ai_service.lm:
        raise HTTPException(status_code=500, detail="AI provider not configured")
        
    try:
        with dspy.settings.context(lm=ai_service.lm):
            predictor = dspy.Predict(MeetingSummarizationSignature)
            ai_res = predictor(transcript=full_transcript)
            parsed: MeetingSummaryAction = ai_res.parsed
            
            executive_summary = parsed.executive_summary
            tasks = parsed.extracted_tasks
    except Exception as e:
        print(f"Summarization AI failed: {e}")
        executive_summary = "AI Summarization failed. Raw Transcript:\n\n" + full_transcript
        tasks = []

    # 1. Fetch Contact
    contact_stmt = select(Contact).where(Contact.id == payload.contact_id, Contact.user_id == user_id)
    contact = (await db.execute(contact_stmt)).scalar_one_or_none()

    # 2. Create the Entry (Note)
    final_content = executive_summary
    
    new_entry = Entry(
        user_id=user_id,
        content=final_content,
        title="Audio Meeting Summary",
        entry_type="MEETING_SUMMARY"
    )
    db.add(new_entry)
    await db.flush() # Get new_entry.id
    
    # Associate Entry with Contact explicitly via association table
    # This prevents SQLAlchemy from attempting a synchronous lazy load on bidirectional relationships
    if contact:
        new_ec = EntryContact(entry_id=new_entry.id, contact_id=contact.id)
        db.add(new_ec)
    
    # 2. Extract Tasks into Transactions (Len-Den)
    from datetime import datetime
    from sqlalchemy.sql import func
    
    for t in tasks:
        # Validate constraint types
        valid_type = t.type if t.type in ["PAYABLE", "RECEIVABLE"] else "PAYABLE"
        valid_cat = t.category if t.category in ["FINANCIAL", "ITEM", "TASK", "OTHER"] else "TASK"
        
        new_txn = Transaction(
            user_id=user_id,
            contact_id=payload.contact_id,
            type=valid_type,
            category=valid_cat,
            title=t.title,
            amount=t.amount,
            status="PENDING",
            due_date=func.now(), # Default
            related_entry_id=new_entry.id
        )
        db.add(new_txn)
        
    # 3. Cleanup chunks
    for c in chunks:
        await db.delete(c)
        
    await db.commit()
    
    return MeetingSummaryResponse(
        entry_id=new_entry.id,
        summary=executive_summary
    )
