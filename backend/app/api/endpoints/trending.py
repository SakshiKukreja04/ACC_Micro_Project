import logging
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import TrendingArticle

router = APIRouter(prefix="/trending", tags=["Trending"])
logger = logging.getLogger("backend.api.trending")


@router.get("", response_model=List[TrendingArticle])
def get_trending_news(
    limit: int = Query(10, ge=1, le=50, description="Number of trending articles to return"),
    db: Session = Depends(get_db),
):
    """
    Retrieve trending articles ranked by a deterministic scoring algorithm.

    ### Trending Algorithm Specification:
    1. **Recency Factor**: Score decreases as article age increases using inverse decay:
       `recency_score = 100 / (1 + (hours_elapsed * 0.15))`
    2. **Content Richness**: Articles with full descriptions and content receive a completeness bonus (+10 pts).
    3. **Story Clustering (Future Phase)**: Stories with shared `cluster_id` receive a multi-source boost.
    4. **Deterministic Tie-breaker**: Ordered by `trending_score DESC`, then `published_at DESC`.
    """
    try:
        # Fetch candidate recent articles (most recent 100 articles)
        candidates = db.scalars(
            select(Article)
            .order_by(desc(Article.published_at))
            .limit(100)
        ).all()

        now = datetime.now(timezone.utc)
        ranked_items: List[TrendingArticle] = []

        for art in candidates:
            pub_date = art.published_at or art.collected_at
            if pub_date.tzinfo is None:
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            else:
                pub_date = pub_date.astimezone(timezone.utc)

            hours_elapsed = max(0.0, (now - pub_date).total_seconds() / 3600.0)

            # 1. Base recency score (decays over time)
            base_score = 100.0 / (1.0 + (hours_elapsed * 0.15))

            # 2. Completeness bonus
            bonus = 10.0 if (art.description and len(art.description) > 50) else 0.0

            # 3. Cluster bonus (if assigned in future phases)
            cluster_bonus = 15.0 if art.cluster_id else 0.0

            final_score = round(base_score + bonus + cluster_bonus, 2)

            ranked_items.append(
                TrendingArticle(
                    id=art.id,
                    title=art.title,
                    canonical_url=art.canonical_url,
                    source_name=art.source_name,
                    category=art.category,
                    description=art.description,
                    content=art.content,
                    published_at=art.published_at,
                    collected_at=art.collected_at,
                    content_hash=art.content_hash,
                    processing_status=art.processing_status,
                    processing_attempts=art.processing_attempts,
                    error_message=art.error_message,
                    summary=art.summary,
                    key_takeaways=art.key_takeaways,
                    cluster_id=art.cluster_id,
                    raw_metadata=art.raw_metadata,
                    trending_score=final_score,
                )
            )

        # Sort deterministically
        ranked_items.sort(key=lambda x: (x.trending_score, x.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
        return ranked_items[:limit]
    except Exception as e:
        logger.error(f"Error computing trending articles: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute trending articles",
        )
