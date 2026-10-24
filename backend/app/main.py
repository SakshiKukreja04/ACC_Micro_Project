import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.api import api_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.metrics import router as metrics_router
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [Backend] %(message)s",
)
logger = logging.getLogger("backend")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Asynchronous Microservices REST API for AI-Based News Aggregator & Summarizer with Supabase PostgreSQL integration.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "database": "Supabase PostgreSQL",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "health": "/health",
            "news_feed": "/api/news",
            "news_detail": "/api/news/{id}",
            "related_news": "/api/news/{id}/related",
            "categories": "/api/categories",
            "keyword_search": "/api/search?q={query}",
            "semantic_search": "/api/search/semantic?q={query}",
            "trending": "/api/trending",
            "rag_chat": "/api/chat/ask",
            "article_explain": "/api/chat/explain/{id}",
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
