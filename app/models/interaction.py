from sqlalchemy import Column, String, Text, DateTime, Integer, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from app.core.database import Base
import uuid

class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # call, meeting, note, email, message, other
    type = Column(Text, nullable=False)
    
    content = Column(Text)
    summary = Column(Text)
    recording_url = Column(Text)
    duration_seconds = Column(Integer)
    
    # Images array (Supabase schema)
    images = Column(ARRAY(Text), default=[])
    
    embedding = Column(Vector(3072))
    
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("interactions_contact_id_occurred_at_idx", "contact_id", "occurred_at"),
    )
