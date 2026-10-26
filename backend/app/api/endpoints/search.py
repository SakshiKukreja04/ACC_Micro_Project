import logging
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import (
    ArticleResponse,
    PaginatedArticlesResponse,
    SemanticSearchItem,
    SemanticSearchResponse,
)
from app.core.metrics import SEMANTIC_SEARCHES
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/search", tags=["Search"])
logger = logging.getLogger("backend.api.search")


@router.get("", response_model=PaginatedArticlesResponse)
def search_articles(
    q: str = Query(..., min_length=1, max_length=150, description="Search keyword or phrase"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    db: Session = Depends(get_db),
):
    """
    Search articles by keyword across title, description, and available content.
    Uses parameterized pattern matching to ensure SQL-injection safety.
    """
    clean_q = q.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query 'q' must contain non-whitespace characters",
        )

    try:
        search_pattern = f"%{clean_q}%"
        query = select(Article).where(
            or_(
                Article.title.ilike(search_pattern),
                Article.description.ilike(search_pattern),
                Article.content.ilike(search_pattern),
            )
        )

        if category:
            query = query.where(func.lower(Article.category) == category.lower().strip())

        # Total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total = db.scalar(count_stmt) or 0

        # Sort by publication recency
        query = query.order_by(desc(Article.published_at))

        # Pagination
        offset = (page - 1) * page_size
        items = db.scalars(query.offset(offset).limit(page_size)).all()

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return PaginatedArticlesResponse(
            items=[ArticleResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    except Exception as e:
        logger.error(f"Error executing search query '{clean_q}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute search query against database",
        )


@router.get("/semantic", response_model=SemanticSearchResponse)
def semantic_search_articles(
    q: str = Query(..., min_length=2, max_length=200, description="Natural language semantic search query"),
    top_k: int = Query(10, ge=1, le=50, description="Maximum number of relevant results"),
    min_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum cosine similarity (default: calibrated)"),
    category: Optional[str] = Query(None, description="Optional category filter"),
    db: Session = Depends(get_db),
):
    """
    Perform semantic vector search using FAISS embeddings.
    Retrieves conceptually relevant articles even if exact keyword matches are absent.
    """
    clean_q = q.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query 'q' must contain valid text",
        )

    SEMANTIC_SEARCHES.inc()
    store = get_vector_store()
    # If the store is empty, sync from DB
    if store.index.ntotal == 0:
        store.sync_from_database(db)

    threshold = min_score if min_score is not None else store.threshold("search")
    matches = store.search(clean_q, top_k=top_k * 2 if category else top_k, min_score=threshold)
    if not matches:
        return SemanticSearchResponse(query=clean_q, total=0, items=[])

    matched_ids = [m[0] for m in matches]
    score_map = dict(matches)

    query_db = select(Article).where(Article.id.in_(matched_ids))
    if category:
        query_db = query_db.where(func.lower(Article.category) == category.lower().strip())

    articles = db.scalars(query_db).all()
    art_dict = {a.id: a for a in articles}

    items: List[SemanticSearchItem] = []
    for art_id in matched_ids:
        if art_id in art_dict:
            data = ArticleResponse.model_validate(art_dict[art_id]).model_dump()
            data["similarity_score"] = round(score_map[art_id], 4)
            items.append(SemanticSearchItem(**data))
            if len(items) >= top_k:
                break

    return SemanticSearchResponse(query=clean_q, total=len(items), items=items)
