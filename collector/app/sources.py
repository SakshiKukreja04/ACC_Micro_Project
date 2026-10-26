import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger("collector.sources")


@dataclass(frozen=True)
class RSSFeedSource:
    name: str
    url: str
    category: str
    enabled: bool = True
    # Dedicated topical feeds keep their category; general feeds are classified per article
    strict_category: bool = False


# Preconfigured, reliable RSS feeds from established publishers
DEFAULT_RSS_SOURCES: List[RSSFeedSource] = [
    RSSFeedSource(name="BBC World News", url="https://feeds.bbci.co.uk/news/world/rss.xml", category="World"),
    RSSFeedSource(name="Ars Technica", url="https://feeds.arstechnica.com/arstechnica/index", category="Technology", strict_category=True),
    RSSFeedSource(name="BBC Business", url="https://feeds.bbci.co.uk/news/business/rss.xml", category="Business", strict_category=True),
    RSSFeedSource(name="NPR News", url="https://feeds.npr.org/1001/rss.xml", category="General"),
    RSSFeedSource(name="The Verge", url="https://www.theverge.com/rss/index.xml", category="Technology", strict_category=True),
    RSSFeedSource(name="BBC Science", url="https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", category="Science", strict_category=True),
    RSSFeedSource(name="BBC Health", url="https://feeds.bbci.co.uk/news/health/rss.xml", category="Health", strict_category=True),
    RSSFeedSource(name="BBC Sport", url="https://feeds.bbci.co.uk/sport/rss.xml", category="Sports", strict_category=True),
    RSSFeedSource(name="BBC Entertainment", url="https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", category="Entertainment", strict_category=True),
    RSSFeedSource(name="The Hindu", url="https://www.thehindu.com/news/national/feeder/default.rss", category="India"),
    RSSFeedSource(name="Times of India", url="https://timesofindia.indiatimes.com/rssfeedstopstories.cms", category="India"),
    RSSFeedSource(name="Al Jazeera", url="https://www.aljazeera.com/xml/rss/all.xml", category="World"),
]


def _extra_sources_from_env() -> List[RSSFeedSource]:
    """
    EXTRA_RSS_FEEDS lets operators add feeds without code changes:
        EXTRA_RSS_FEEDS="Hacker News|https://hnrss.org/frontpage|Technology;NDTV|https://feeds.feedburner.com/ndtvnews-top-stories|India"
    """
    raw = os.getenv("EXTRA_RSS_FEEDS", "").strip()
    sources = []
    for chunk in filter(None, (c.strip() for c in raw.split(";"))):
        parts = [p.strip() for p in chunk.split("|")]
        if len(parts) >= 2 and parts[1].startswith("http"):
            sources.append(RSSFeedSource(name=parts[0], url=parts[1], category=parts[2] if len(parts) > 2 else "General"))
        else:
            logger.warning(f"Ignoring malformed EXTRA_RSS_FEEDS entry: {chunk}")
    return sources


def get_active_sources() -> List[RSSFeedSource]:
    """Retrieve list of currently enabled RSS feed sources (minus DISABLED_RSS_FEEDS names)."""
    disabled = {n.strip().lower() for n in os.getenv("DISABLED_RSS_FEEDS", "").split(",") if n.strip()}
    return [s for s in DEFAULT_RSS_SOURCES + _extra_sources_from_env() if s.enabled and s.name.lower() not in disabled]
