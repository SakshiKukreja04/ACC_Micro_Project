import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.deduplication import DuplicateDetector
from app.fetcher import FeedFetcher
from app.metrics import (
    CYCLE_DURATION,
    DUPLICATES,
    FEED_ERRORS,
    FETCH_DURATION,
    FETCHED,
    INSERTED,
    LAST_CYCLE,
    LAST_SUCCESS,
    SOURCES_CONFIGURED,
)
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

    def _persist(self, source_name: str, normalized: List[Dict[str, Any]], result: Dict[str, Any]) -> None:
        deduped = DuplicateDetector.deduplicate_batch(normalized)
        save_stats = self.repository.save_articles(deduped)
        result["inserted"] += save_stats["inserted"]
        result["duplicates"] += save_stats["duplicates"] + (len(normalized) - len(deduped))
        result["failed"] += save_stats["failed"]
        INSERTED.labels(source=source_name).inc(save_stats["inserted"])
        DUPLICATES.labels(source=source_name).inc(save_stats["duplicates"] + (len(normalized) - len(deduped)))

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

        # Touch labelled series so dashboards show 0 instead of "no data" for new sources
        for counter in (FETCHED, INSERTED, DUPLICATES, FEED_ERRORS):
            counter.labels(source=source.name)

        started = time.perf_counter()
        try:
            entries, ok = self.fetcher.fetch_source_with_status(source)
            FETCH_DURATION.labels(source=source.name).observe(time.perf_counter() - started)
            source_result["raw_entries"] = len(entries)
            FETCHED.labels(source=source.name).inc(len(entries))

            if not ok:
                FEED_ERRORS.labels(source=source.name).inc()
                logger.warning(f"Feed unavailable: {source.name}")
                return source_result

            LAST_SUCCESS.labels(source=source.name).set_to_current_time()
            if not entries:
                logger.warning(f"No entries collected from {source.name}")
                source_result["success"] = True
                return source_result

            entries = entries[: settings.MAX_ARTICLES_PER_FEED]
            normalized_articles: List[Dict[str, Any]] = []
            for entry in entries:
                try:
                    norm = self.normalizer.normalize_entry(entry, source)
                    if norm:
                        normalized_articles.append(norm)
                except Exception as e:
                    logger.warning(f"Error normalizing entry from {source.name}: {e}")

            source_result["normalized"] = len(normalized_articles)
            self._persist(source.name, normalized_articles, source_result)
            source_result["success"] = True

            logger.info(
                f"Completed {source.name}: {source_result['inserted']} inserted, "
                f"{source_result['duplicates']} duplicates, {source_result['failed']} failed."
            )
        except Exception as e:
            FEED_ERRORS.labels(source=source.name).inc()
            logger.error(f"Unexpected error collecting feed {source.name} ({source.url}): {e}", exc_info=True)
            source_result["success"] = False

        return source_result

    def collect_api_sources(self) -> List[Dict[str, Any]]:
        """Collect from optional NewsAPI / GNews sources (only when API keys are configured)."""
        from app.api_sources import fetch_gnews, fetch_newsapi

        results = []
        for label, fn in (("NewsAPI", fetch_newsapi), ("GNews", fetch_gnews)):
            pairs: List[Tuple[Dict, RSSFeedSource]]
            pairs, ok = fn()
            if not ok:
                FEED_ERRORS.labels(source=label).inc()
                results.append({"source": label, "raw_entries": 0, "normalized": 0, "inserted": 0,
                                "duplicates": 0, "failed": 0, "success": False})
                continue
            if not pairs:
                continue
            LAST_SUCCESS.labels(source=label).set_to_current_time()
            FETCHED.labels(source=label).inc(len(pairs))
            result = {"source": label, "raw_entries": len(pairs), "normalized": 0, "inserted": 0,
                      "duplicates": 0, "failed": 0, "success": True}
            normalized = []
            for entry, src in pairs:
                norm = self.normalizer.normalize_entry(entry, src)
                if norm:
                    norm["raw_metadata"]["via"] = label
                    normalized.append(norm)
            result["normalized"] = len(normalized)
            self._persist(label, normalized, result)
            results.append(result)
        return results

    def collect_once(self, sources: Optional[List[RSSFeedSource]] = None) -> Dict[str, Any]:
        """Run a single complete collection cycle across all active sources."""
        cycle_start = time.perf_counter()
        active_sources = sources or get_active_sources()
        SOURCES_CONFIGURED.set(len(active_sources))
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

        results = [self.collect_source(source) for source in active_sources]
        if sources is None:
            results.extend(self.collect_api_sources())

        for res in results:
            summary["sources_detail"].append(res)
            summary["total_raw_entries"] += res["raw_entries"]
            summary["total_inserted"] += res["inserted"]
            summary["total_duplicates"] += res["duplicates"]
            summary["total_failed"] += res["failed"]
            if res["success"]:
                summary["successful_sources"] += 1
            else:
                summary["failed_sources"] += 1

        CYCLE_DURATION.observe(time.perf_counter() - cycle_start)
        LAST_CYCLE.set_to_current_time()
        logger.info(
            f"Collection cycle complete: {summary['total_inserted']} new articles inserted, "
            f"{summary['total_duplicates']} duplicates skipped, "
            f"{summary['successful_sources']}/{len(results)} sources succeeded."
        )
        return summary

    def maybe_seed_demo(self, summary: Dict[str, Any]) -> int:
        """
        SEED_DEMO_DATA=auto (default): if the database is still empty after a collection cycle
        (e.g. a campus network blocks the feeds), load clearly-labelled offline demo articles so
        every feature can still be demonstrated. SEED_DEMO_DATA=true always seeds; false never.
        """
        mode = os.getenv("SEED_DEMO_DATA", "auto").lower()
        if mode in ("false", "0", "no", "off"):
            return 0
        if mode == "auto" and self.repository.count_articles() > 0:
            return 0
        from app.demo_seed import seed_demo_articles

        inserted = seed_demo_articles(self.repository)
        if inserted:
            logger.warning(
                f"Seeded {inserted} offline DEMO articles (sources prefixed 'Demo'). "
                "Set SEED_DEMO_DATA=false to disable."
            )
        return inserted

    def run_periodic(self, interval_seconds: Optional[int] = None) -> None:
        """Run periodic collection loop safely preventing overlapping cycles."""
        interval = interval_seconds or settings.COLLECTION_INTERVAL_SECONDS
        logger.info(f"Starting periodic news collector with {interval}s interval.")
        self.is_running = True
        first_cycle = True

        while self.is_running:
            start_time = time.time()
            try:
                summary = self.collect_once()
                if first_cycle:
                    self.maybe_seed_demo(summary)
                    first_cycle = False
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
