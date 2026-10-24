import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import CategoryCount

router = APIRouter(prefix="/categories", tags=["Categories"])
logger = logging.getLogger("backend.api.categories")


@router.get("", response_model=List[CategoryCount])
def get_categories(db: Session = Depends(get_db)):
    """
    Retrieve all distinct article categories along with the count of articles in each.
    Results are ordered by the number of articles descending.
    """
    try:
        stmt = (
            select(Article.category, func.count(Article.id).label("count"))
            .group_by(Article.category)
            .order_by(desc("count"))
        )
        results = db.execute(stmt).all()
        return [
            CategoryCount(category=row[0], article_count=row[1])
            for row in results
        ]
    except Exception as e:
        logger.error(f"Error fetching categories: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve categories from database",
        )
