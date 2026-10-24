import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from app.core.config import settings
from app.db.session import SessionLocal

router = APIRouter(tags=["System"])
logger = logging.getLogger("backend.api.health")


@router.get("/health")
def health_check(response: Response):
    """
    Check application health and verify live database connectivity to Supabase/PostgreSQL.
    Returns status 200 when fully healthy, or 503 when dependencies are unavailable.
    """
    db_connected = False
    db_error = None

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            db_connected = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        db_error = "Database connection failed"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if db_connected else "degraded",
        "service": "backend-api",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "connected" if db_connected else "unavailable",
        "error": db_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
