from sqlalchemy import Column, String, Text, DateTime, Integer, func, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    
    title = Column(Text, nullable=False)
    description = Column(Text)
    
    # Status: pending, in_progress, completed, archived
    status = Column(Text, default="pending")
    # Priority: low, medium, high
    priority = Column(Text, default="medium")
    
    due_date = Column(DateTime(timezone=True))
    
    linked_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"))
    source_entry_id = Column(BigInteger, ForeignKey("entries.id", ondelete="SET NULL"))
    
    # Vector embedding for semantic search
    embedding = Column(Vector(3072))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
