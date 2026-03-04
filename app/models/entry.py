from sqlalchemy import Column, Integer, String, Text, DateTime, func, Float, BigInteger
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from app.core.database import Base
import datetime

class Entry(Base):
    __tablename__ = "entries"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    content = Column(Text, nullable=False)
    title = Column(String, nullable=True)
    images = Column(ARRAY(Text), default=[])
    audio_url = Column(Text)
    sentiment_score = Column(Float)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Vector embedding for semantic search
    embedding = Column(Vector(3072))

    # Relationships
    contacts = relationship(
        "Contact",
        secondary="entry_contacts",
        back_populates="entries",
        lazy="select"
    )

    def __repr__(self):
        return f"<Entry(id={self.id}, created_at={self.created_at})>"
