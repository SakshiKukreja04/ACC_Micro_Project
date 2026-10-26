import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load root .env
root_dir = Path(__file__).resolve().parent.parent.parent
env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()


class WorkerSettings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database configuration
    SUPABASE_DB_URL: str | None = None
    DATABASE_SYNC_URL: str | None = None
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "newsuser"
    POSTGRES_PASSWORD: str = "newspassword"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "newsdb"

    # Job queue processing parameters
    WORKER_POLL_INTERVAL_SECONDS: int = 5
    WORKER_BATCH_SIZE: int = 10
    WORKER_MAX_RETRIES: int = 3
    WORKER_LEASE_TIMEOUT_SECONDS: int = 300  # 5 minutes lease before reclaiming abandoned jobs
    WORKER_METRICS_PORT: int = 9101

    def get_database_url(self) -> str:
        """Resolve database URL prioritizing Supabase then DATABASE_SYNC_URL."""
        raw_url = os.getenv("SUPABASE_DB_URL") or self.SUPABASE_DB_URL or os.getenv("DATABASE_SYNC_URL") or self.DATABASE_SYNC_URL or os.getenv("DATABASE_URL") or self.DATABASE_URL
        if not raw_url:
            raw_url = f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif raw_url.startswith("postgresql://"):
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif raw_url.startswith("postgresql+asyncpg://"):
            raw_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

        if "supabase" in raw_url.lower() and "sslmode=" not in raw_url:
            connector = "&" if "?" in raw_url else "?"
            raw_url = f"{raw_url}{connector}sslmode=require"

        return raw_url

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = WorkerSettings()
