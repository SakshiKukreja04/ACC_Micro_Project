import logging
from typing import Any, Dict, List, Optional, Set
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker, Session
from app.config import settings
from app.models import Article, Base

logger = logging.getLogger("collector.repository")


class ArticleRepository:
    """Handles database persistence and deduplication for news articles."""

    def __init__(self, db_url: Optional[str] = None, create_tables: bool = False):
        self.db_url = db_url or settings.get_database_url()
        engine_args = {"pool_pre_ping": True}
        if "sqlite" in self.db_url:
            engine_args["connect_args"] = {"check_same_thread": False}

        self.engine = create_engine(self.db_url, **engine_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        if create_tables:
            Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        """Create and return a new session."""
        return self.SessionLocal()

    def get_existing_urls_and_hashes(self, urls: List[str], hashes: List[str]) -> tuple[Set[str], Set[str]]:
        """Query database for URLs and content hashes that already exist."""
        if not urls and not hashes:
            return set(), set()

        existing_urls: Set[str] = set()
        existing_hashes: Set[str] = set()

        with self.get_session() as session:
            try:
                if urls:
                    url_stmt = select(Article.canonical_url).where(Article.canonical_url.in_(urls))
                    existing_urls = set(session.scalars(url_stmt).all())

                if hashes:
                    hash_stmt = select(Article.content_hash).where(Article.content_hash.in_(hashes))
                    existing_hashes = set(session.scalars(hash_stmt).all())
            except SQLAlchemyError as e:
                logger.error(f"Error querying existing articles: {e}")
                raise

        return existing_urls, existing_hashes

    def save_articles(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Persist a batch of normalized articles with idempotent duplicate prevention.
        Returns a dictionary with counts: {"inserted": count, "duplicates": count, "failed": count}.
        """
        if not articles:
            return {"inserted": 0, "duplicates": 0, "failed": 0}

        inserted_count = 0
        duplicate_count = 0
        failed_count = 0

        # Try fast PostgreSQL / Supabase dialect insert with ON CONFLICT DO NOTHING
        if self.engine.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            with self.get_session() as session:
                for article_data in articles:
                    try:
                        stmt = pg_insert(Article).values(**article_data).on_conflict_do_nothing(
                            index_elements=["canonical_url"]
                        )
                        res = session.execute(stmt)
                        if res.rowcount > 0:
                            inserted_count += 1
                        else:
                            duplicate_count += 1
                        session.commit()
                    except SQLAlchemyError as e:
                        session.rollback()
                        logger.error(f"Database error inserting article '{article_data.get('title')}': {e}")
                        failed_count += 1

            return {
                "inserted": inserted_count,
                "duplicates": duplicate_count,
                "failed": failed_count,
            }

        # Portable fallback (for SQLite, testing, etc.)
        candidate_urls = [a["canonical_url"] for a in articles if a.get("canonical_url")]
        candidate_hashes = [a["content_hash"] for a in articles if a.get("content_hash")]

        existing_urls, existing_hashes = self.get_existing_urls_and_hashes(candidate_urls, candidate_hashes)

        with self.get_session() as session:
            for article_data in articles:
                url = article_data.get("canonical_url")
                chash = article_data.get("content_hash")

                if url in existing_urls or chash in existing_hashes:
                    duplicate_count += 1
                    continue

                try:
                    article = Article(**article_data)
                    session.add(article)
                    session.commit()
                    inserted_count += 1
                    existing_urls.add(url)
                    existing_hashes.add(chash)
                except IntegrityError as e:
                    session.rollback()
                    logger.debug(f"Integrity duplicate caught on commit for {url}: {e}")
                    duplicate_count += 1
                except SQLAlchemyError as e:
                    session.rollback()
                    logger.error(f"Database error saving article '{url}': {e}")
                    failed_count += 1

        return {
            "inserted": inserted_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
        }

    def count_articles(self) -> int:
        """Count total stored articles."""
        with self.get_session() as session:
            return session.scalar(select(func.count()).select_from(Article)) or 0
