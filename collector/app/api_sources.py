"""
Optional JSON news-API sources (NewsAPI.org and GNews.io), matching the architecture's
"NewsAPI / GNews" box. Enabled only when an API key is configured. Each API article is converted
into a feedparser-like entry so the same normalizer, deduplication and storage path is reused.

Free tiers are small (≈100 requests/day), so the APIs are polled at most every
NEWS_API_INTERVAL_SECONDS (default 1 hour) regardless of the RSS cycle.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Tuple

import httpx

from app.sources import RSSFeedSource

logger = logging.getLogger("collector.api_sources")

_last_poll = {"newsapi": 0.0, "gnews": 0.0}


def _entry(title, url, description, content, published, author=None) -> Dict[str, Any]:
    return {
        "title": title,
        "link": url,
        "summary": description or "",
        "content": [{"value": content}] if content else [],
        "published": published,
        "author": author,
    }


def _due(name: str) -> bool:
    interval = int(os.getenv("NEWS_API_INTERVAL_SECONDS", "3600"))
    return time.time() - _last_poll[name] >= interval


def fetch_newsapi() -> Tuple[List[Tuple[Dict, RSSFeedSource]], bool]:
    key = os.getenv("NEWSAPI_KEY", "").strip()
    if not key or not _due("newsapi"):
        return [], True
    _last_poll["newsapi"] = time.time()
    params = {"apiKey": key, "pageSize": 40, "language": "en"}
    country = os.getenv("NEWS_API_COUNTRY", "in")
    params["country"] = country
    try:
        resp = httpx.get("https://newsapi.org/v2/top-headlines", params=params, timeout=15)
        resp.raise_for_status()
        out = []
        for a in resp.json().get("articles", []):
            if not a.get("title") or not a.get("url") or a.get("title") == "[Removed]":
                continue
            src_name = ((a.get("source") or {}).get("name") or "NewsAPI")[:90]
            out.append((
                _entry(a["title"], a["url"], a.get("description"), a.get("content"), a.get("publishedAt"), a.get("author")),
                RSSFeedSource(name=src_name, url="https://newsapi.org", category="General"),
            ))
        return out, True
    except Exception as e:
        logger.warning(f"NewsAPI fetch failed: {e}")
        return [], False


def fetch_gnews() -> Tuple[List[Tuple[Dict, RSSFeedSource]], bool]:
    key = os.getenv("GNEWS_API_KEY", "").strip()
    if not key or not _due("gnews"):
        return [], True
    _last_poll["gnews"] = time.time()
    params = {"apikey": key, "lang": "en", "max": 25, "country": os.getenv("NEWS_API_COUNTRY", "in")}
    try:
        resp = httpx.get("https://gnews.io/api/v4/top-headlines", params=params, timeout=15)
        resp.raise_for_status()
        out = []
        for a in resp.json().get("articles", []):
            if not a.get("title") or not a.get("url"):
                continue
            src_name = ((a.get("source") or {}).get("name") or "GNews")[:90]
            out.append((
                _entry(a["title"], a["url"], a.get("description"), a.get("content"), a.get("publishedAt")),
                RSSFeedSource(name=src_name, url="https://gnews.io", category="General"),
            ))
        return out, True
    except Exception as e:
        logger.warning(f"GNews fetch failed: {e}")
        return [], False


def api_sources_enabled() -> List[str]:
    return [n for n, k in (("NewsAPI", "NEWSAPI_KEY"), ("GNews", "GNEWS_API_KEY")) if os.getenv(k, "").strip()]
