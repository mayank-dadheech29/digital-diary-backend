from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
import uuid

class MeetingChunk(Base):
    __tablename__ = "meeting_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    transcript_text = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<MeetingChunk(session_id={self.session_id}, index={self.chunk_index})>"
