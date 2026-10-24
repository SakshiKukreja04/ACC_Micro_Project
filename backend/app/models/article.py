import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    JSON,
    Index,
    UniqueConstraint,
)
from app.db.session import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate hex UUID string."""
    return uuid.uuid4().hex


class Article(Base):
    __tablename__ = "articles"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Core article metadata
    title = Column(String(500), nullable=False)
    canonical_url = Column(Text, nullable=False, unique=True, index=True)
    source_name = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)

    # Text content (preserves partial RSS content)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)

    # Timestamps (always normalized to UTC)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    # Deduplication content hash (SHA-256)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)

    # Worker job queue state machine
    # States: pending -> processing -> completed / failed
    processing_status = Column(String(32), nullable=False, default="pending", index=True)
    processing_attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # AI outputs (prepared for Phases 3 & 4)
    summary = Column(Text, nullable=True)
    key_takeaways = Column(JSON, nullable=True)
    cluster_id = Column(String(64), nullable=True, index=True)

    # Additional raw feed attributes
    raw_metadata = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        Index("ix_articles_status_collected", "processing_status", "collected_at"),
        Index("ix_articles_category_published", "category", "published_at"),
    )

    def to_dict(self) -> dict:
        """Convert model instance to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "canonical_url": self.canonical_url,
            "source_name": self.source_name,
            "category": self.category,
            "description": self.description,
            "content": self.content,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "content_hash": self.content_hash,
            "processing_status": self.processing_status,
            "processing_attempts": self.processing_attempts,
            "error_message": self.error_message,
            "summary": self.summary,
            "key_takeaways": self.key_takeaways,
            "cluster_id": self.cluster_id,
            "raw_metadata": self.raw_metadata,
        }

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, title='{self.title[:30]}...', source='{self.source_name}')>"
