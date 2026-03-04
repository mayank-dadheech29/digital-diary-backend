from sqlalchemy import Column, String, Text, DateTime, Float, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.core.database import Base
import uuid

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # type: PAYABLE (I owe), RECEIVABLE (They owe)
    type = Column(String, nullable=False)
    
    # category: FINANCIAL, ITEM, TASK, OTHER
    category = Column(String, nullable=False, default="FINANCIAL", index=True)
    
    title = Column(String, nullable=True)
    
    amount = Column(Float, nullable=True)
    currency = Column(String, nullable=True, default="INR")
    
    # status: PENDING, COMPLETED, CANCELLED
    status = Column(String, default="PENDING", index=True)
    
    due_date = Column(DateTime(timezone=True), nullable=False, index=True)
    reminder_at = Column(DateTime(timezone=True), nullable=True)
    
    description = Column(Text)
    
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    search_text = Column(TSVECTOR, nullable=True)
    
    related_entry_id = Column(BigInteger, ForeignKey("entries.id", ondelete="SET NULL"), nullable=True)
    
    # Vector embedding for semantic search
    embedding = Column(Vector(3072))

    # Relationships
    contact = relationship("Contact", backref="transactions")
    related_entry = relationship("Entry")

    def __repr__(self):
        return f"<Transaction(id={self.id}, type={self.type}, amount={self.amount}, status={self.status})>"
