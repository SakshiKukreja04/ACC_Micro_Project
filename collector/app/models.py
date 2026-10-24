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
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return uuid.uuid4().hex


class Article(Base):
    __tablename__ = "articles"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(500), nullable=False)
    canonical_url = Column(Text, nullable=False, unique=True, index=True)
    source_name = Column(String(100), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    collected_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    processing_status = Column(String(32), nullable=False, default="pending", index=True)
    processing_attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    key_takeaways = Column(JSON, nullable=True)
    cluster_id = Column(String(64), nullable=True, index=True)
    raw_metadata = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        Index("ix_articles_status_collected", "processing_status", "collected_at"),
        Index("ix_articles_category_published", "category", "published_at"),
    )

    def to_dict(self) -> dict:
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
        }
