import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metrics import (
    APP_INFO,
    ARTICLES_BY_SENTIMENT,
    ARTICLES_BY_STATUS,
    ARTICLES_INGESTED_LAST_HOUR,
    ARTICLES_TOTAL,
    AVG_GROUNDING_SCORE,
    BOOKMARKS_TOTAL,
    DATABASE_HEALTH,
    FAISS_VECTORS_TOTAL,
)
from app.core.redis_cache import redis_ping
from app.db.session import get_db
from app.models.article import Article, Bookmark
from app.services.vector_store import VectorStoreService

router = APIRouter(tags=["Monitoring & Metrics"])
logger = logging.getLogger("backend.api.metrics")

APP_INFO.info({"version": settings.VERSION, "environment": settings.ENVIRONMENT})


def refresh_data_gauges(db: Session) -> None:
    """Refresh the business / pipeline gauges from PostgreSQL (called on every Prometheus scrape)."""
    ARTICLES_TOTAL.clear()
    for cat, cnt in db.execute(select(Article.category, func.count(Article.id)).group_by(Article.category)).all():
        ARTICLES_TOTAL.labels(category=cat).set(cnt)

    ARTICLES_BY_STATUS.clear()
    for st in ("pending", "processing", "completed", "failed"):
        ARTICLES_BY_STATUS.labels(status=st).set(0)
    for st, cnt in db.execute(
        select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
    ).all():
        ARTICLES_BY_STATUS.labels(status=st).set(cnt)

    ARTICLES_BY_SENTIMENT.clear()
    for sent, cnt in db.execute(
        select(Article.sentiment, func.count(Article.id)).where(Article.sentiment.isnot(None)).group_by(Article.sentiment)
    ).all():
        ARTICLES_BY_SENTIMENT.labels(sentiment=sent).set(cnt)

    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    ARTICLES_INGESTED_LAST_HOUR.set(
        db.scalar(select(func.count(Article.id)).where(Article.collected_at >= hour_ago)) or 0
    )
    avg_ground = db.scalar(select(func.avg(Article.grounding_score)).where(Article.grounding_score.isnot(None)))
    AVG_GROUNDING_SCORE.set(float(avg_ground) if avg_ground is not None else 0)
    BOOKMARKS_TOTAL.set(db.scalar(select(func.count(Bookmark.id))) or 0)


@router.get("/metrics", include_in_schema=True)
def get_prometheus_metrics(db: Session = Depends(get_db)):
    """
    Prometheus scraping endpoint. Exposes HTTP RED metrics (rate, errors, duration), cache hit/miss,
    Groq LLM latency and outcomes, RAG retrieval sizes, FAISS index size, pipeline status counts,
    sentiment distribution and Fact-Grounding score.
    """
    try:
        refresh_data_gauges(db)
        DATABASE_HEALTH.set(1)
    except Exception as e:
        logger.warning(f"Metrics refresh failed: {e}")
        DATABASE_HEALTH.set(0)

    redis_ping()
    instance = VectorStoreService._instance
    if instance is not None:
        FAISS_VECTORS_TOTAL.set(instance.index.ntotal)

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
