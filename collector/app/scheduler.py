import logging
import time
from typing import Any, Dict, List, Optional
from app.config import settings
from app.deduplication import DuplicateDetector
from app.fetcher import FeedFetcher
from app.normalizer import ArticleNormalizer
from app.repository import ArticleRepository
from app.sources import RSSFeedSource, get_active_sources

logger = logging.getLogger("collector.scheduler")


class NewsCollectorService:
    """Orchestrates fetching, normalizing, deduplicating and persisting RSS articles."""

    def __init__(
        self,
        repository: Optional[ArticleRepository] = None,
        fetcher: Optional[FeedFetcher] = None,
        normalizer: Optional[ArticleNormalizer] = None,
    ):
        self.repository = repository or ArticleRepository(create_tables=True)
        self.fetcher = fetcher or FeedFetcher()
        self.normalizer = normalizer or ArticleNormalizer()
        self.is_running = False

    def collect_source(self, source: RSSFeedSource) -> Dict[str, Any]:
        """Fetch, normalize and persist articles for a single RSS source."""
        source_result = {
            "source": source.name,
            "raw_entries": 0,
            "normalized": 0,
            "inserted": 0,
            "duplicates": 0,
            "failed": 0,
            "success": False,
        }

        try:
            # 1. Fetch raw entries
            entries = self.fetcher.fetch_source_entries(source)
            source_result["raw_entries"] = len(entries)

            if not entries:
                logger.warning(f"No entries collected from {source.name}")
                source_result["success"] = True
                return source_result

            # Limit per feed to avoid spike
            entries = entries[: settings.MAX_ARTICLES_PER_FEED]

            # 2. Normalize entries
            normalized_articles: List[Dict[str, Any]] = []
            for entry in entries:
                try:
                    norm = self.normalizer.normalize_entry(entry, source)
                    if norm:
                        normalized_articles.append(norm)
                except Exception as e:
                    logger.warning(f"Error normalizing entry from {source.name}: {e}")

            source_result["normalized"] = len(normalized_articles)

            # 3. In-batch deduplication
            deduped_articles = DuplicateDetector.deduplicate_batch(normalized_articles)

            # 4. Persist to database
            save_stats = self.repository.save_articles(deduped_articles)
            source_result["inserted"] = save_stats["inserted"]
            source_result["duplicates"] = save_stats["duplicates"]
            source_result["failed"] = save_stats["failed"]
            source_result["success"] = True

            logger.info(
                f"Completed {source.name}: {save_stats['inserted']} inserted, "
                f"{save_stats['duplicates']} duplicates, {save_stats['failed']} failed."
            )
        except Exception as e:
            logger.error(f"Unexpected error collecting feed {source.name} ({source.url}): {e}", exc_info=True)
            source_result["success"] = False

        return source_result

    def collect_once(self, sources: Optional[List[RSSFeedSource]] = None) -> Dict[str, Any]:
        """Run a single complete collection cycle across all active sources."""
        active_sources = sources or get_active_sources()
        logger.info(f"Starting news collection cycle across {len(active_sources)} sources.")

        summary = {
            "total_sources": len(active_sources),
            "successful_sources": 0,
            "failed_sources": 0,
            "total_raw_entries": 0,
            "total_inserted": 0,
            "total_duplicates": 0,
            "total_failed": 0,
            "sources_detail": [],
        }

        for source in active_sources:
            res = self.collect_source(source)
            summary["sources_detail"].append(res)
            summary["total_raw_entries"] += res["raw_entries"]
            summary["total_inserted"] += res["inserted"]
            summary["total_duplicates"] += res["duplicates"]
            summary["total_failed"] += res["failed"]

            if res["success"]:
                summary["successful_sources"] += 1
            else:
                summary["failed_sources"] += 1

        logger.info(
            f"Collection cycle complete: {summary['total_inserted']} new articles inserted, "
            f"{summary['total_duplicates']} duplicates skipped, "
            f"{summary['successful_sources']}/{summary['total_sources']} sources succeeded."
        )
        return summary

    def run_periodic(self, interval_seconds: Optional[int] = None) -> None:
        """Run periodic collection loop safely preventing overlapping cycles."""
        interval = interval_seconds or settings.COLLECTION_INTERVAL_SECONDS
        logger.info(f"Starting periodic news collector with {interval}s interval.")
        self.is_running = True

        while self.is_running:
            start_time = time.time()
            try:
                self.collect_once()
            except Exception as e:
                logger.error(f"Fatal unhandled error during collection cycle: {e}", exc_info=True)

            elapsed = time.time() - start_time
            sleep_time = max(1.0, interval - elapsed)
            logger.info(f"Cycle completed in {elapsed:.2f}s. Next collection in {sleep_time:.1f}s.")

            try:
                time.sleep(sleep_time)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Collector interrupted by user. Stopping.")
                self.is_running = False
                break
