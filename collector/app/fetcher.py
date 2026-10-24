import logging
from typing import Any, Dict, List, Optional
# pyrefly: ignore[missing-import]
import feedparser
import httpx
from app.config import settings
from app.sources import RSSFeedSource

logger = logging.getLogger("collector.fetcher")


class FeedFetcher:
    """Fetches and parses RSS/Atom feeds using HTTPX and Feedparser."""

    def __init__(self, timeout: int = settings.FEED_FETCH_TIMEOUT_SECONDS, user_agent: str = settings.USER_AGENT):
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/rdf+xml, application/atom+xml, application/xml, text/xml, */*",
        }

    def fetch_feed_xml(self, url: str) -> Optional[str]:
        """Fetch raw XML content with timeout and error handling."""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException as e:
            logger.warning(f"Timeout fetching feed {url}: {e}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error {e.response.status_code} fetching feed {url}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching feed {url}: {e}")
            return None

    def parse_feed_content(self, raw_content: str, source: RSSFeedSource) -> List[Dict[str, Any]]:
        """Parse raw XML content using feedparser."""
        try:
            parsed = feedparser.parse(raw_content)
            if parsed.bozo and not parsed.entries:
                logger.warning(f"Feed {source.name} returned malformed/unparseable XML: {parsed.bozo_exception}")
                return []
            return list(parsed.entries)
        except Exception as e:
            logger.warning(f"Failed to parse feed {source.name}: {e}")
            return []

    def fetch_source_entries(self, source: RSSFeedSource) -> List[Dict[str, Any]]:
        """Fetch and return parsed entries for a single RSS source."""
        logger.info(f"Fetching RSS feed from: {source.name} ({source.url})")
        raw_xml = self.fetch_feed_xml(source.url)
        if not raw_xml:
            logger.error(f"Failed to fetch content from {source.name}")
            return []

        entries = self.parse_feed_content(raw_xml, source)
        logger.info(f"Retrieved {len(entries)} raw entries from {source.name}")
        return entries
