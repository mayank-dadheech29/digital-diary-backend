from sqlalchemy import Column, String, Text, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
import uuid
from typing import Optional, List

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # user_id from Supabase Auth (no FK constraint)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    full_name = Column(Text, nullable=False)
    avatar_url = Column(Text)
    primary_title = Column(Text)
    primary_org = Column(Text)
    job_title_category = Column(Text, nullable=True)
    
    # Store flexible fields: { emails: [], phones: [], social_links: {}, tags: [], metadata: {} }
    dynamic_details = Column(JSONB, default={})
    search_text = Column(TSVECTOR, nullable=True)
    
    # AI Logic
    # search_text tsvector (managed by DB trigger usually, or we can use SQLAlchemy TSVector)
    # Gemini embeddings are 3072 dimensions (or 768 depending on model). 
    # Current error shows we are receiving 3072.
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(3072), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    entries = relationship(
        "Entry",
        secondary="entry_contacts",
        back_populates="contacts",
        lazy="select"
    )

    # Indexes
    __table_args__ = (
        Index("contacts_gin_idx", "dynamic_details", postgresql_using="gin"),
    )
