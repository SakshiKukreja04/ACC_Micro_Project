from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ArticleBase(BaseModel):
    title: str = Field(..., description="Article headline")
    canonical_url: str = Field(..., description="Original article URL with tracking parameters stripped")
    source_name: str = Field(..., description="Publisher name")
    category: str = Field(..., description="Article topic category")
    description: Optional[str] = Field(None, description="Short summary/description from feed")
    content: Optional[str] = Field(None, description="Available article content or extended summary")
    published_at: Optional[datetime] = Field(None, description="UTC publication timestamp")


class ArticleResponse(ArticleBase):
    id: str = Field(..., description="Unique article ID")
    collected_at: datetime = Field(..., description="UTC timestamp when collected")
    content_hash: str = Field(..., description="SHA-256 content deduplication hash")
    processing_status: str = Field(..., description="AI processing status (pending, completed, failed)")
    processing_attempts: int = Field(0, description="Number of processing attempts")
    error_message: Optional[str] = Field(None, description="Failure description if processing failed")
    summary: Optional[str] = Field(None, description="AI-generated summary")
    key_takeaways: Optional[List[str] | Any] = Field(None, description="Key takeaway bullets")
    cluster_id: Optional[str] = Field(None, description="Story cluster ID for related news")
    raw_metadata: Optional[Dict[str, Any]] = Field(None, description="Raw feed metadata")

    model_config = ConfigDict(from_attributes=True)


class PaginatedArticlesResponse(BaseModel):
    items: List[ArticleResponse] = Field(..., description="List of articles for the current page")
    total: int = Field(..., description="Total matching articles across all pages")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")


class CategoryCount(BaseModel):
    category: str = Field(..., description="Category name")
    article_count: int = Field(..., description="Number of articles in this category")


class TrendingArticle(ArticleResponse):
    trending_score: float = Field(..., description="Deterministic recency & prominence ranking score")


class RelatedArticleItem(ArticleResponse):
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")


class SemanticSearchItem(ArticleResponse):
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 to 1.0)")


class SemanticSearchResponse(BaseModel):
    query: str = Field(..., description="Original search query")
    total: int = Field(..., description="Number of matching articles")
    items: List[SemanticSearchItem] = Field(..., description="List of semantically ranked articles")


class SourceArticleRef(BaseModel):
    id: str = Field(..., description="Article ID")
    title: str = Field(..., description="Article title")
    canonical_url: str = Field(..., description="Source article URL")
    source_name: str = Field(..., description="Source publisher name")
    similarity_score: float = Field(..., description="Relevance score to query")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500, description="User question to answer grounded in news")
    top_k: int = Field(4, ge=1, le=10, description="Number of context articles to retrieve")


class ChatResponse(BaseModel):
    question: str = Field(..., description="The user's question")
    answer: str = Field(..., description="AI response grounded strictly in retrieved news evidence")
    sources: List[SourceArticleRef] = Field(..., description="References to news articles cited")
