import os
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
# pyrefly: ignore[missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore[missing-import]
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Load root .env file
root_dir = Path(__file__).resolve().parent.parent.parent.parent
env_path = root_dir / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()  # also check current working directory

# Base for declarative SQLAlchemy models
Base = declarative_base()


def get_sync_database_url() -> str:
    """Resolve sync database URL from environment with Supabase / PostgreSQL normalization."""
    raw_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_SYNC_URL") or os.getenv("DATABASE_URL")
    if not raw_url:
        user = os.getenv("POSTGRES_USER", "newsuser")
        pwd = os.getenv("POSTGRES_PASSWORD", "newspassword")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "newsdb")
        raw_url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"

    # Normalize driver scheme for sync SQLAlchemy using psycopg2
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgresql+asyncpg://"):
        raw_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

    # Supabase connection handling
    if "supabase" in raw_url.lower() and "sslmode=" not in raw_url:
        connector = "&" if "?" in raw_url else "?"
        raw_url = f"{raw_url}{connector}sslmode=require"

    return raw_url


SYNC_DATABASE_URL = get_sync_database_url()


def create_sync_engine(url: str | None = None):
    target_url = url or SYNC_DATABASE_URL
    engine_kwargs = {"pool_pre_ping": True}
    if "sqlite" in target_url:
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = 10
        engine_kwargs["max_overflow"] = 20
    return create_engine(target_url, **engine_kwargs)


sync_engine = create_sync_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
