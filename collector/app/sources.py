from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class RSSFeedSource:
    name: str
    url: str
    category: str
    enabled: bool = True


# Preconfigured, reliable RSS feeds from established publishers
DEFAULT_RSS_SOURCES: List[RSSFeedSource] = [
    RSSFeedSource(
        name="BBC World News",
        url="https://feeds.bbci.co.uk/news/world/rss.xml",
        category="World",
    ),
    RSSFeedSource(
        name="Ars Technica",
        url="https://feeds.arstechnica.com/arstechnica/index",
        category="Technology",
    ),
    RSSFeedSource(
        name="BBC Business",
        url="https://feeds.bbci.co.uk/news/business/rss.xml",
        category="Business",
    ),
    RSSFeedSource(
        name="NPR News",
        url="https://feeds.npr.org/1001/rss.xml",
        category="General",
    ),
    RSSFeedSource(
        name="The Verge",
        url="https://www.theverge.com/rss/index.xml",
        category="Technology",
    ),
]


def get_active_sources() -> List[RSSFeedSource]:
    """Retrieve list of currently enabled RSS feed sources."""
    return [source for source in DEFAULT_RSS_SOURCES if source.enabled]
