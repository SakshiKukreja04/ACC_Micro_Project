import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.api import api_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.metrics import router as metrics_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.metrics import PrometheusMiddleware
from app.services.background import background_jobs

configure_logging("backend", settings.LOG_LEVEL)
logger = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} ({settings.ENVIRONMENT})")
    background_jobs.start()
    yield
    background_jobs.stop()
    logger.info("Backend shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Microservices REST API for the AI-Based News Aggregator & Summarizer: news feed, FAISS semantic search, "
        "RAG chatbot, Perspective Lens, personalised recommendations, insights, real-time events and full "
        "Prometheus observability."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Middleware (last added = outermost): metrics wrap everything, then gzip, then CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(PrometheusMiddleware)


# Global exception handler to prevent leaking internal stack traces or credentials
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# Root informational endpoint
@app.get("/", tags=["Root"])
def root():
    return {
        "message": "AI-Based News Aggregator and Summarizer API is running",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "endpoints": {
            "news_feed": "/api/news",
            "news_detail": "/api/news/{id}",
            "related_news": "/api/news/{id}/related",
            "perspective_lens": "/api/news/{id}/perspectives",
            "story_timeline": "/api/news/{id}/timeline",
            "translate": "/api/news/{id}/translate?lang=hi",
            "categories": "/api/categories",
            "keyword_search": "/api/search?q={query}",
            "semantic_search": "/api/search/semantic?q={query}",
            "trending": "/api/trending",
            "daily_briefing": "/api/briefing",
            "rag_chat": "/api/chat/ask",
            "article_explain": "/api/chat/explain/{id}",
            "for_you": "/api/me/for-you",
            "bookmarks": "/api/me/bookmarks",
            "insights": "/api/insights/overview",
            "trending_topics": "/api/insights/topics",
            "live_events": "/api/stream/events",
            "system_monitor": "/api/monitoring/overview",
        },
    }


# Health check at root /health
app.include_router(health_router)

# Prometheus metrics at /metrics
app.include_router(metrics_router)

# Mount all API endpoints under /api
app.include_router(api_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
