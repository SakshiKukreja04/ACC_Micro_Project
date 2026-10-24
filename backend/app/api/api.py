from fastapi import APIRouter
from app.api.endpoints import categories, chat, health, news, search, trending

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(news.router)
api_router.include_router(categories.router)
api_router.include_router(search.router)
api_router.include_router(trending.router)
api_router.include_router(chat.router)
