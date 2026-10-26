from fastapi import APIRouter
from app.api.endpoints import (
    briefing,
    categories,
    chat,
    health,
    insights,
    monitoring,
    news,
    personal,
    perspectives,
    search,
    stream,
    trending,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(perspectives.router)  # /news/{id}/perspectives|timeline|translate
api_router.include_router(news.router)
api_router.include_router(categories.router)
api_router.include_router(search.router)
api_router.include_router(trending.router)
api_router.include_router(chat.router)
api_router.include_router(personal.router)
api_router.include_router(insights.router)
api_router.include_router(briefing.router)
api_router.include_router(monitoring.router)
api_router.include_router(stream.router)
