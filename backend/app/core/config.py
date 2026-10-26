import os
from typing import List
# pyrefly: ignore[missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Based News Aggregator & Summarizer API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server configuration
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # CORS configuration
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Database
    POSTGRES_USER: str = "newsuser"
    POSTGRES_PASSWORD: str = "newspassword"
    POSTGRES_DB: str = "newsdb"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://newsuser:newspassword@postgres:5432/newsdb"
    DATABASE_SYNC_URL: str = "postgresql://newsuser:newspassword@postgres:5432/newsdb"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://redis:6379/0"

    # Background vector-index maintenance
    EMBED_SYNC_INTERVAL_SECONDS: int = 60
    CLUSTER_INTERVAL_SECONDS: int = 300
    ENABLE_BACKGROUND_JOBS: bool = True

    # Service discovery for the in-app System Monitor (internal Docker DNS names)
    WORKER_METRICS_URL: str = "http://worker:9101/metrics"
    COLLECTOR_METRICS_URL: str = "http://collector:9102/metrics"
    PROMETHEUS_INTERNAL_URL: str = "http://prometheus:9090"

    # Public URLs shown as links in the dashboard (as seen from the reader's browser)
    GRAFANA_PUBLIC_URL: str = "http://localhost:3000"
    PROMETHEUS_PUBLIC_URL: str = "http://localhost:9090"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
