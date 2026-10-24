import hashlib
import html
import logging
import re
import urllib.parse
from datetime import datetime, timezone
import time
from typing import Any, Dict, Optional
from dateutil import parser as date_parser
from app.sources import RSSFeedSource

logger = logging.getLogger("collector.normalizer")

# Query parameters to remove when creating canonical URLs
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "ref",
    "feedName",
    "feedType",
    "ncid",
    "gclid",
    "fbclid",
    "guccounter",
}


def clean_html_text(text: Optional[str]) -> str:
    """Remove HTML tags, decode HTML entities and normalize whitespace."""
    if not text:
        return ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&amp; &quot; &#39; etc.)
    clean = html.unescape(clean)
    # Collapse multiple whitespaces
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def canonicalize_url(raw_url: Optional[str]) -> Optional[str]:
    """Normalize and strip tracking query parameters from article URL."""
    if not raw_url:
        return None

    raw_url = raw_url.strip()
    if not raw_url:
        return None

    try:
        parsed = urllib.parse.urlparse(raw_url)
        # Ensure scheme
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower()

        # Filter out tracking query parameters
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        clean_pairs = [
            (k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS
        ]
        clean_query = urllib.parse.urlencode(clean_pairs)

        # Normalize path
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

        canonical = urllib.parse.urlunparse((
            scheme,
            netloc,
            path,
            parsed.params,
            clean_query,
            "",  # Remove URL fragment
        ))
        return canonical
    except Exception as e:
        logger.warning(f"Failed to canonicalize URL '{raw_url}': {e}")
        return raw_url


def parse_datetime_to_utc(entry: Dict[str, Any]) -> datetime:
    """Extract and normalize publication timestamp to timezone-aware UTC datetime."""
    # 1. Check feedparser's parsed time tuple
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        time_struct = entry.get(field)
        if time_struct:
            try:
                dt = datetime.fromtimestamp(time.mktime(time_struct), tz=timezone.utc)
                return dt
            except Exception:
                pass

    # 2. Check string date representations
    for field in ("published", "pubDate", "updated", "created", "date"):
        date_str = entry.get(field)
        if date_str and isinstance(date_str, str):
            try:
                dt = date_parser.parse(date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                pass

    # Default fallback to current UTC time if date is missing/invalid
    return datetime.now(timezone.utc)


def compute_content_hash(canonical_url: str, title: str) -> str:
    """Compute SHA-256 hash from canonical URL and title for duplicate detection."""
    payload = f"{canonical_url}|{title}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class ArticleNormalizer:
    """Normalizes raw feedparser entries into standardized dictionary schemas."""

    @staticmethod
    def normalize_entry(
        raw_entry: Dict[str, Any],
        source: RSSFeedSource
    ) -> Optional[Dict[str, Any]]:
        """Normalize a single raw RSS entry. Returns None if required fields are missing."""
        # 1. Title
        raw_title = raw_entry.get("title")
        title = clean_html_text(raw_title)
        if not title:
            logger.debug(f"Skipping entry from {source.name}: missing title")
            return None

        # 2. Canonical URL
        raw_url = raw_entry.get("link") or raw_entry.get("id")
        canonical_url = canonicalize_url(raw_url)
        if not canonical_url:
            logger.debug(f"Skipping entry '{title}': missing canonical URL")
            return None

        # 3. Description
        raw_description = raw_entry.get("summary") or raw_entry.get("description") or ""
        description = clean_html_text(raw_description)

        # 4. Content (check content field or content:encoded)
        content_text = ""
        content_items = raw_entry.get("content", [])
        if isinstance(content_items, list) and content_items:
            for item in content_items:
                if isinstance(item, dict) and item.get("value"):
                    content_text = clean_html_text(item["value"])
                    if content_text:
                        break

        if not content_text:
            content_text = description

        # 5. Category (use entry category or fall back to source category)
        entry_tags = raw_entry.get("tags") or []
        tag_names = [t.get("term") for t in entry_tags if isinstance(t, dict) and t.get("term")]
        category = tag_names[0] if tag_names else source.category

        # 6. Timestamps
        published_at = parse_datetime_to_utc(raw_entry)
        collected_at = datetime.now(timezone.utc)

        # 7. Content Hash
        content_hash = compute_content_hash(canonical_url, title)

        return {
            "title": title[:500],
            "canonical_url": canonical_url,
            "source_name": source.name,
            "category": category[:100],
            "description": description or None,
            "content": content_text or None,
            "published_at": published_at,
            "collected_at": collected_at,
            "content_hash": content_hash,
            "processing_status": "pending",
            "processing_attempts": 0,
            "error_message": None,
            "raw_metadata": {
                "author": raw_entry.get("author"),
                "feed_url": source.url,
                "tags": tag_names[:5],
            },
        }
