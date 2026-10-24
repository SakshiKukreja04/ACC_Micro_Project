import httpx
import pytest
from app.fetcher import FeedFetcher
from app.sources import RSSFeedSource
from tests.fixtures import VALID_RSS_XML, MALFORMED_RSS_XML


def test_parse_valid_feed():
    source = RSSFeedSource(name="Valid Source", url="https://example.com/rss", category="Tech")
    fetcher = FeedFetcher()
    entries = fetcher.parse_feed_content(VALID_RSS_XML, source)
    assert len(entries) == 2
    assert entries[0]["title"] == "New Quantum Computing Breakthrough Announced"


def test_parse_malformed_feed_does_not_crash():
    source = RSSFeedSource(name="Malformed Source", url="https://example.com/broken", category="Tech")
    fetcher = FeedFetcher()
    # Feedparser handles malformed feeds gracefully by either fixing or setting bozo
    entries = fetcher.parse_feed_content(MALFORMED_RSS_XML, source)
    assert isinstance(entries, list)


def test_fetch_handles_timeout_gracefully(monkeypatch):
    source = RSSFeedSource(name="Timeout Source", url="https://example.com/timeout", category="Tech")
    fetcher = FeedFetcher()

    def mock_get(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    result = fetcher.fetch_feed_xml(source.url)
    assert result is None


def test_fetch_handles_http_error_gracefully(monkeypatch):
    source = RSSFeedSource(name="Error Source", url="https://example.com/404", category="Tech")
    fetcher = FeedFetcher()

    def mock_get(*args, **kwargs):
        request = httpx.Request("GET", source.url)
        response = httpx.Response(status_code=404, request=request)
        raise httpx.HTTPStatusError("404 Not Found", request=request, response=response)

    monkeypatch.setattr(httpx.Client, "get", mock_get)
    result = fetcher.fetch_feed_xml(source.url)
    assert result is None
