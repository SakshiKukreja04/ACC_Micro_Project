import os
from fastapi import APIRouter, Depends, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.services.vector_store import get_vector_store

router = APIRouter(tags=["Monitoring & Metrics"])

# Prometheus Metrics Definitions
HTTP_REQUESTS_TOTAL = Counter(
    "news_http_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION = Histogram(
    "news_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)

ARTICLES_TOTAL = Gauge(
    "news_articles_total",
    "Total news articles stored in PostgreSQL",
    ["category"],
)

FAISS_VECTORS_TOTAL = Gauge(
    "news_faiss_vectors_total",
    "Total vector embeddings indexed in FAISS",
)

DATABASE_HEALTH = Gauge(
    "news_database_up",
    "Database connectivity health (1 = connected, 0 = degraded)",
)


@router.get("/metrics")
def get_prometheus_metrics(db: Session = Depends(get_db)):
    """
    Prometheus scraping endpoint exposing cloud monitoring metrics.
    Collects live article counts, FAISS vector count, and DB status.
    """
    try:
        # Check DB status
        db.execute(select(1))
        DATABASE_HEALTH.set(1)

        # Update article counts per category
        counts = db.execute(
            select(Article.category, func.count(Article.id)).group_by(Article.category)
        ).all()
        for cat, cnt in counts:
            ARTICLES_TOTAL.labels(category=cat).set(cnt)

        # Update FAISS vectors count
        store = get_vector_store()
        FAISS_VECTORS_TOTAL.set(store.index.ntotal)
    except Exception:
        DATABASE_HEALTH.set(0)

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
