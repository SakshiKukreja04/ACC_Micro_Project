import feedparser
from datetime import datetime, timezone
from app.normalizer import (
    ArticleNormalizer,
    canonicalize_url,
    clean_html_text,
    compute_content_hash,
)
from app.sources import RSSFeedSource
from tests.fixtures import VALID_RSS_XML, MISSING_FIELDS_RSS_XML


def test_clean_html_text():
    raw = "<p>This is <strong>bold</strong> &amp; clean.</p>"
    cleaned = clean_html_text(raw)
    assert cleaned == "This is bold & clean."

    assert clean_html_text(None) == ""
    assert clean_html_text("") == ""


def test_canonicalize_url():
    # Strips UTM params and fragments, normalizes trailing slash
    raw = "https://example.com/news/story/?utm_source=twitter&utm_medium=social#comments"
    canonical = canonicalize_url(raw)
    assert canonical == "https://example.com/news/story"

    # Preserves non-tracking query parameters
    raw_query = "https://example.com/item?id=12345&utm_campaign=daily"
    canonical_query = canonicalize_url(raw_query)
    assert canonical_query == "https://example.com/item?id=12345"


def test_compute_content_hash_deterministic():
    url = "https://example.com/article-1"
    title = "Groundbreaking Study in Clean Energy"
    hash1 = compute_content_hash(url, title)
    hash2 = compute_content_hash(url, title)
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 length


def test_normalize_valid_entries():
    source = RSSFeedSource(name="Tech Test", url="https://example.com/rss", category="Tech")
    parsed = feedparser.parse(VALID_RSS_XML)
    assert len(parsed.entries) == 2

    first_entry = parsed.entries[0]
    normalized = ArticleNormalizer.normalize_entry(first_entry, source)

    assert normalized is not None
    assert normalized["title"] == "New Quantum Computing Breakthrough Announced"
    assert normalized["canonical_url"] == "https://example.com/articles/quantum-breakthrough"
    assert "utm_source" not in normalized["canonical_url"]
    assert normalized["source_name"] == "Tech Test"
    assert normalized["category"] == "Quantum"
    assert "Researchers have achieved a major milestone" in normalized["description"]
    assert "Full article text explaining" in normalized["content"]
    assert normalized["processing_status"] == "pending"
    assert normalized["processing_attempts"] == 0
    assert isinstance(normalized["published_at"], datetime)
    assert normalized["published_at"].tzinfo == timezone.utc
    assert len(normalized["content_hash"]) == 64


def test_normalize_skips_missing_mandatory_fields():
    source = RSSFeedSource(name="Incomplete Feed", url="https://example.com/incomplete", category="General")
    parsed = feedparser.parse(MISSING_FIELDS_RSS_XML)

    # Entry 1 has missing title -> should be None
    norm1 = ArticleNormalizer.normalize_entry(parsed.entries[0], source)
    assert norm1 is None

    # Entry 2 has missing URL -> should be None
    norm2 = ArticleNormalizer.normalize_entry(parsed.entries[1], source)
    assert norm2 is None

    # Entry 3 has missing date -> should fall back gracefully to UTC datetime
    norm3 = ArticleNormalizer.normalize_entry(parsed.entries[2], source)
    assert norm3 is not None
    assert norm3["title"] == "Entry with Missing PubDate"
    assert isinstance(norm3["published_at"], datetime)
