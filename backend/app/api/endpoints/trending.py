import logging
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import ArticleResponse, TrendingArticle

router = APIRouter(prefix="/trending", tags=["Trending"])
logger = logging.getLogger("backend.api.trending")


def compute_trending(db: Session, limit: int = 10, category: Optional[str] = None) -> List[TrendingArticle]:
    """
    Deterministic trending score:
      recency       100 / (1 + hours_elapsed * 0.15)
      richness      +10 when the article has a substantial description
      AI-ready      +5 when an AI summary exists
      coverage      +12 per additional *distinct source* covering the same story cluster (max +36)
    """
    query = select(Article).order_by(desc(Article.published_at)).limit(200)
    if category:
        query = query.where(func.lower(Article.category) == category.lower().strip())
    candidates = db.scalars(query).all()

    cluster_sources: dict[str, set] = {}
    for art in candidates:
        if art.cluster_id:
            cluster_sources.setdefault(art.cluster_id, set()).add(art.source_name)

    now = datetime.now(timezone.utc)
    ranked: List[TrendingArticle] = []
    seen_clusters: Counter = Counter()
    for art in candidates:
        pub_date = art.published_at or art.collected_at
        pub_date = pub_date.replace(tzinfo=timezone.utc) if pub_date.tzinfo is None else pub_date.astimezone(timezone.utc)
        hours_elapsed = max(0.0, (now - pub_date).total_seconds() / 3600.0)

        score = 100.0 / (1.0 + hours_elapsed * 0.15)
        if art.description and len(art.description) > 50:
            score += 10.0
        if art.summary:
            score += 5.0
        if art.cluster_id:
            extra_sources = max(0, len(cluster_sources.get(art.cluster_id, ())) - 1)
            score += min(36.0, 12.0 * extra_sources) if extra_sources else 6.0

        data = ArticleResponse.model_validate(art).model_dump()
        ranked.append(TrendingArticle(**data, trending_score=round(score, 2)))

    ranked.sort(
        key=lambda x: (x.trending_score, x.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True
    )

    # Diversity: at most 2 stories from the same cluster in the trending list
    result: List[TrendingArticle] = []
    for item in ranked:
        if item.cluster_id:
            if seen_clusters[item.cluster_id] >= 2:
                continue
            seen_clusters[item.cluster_id] += 1
        result.append(item)
        if len(result) >= limit:
            break
    return result


@router.get("", response_model=List[TrendingArticle])
def get_trending_news(
    limit: int = Query(10, ge=1, le=50, description="Number of trending articles to return"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    db: Session = Depends(get_db),
):
    """
    Retrieve trending articles ranked by recency, content richness and multi-source coverage
    (stories reported by several publishers in the same FAISS/DSU cluster rank higher).
    """
    try:
        return compute_trending(db, limit, category)
    except Exception as e:
        logger.error(f"Error computing trending articles: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute trending articles",
        )
