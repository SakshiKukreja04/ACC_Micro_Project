import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    Float,
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
    sentiment = Column(String(16), nullable=True, index=True)
    sentiment_score = Column(Float, nullable=True)
    grounding_score = Column(Float, nullable=True)
    reading_time_minutes = Column(Integer, nullable=True)
    keywords = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
        Index("ix_articles_status_collected", "processing_status", "collected_at"),
        Index("ix_articles_category_published", "category", "published_at"),
    )
