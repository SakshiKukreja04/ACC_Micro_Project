"""Pydantic schemas package."""
from app.schemas.article import (
    ArticleBase,
    ArticleResponse,
    PaginatedArticlesResponse,
    CategoryCount,
    TrendingArticle,
)

__all__ = [
    "ArticleBase",
    "ArticleResponse",
    "PaginatedArticlesResponse",
    "CategoryCount",
    "TrendingArticle",
]
