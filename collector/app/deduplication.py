import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger("collector.deduplication")


class DuplicateDetector:
    """Detects and filters duplicate articles in-memory before database operations."""

    @staticmethod
    def deduplicate_batch(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out duplicates within the current in-memory collection batch."""
        seen_urls: Set[str] = set()
        seen_hashes: Set[str] = set()
        unique_articles: List[Dict[str, Any]] = []

        for article in articles:
            url = article.get("canonical_url")
            chash = article.get("content_hash")

            if not url or not chash:
                continue

            if url in seen_urls or chash in seen_hashes:
                logger.debug(f"Duplicate detected in current batch: {url}")
                continue

            seen_urls.add(url)
            seen_hashes.add(chash)
            unique_articles.append(article)

        return unique_articles

    @staticmethod
    def filter_existing(
        articles: List[Dict[str, Any]],
        existing_urls: Set[str],
        existing_hashes: Set[str]
    ) -> List[Dict[str, Any]]:
        """Filter out articles that already exist in the database."""
        new_articles: List[Dict[str, Any]] = []

        for article in articles:
            url = article.get("canonical_url")
            chash = article.get("content_hash")

            if url in existing_urls or chash in existing_hashes:
                logger.debug(f"Article already in database: {url}")
                continue

            new_articles.append(article)

        return new_articles
