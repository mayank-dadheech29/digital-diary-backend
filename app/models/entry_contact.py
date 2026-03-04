from sqlalchemy import Column, Text, DateTime, func, ForeignKey, BigInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class EntryContact(Base):
    __tablename__ = "entry_contacts"

    id = Column(BigInteger, primary_key=True, index=True)
    entry_id = Column(BigInteger, ForeignKey("entries.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    
    context_summary = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('entry_id', 'contact_id', name='unique_entry_contact'),
    )
