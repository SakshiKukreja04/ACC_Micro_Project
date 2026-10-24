import pytest
from app.fetcher import FeedFetcher
from app.normalizer import ArticleNormalizer
from app.repository import ArticleRepository
from app.scheduler import NewsCollectorService
from app.sources import RSSFeedSource
from tests.fixtures import VALID_RSS_XML, MALFORMED_RSS_XML


@pytest.fixture
def test_service(tmp_path, monkeypatch):
    """Creates a NewsCollectorService backed by an isolated test database and mocked feeds."""
    db_file = tmp_path / "pipeline_test.db"
    db_url = f"sqlite:///{db_file}"
    repo = ArticleRepository(db_url=db_url, create_tables=True)
    fetcher = FeedFetcher()
    normalizer = ArticleNormalizer()

    # Feed dispatch dictionary for mocked network responses
    feed_catalog = {
        "https://feeds.example.com/good": VALID_RSS_XML,
        "https://feeds.example.com/malformed": MALFORMED_RSS_XML,
        "https://feeds.example.com/broken_http": None,  # Simulates HTTP 500/timeout
    }

    def mock_fetch(url: str):
        return feed_catalog.get(url)

    monkeypatch.setattr(fetcher, "fetch_feed_xml", mock_fetch)

    service = NewsCollectorService(
        repository=repo,
        fetcher=fetcher,
        normalizer=normalizer,
    )
    return service, repo


def test_collection_pipeline_resilience_and_deduplication(test_service):
    service, repo = test_service

    # Define test sources: 1 good feed, 1 malformed feed, 1 broken HTTP feed
    sources = [
        RSSFeedSource(name="Valid Feed", url="https://feeds.example.com/good", category="Technology"),
        RSSFeedSource(name="Broken HTTP", url="https://feeds.example.com/broken_http", category="News"),
        RSSFeedSource(name="Malformed XML", url="https://feeds.example.com/malformed", category="Science"),
    ]

    # --- Run 1: Initial Collection ---
    summary1 = service.collect_once(sources=sources)

    # 1. Verify broken feeds did NOT crash collection of the good feed
    assert summary1["total_sources"] == 3
    assert summary1["total_inserted"] == 2
    assert summary1["total_duplicates"] == 0
    assert repo.count_articles() == 2

    # Verify per-source outcomes
    detail_map = {d["source"]: d for d in summary1["sources_detail"]}
    assert detail_map["Valid Feed"]["inserted"] == 2
    assert detail_map["Broken HTTP"]["inserted"] == 0
    assert detail_map["Malformed XML"]["inserted"] == 0

    # --- Run 2: Repeat Collection with same feeds ---
    summary2 = service.collect_once(sources=sources)

    # 2. Verify idempotency: 0 new insertions, 2 duplicates detected
    assert summary2["total_inserted"] == 0
    assert summary2["total_duplicates"] == 2
    assert repo.count_articles() == 2
