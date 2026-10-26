import logging
import math
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, asc, func, or_, select
from sqlalchemy.orm import Session
from app.core.redis_cache import cache_get, cache_set
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import (
    ArticleResponse,
    CategoryCount,
    PaginatedArticlesResponse,
    RelatedArticleItem,
    TrendingArticle,
)
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/news", tags=["News"])
logger = logging.getLogger("backend.api.news")


@router.get("", response_model=PaginatedArticlesResponse)
def get_news_feed(
    page: int = Query(1, ge=1, description="Page number starting at 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    category: Optional[str] = Query(None, description="Filter by topic category"),
    source: Optional[str] = Query(None, description="Filter by publisher name"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by processing status (pending, completed, failed)"),
    cluster_id: Optional[str] = Query(None, description="Filter by story cluster ID"),
    sentiment: Optional[str] = Query(None, pattern="^(positive|neutral|negative)$", description="Filter by sentiment"),
    from_date: Optional[datetime] = Query(None, description="Filter published after this timestamp"),
    to_date: Optional[datetime] = Query(None, description="Filter published before this timestamp"),
    sort_by: str = Query("published_at", pattern="^(published_at|collected_at)$", description="Sort field"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort direction"),
    db: Session = Depends(get_db),
):
    """
    Retrieve a paginated list of news articles with optional category, source, status, and date filters.
    """
    cache_key = f"news_feed:{category}:{source}:{status_filter}:{cluster_id}:{sentiment}:{from_date}:{to_date}:{sort_by}:{order}:{page}:{page_size}"
    cached_data = cache_get(cache_key)
    if cached_data:
        return PaginatedArticlesResponse(**cached_data)

    try:
        query = select(Article)

        # Apply filters
        if category:
            query = query.where(func.lower(Article.category) == category.lower().strip())
        if source:
            query = query.where(func.lower(Article.source_name) == source.lower().strip())
        if status_filter:
            query = query.where(Article.processing_status == status_filter.strip())
        if cluster_id:
            query = query.where(Article.cluster_id == cluster_id.strip())
        if sentiment:
            query = query.where(Article.sentiment == sentiment)
        if from_date:
            query = query.where(Article.published_at >= from_date)
        if to_date:
            query = query.where(Article.published_at <= to_date)

        # Count total matching records
        count_stmt = select(func.count()).select_from(query.subquery())
        total = db.scalar(count_stmt) or 0

        # Apply sorting
        sort_col = getattr(Article, sort_by)
        query = query.order_by(desc(sort_col) if order == "desc" else asc(sort_col))

        # Apply pagination
        offset = (page - 1) * page_size
        items = db.scalars(query.offset(offset).limit(page_size)).all()

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        result = PaginatedArticlesResponse(
            items=[ArticleResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
        cache_set(cache_key, result.model_dump(), expire_seconds=45)
        return result
    except Exception as e:
        logger.error(f"Error fetching news feed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve news feed from database",
        )


@router.post("/sync-embeddings")
def sync_embeddings(db: Session = Depends(get_db)):
    """
    Index any unindexed articles from PostgreSQL into the FAISS vector store.
    """
    try:
        store = get_vector_store()
        added = store.sync_from_database(db)
        return {
            "status": "success",
            "newly_indexed_articles": added,
            "total_vectors_in_index": store.index.ntotal,
        }
    except Exception as e:
        logger.error(f"Error synchronizing embeddings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synchronize vector embeddings: {str(e)}",
        )


@router.post("/cluster")
def cluster_news_stories(
    threshold: Optional[float] = Query(None, ge=0.2, le=1.0, description="Similarity threshold (default: calibrated)"),
    db: Session = Depends(get_db),
):
    """
    Cluster related news stories based on embedding cosine similarity.
    Assigns cluster_id to matched articles in PostgreSQL.
    """
    try:
        store = get_vector_store()
        threshold = threshold if threshold is not None else store.threshold("cluster")
        cluster_map = store.cluster_articles(db, threshold=threshold)
        return {
            "status": "success",
            "threshold": threshold,
            "clustered_articles_count": len(cluster_map),
            "clusters": cluster_map,
        }
    except Exception as e:
        logger.error(f"Error clustering news: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cluster news: {str(e)}",
        )


@router.get("/{article_id}", response_model=ArticleResponse)
def get_article_details(
    article_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve detailed information for a single article by its unique ID.
    Returns 404 if the article does not exist.
    """
    article = db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID '{article_id}' was not found",
        )
    return ArticleResponse.model_validate(article)


@router.post("/{article_id}/summarize")
def summarize_article_on_demand(
    article_id: str,
    db: Session = Depends(get_db),
):
    """
    On-demand AI summarization for an article.
    If the article already has a summary, returns it immediately.
    Otherwise, invokes the Groq LLM, updates Supabase PostgreSQL, and returns the generated summary.
    """
    from app.services.summarizer import generate_article_summary

    article = db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID '{article_id}' was not found",
        )

    # Return existing summary if already present
    if article.summary and article.key_takeaways:
        return {
            "id": article.id,
            "title": article.title,
            "summary": article.summary,
            "key_takeaways": article.key_takeaways,
            "sentiment": article.sentiment,
            "sentiment_score": article.sentiment_score,
            "grounding_score": article.grounding_score,
            "reading_time_minutes": article.reading_time_minutes,
            "cached": True,
        }

    # Generate summary with Groq LLM
    res = generate_article_summary(
        title=article.title,
        source_name=article.source_name,
        category=article.category,
        description=article.description,
        content=article.content,
    )

    if not res:
        desc = (article.description or article.content or "").strip()
        summary_text = desc[:280] + ("..." if len(desc) > 280 else "")
        res = {
            "summary": summary_text or f"Summary overview for {article.title}.",
            "key_takeaways": [
                f"Source: {article.source_name}",
                f"Category: {article.category}",
                "Full story available at publisher link",
            ],
        }

    from app.core.redis_cache import cache_delete_pattern
    from app.services.enrichment import enrich_article

    article.summary = res["summary"]
    article.key_takeaways = res["key_takeaways"]
    enrichment = enrich_article(article.title, article.description, article.content, article.summary)
    for field, value in enrichment.items():
        setattr(article, field, value)
    article.processing_status = "completed"
    article.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(article)

    # Invalidate feed cache so fresh summary appears in feeds
    cache_delete_pattern("news_feed:*")

    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "key_takeaways": article.key_takeaways,
        "sentiment": article.sentiment,
        "sentiment_score": article.sentiment_score,
        "grounding_score": article.grounding_score,
        "reading_time_minutes": article.reading_time_minutes,
        "cached": False,
    }


@router.get("/{article_id}/related", response_model=List[RelatedArticleItem])
def get_related_articles(
    article_id: str,
    top_k: int = Query(5, ge=1, le=20, description="Max number of related articles"),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum similarity (default: calibrated to the embedding model)"),
    db: Session = Depends(get_db),
):
    """
    Retrieve semantically related articles for a given article ID using FAISS vector search.
    """
    # Verify article exists
    article = db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID '{article_id}' was not found",
        )

    store = get_vector_store()
    # Ensure article is in index
    if article_id not in store.id_to_idx:
        store.add_articles([article.to_dict()])

    threshold = min_score if min_score is not None else store.threshold("related")
    related_matches = store.find_related(article_id, top_k=top_k, min_score=threshold)
    if not related_matches:
        return []

    # Fetch corresponding articles from DB in order of similarity
    matched_ids = [m[0] for m in related_matches]
    score_map = dict(related_matches)

    db_articles = db.scalars(select(Article).where(Article.id.in_(matched_ids))).all()
    art_dict = {a.id: a for a in db_articles}

    results: List[RelatedArticleItem] = []
    for art_id in matched_ids:
        if art_id in art_dict:
            item_data = ArticleResponse.model_validate(art_dict[art_id]).model_dump()
            item_data["similarity_score"] = round(score_map[art_id], 4)
            results.append(RelatedArticleItem(**item_data))

    return results
