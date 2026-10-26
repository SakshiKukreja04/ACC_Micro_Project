import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings
from app.models import Article, Base

logger = logging.getLogger("worker.queue")


@dataclass
class ArticleJob:
    """Detached data transfer object for an article claimed by the worker."""
    id: str
    title: str
    canonical_url: str
    source_name: str
    category: str
    description: Optional[str]
    content: Optional[str]
    processing_attempts: int
    published_at: Optional[datetime]


class JobQueue:
    """
    PostgreSQL-backed job state queue implementing concurrency-safe row-level locking
    with short claim transactions, lease timeouts, retries, and crash recovery.
    """

    def __init__(self, db_url: Optional[str] = None, create_tables: bool = False):
        self.db_url = db_url or settings.get_database_url()
        engine_args = {"pool_pre_ping": True}
        if "sqlite" in self.db_url:
            engine_args["connect_args"] = {"check_same_thread": False}
        else:
            engine_args["pool_size"] = 5
            engine_args["max_overflow"] = 10

        self.engine = create_engine(self.db_url, **engine_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        if create_tables:
            Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def recover_abandoned_jobs(self, lease_timeout_seconds: int = 300) -> int:
        """
        Recover jobs stuck in 'processing' state past their lease timeout due to worker crashes.
        Resets them to 'pending' with cleared lock timestamps.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=lease_timeout_seconds)
        recovered_count = 0

        with self.get_session() as session:
            try:
                stmt = (
                    select(Article)
                    .where(
                        Article.processing_status == "processing",
                        Article.locked_at <= cutoff,
                    )
                    .with_for_update(skip_locked=True)
                )
                abandoned_articles = session.scalars(stmt).all()

                for art in abandoned_articles:
                    stuck_since = art.locked_at
                    art.processing_status = "pending"
                    art.locked_at = None
                    art.error_message = f"Recovered from abandoned lease (stuck since {stuck_since})"
                    recovered_count += 1

                session.commit()
                if recovered_count > 0:
                    logger.warning(f"Recovered {recovered_count} abandoned jobs stuck in 'processing'")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recovering abandoned jobs: {e}")

        return recovered_count

    def claim_jobs(self, batch_size: int = 10) -> List[ArticleJob]:
        """
        Safely claim pending jobs using PostgreSQL FOR UPDATE SKIP LOCKED.
        Uses an ultra-short transaction: claims and commits before any external processing.
        """
        claimed_jobs: List[ArticleJob] = []
        now = datetime.now(timezone.utc)

        with self.get_session() as session:
            try:
                # Query pending jobs using concurrency-safe row-level locking
                stmt = (
                    select(Article)
                    .where(Article.processing_status == "pending")
                    .order_by(Article.collected_at.asc())
                    .limit(batch_size)
                )

                # FOR UPDATE SKIP LOCKED is supported on PostgreSQL / Supabase
                if "sqlite" not in self.db_url:
                    stmt = stmt.with_for_update(skip_locked=True)

                articles = session.scalars(stmt).all()

                for art in articles:
                    art.processing_status = "processing"
                    art.locked_at = now
                    art.processing_attempts += 1

                    claimed_jobs.append(
                        ArticleJob(
                            id=art.id,
                            title=art.title,
                            canonical_url=art.canonical_url,
                            source_name=art.source_name,
                            category=art.category,
                            description=art.description,
                            content=art.content,
                            processing_attempts=art.processing_attempts,
                            published_at=art.published_at,
                        )
                    )

                # Commit immediately to release the row lock and keep transaction time < 10ms
                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error claiming pending jobs: {e}")

        return claimed_jobs

    def mark_completed(self, article_id: str, results: Optional[dict] = None) -> bool:
        """Mark a job completed and save outputs."""
        with self.get_session() as session:
            try:
                art = session.scalar(select(Article).where(Article.id == article_id))
                if not art:
                    logger.error(f"Cannot complete job: article '{article_id}' not found")
                    return False

                art.processing_status = "completed"
                art.completed_at = datetime.now(timezone.utc)
                art.locked_at = None
                art.error_message = None

                if results:
                    for field in (
                        "summary", "key_takeaways", "sentiment", "sentiment_score",
                        "grounding_score", "reading_time_minutes", "keywords",
                    ):
                        if field in results:
                            setattr(art, field, results[field])
                    if results.get("cluster_id"):
                        art.cluster_id = results["cluster_id"]
                    if results.get("category"):
                        art.category = results["category"]

                session.commit()
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error marking job '{article_id}' as completed: {e}")
                return False

    def status_counts(self) -> dict:
        """Number of articles per processing status (queue depth)."""
        from sqlalchemy import func

        counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        with self.get_session() as session:
            try:
                for st, cnt in session.execute(
                    select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
                ).all():
                    counts[st] = cnt
            except SQLAlchemyError as e:
                logger.error(f"Error reading queue depth: {e}")
        return counts

    def mark_failed(self, article_id: str, error_message: str, max_retries: int = 3) -> bool:
        """Record job failure and retry or mark permanently failed according to bounded retry policy."""
        with self.get_session() as session:
            try:
                art = session.scalar(select(Article).where(Article.id == article_id))
                if not art:
                    logger.error(f"Cannot fail job: article '{article_id}' not found")
                    return False

                art.locked_at = None
                art.error_message = str(error_message)[:500]

                if art.processing_attempts >= max_retries:
                    art.processing_status = "failed"
                    logger.warning(
                        f"Job '{article_id}' permanently failed after {art.processing_attempts} attempts: {error_message}"
                    )
                else:
                    # Return to pending for bounded retry
                    art.processing_status = "pending"
                    logger.info(
                        f"Job '{article_id}' failed attempt {art.processing_attempts}/{max_retries}. Returned to pending."
                    )

                session.commit()
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Error recording failure for job '{article_id}': {e}")
                return False
