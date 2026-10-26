"""
Tests for the features added on top of the original API:
enrichment (sentiment, Fact-Grounding, keywords, classifier), metrics middleware,
personalization, Perspective Lens, timeline, insights, briefing, SSE and the system monitor.

Integration tests run against the configured database (like test_api.py) and expect
articles to exist — run `python -m app.main --seed-demo` in collector/ on an empty DB.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.enrichment import (
    analyze_sentiment,
    classify_topic,
    enrich_article,
    extract_keywords,
    grounding_score,
    normalize_category,
)

CLIENT = {"X-Client-Id": "pytest-reader-0001"}


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ----------------------------------------------------------------------------- unit: enrichment
def test_sentiment_orders_framing():
    pos_label, pos = analyze_sentiment("Scientists celebrate breakthrough that improves recovery.", title="Breakthrough offers hope")
    neg_label, neg = analyze_sentiment("Critics warn the plan failed and losses deepen.", title="Crisis deepens as plan fails")
    assert pos_label == "positive" and neg_label == "negative"
    assert -1 <= neg < 0 < pos <= 1


def test_grounding_flags_unsupported_summary():
    source = "The Reserve Bank kept the repo rate unchanged at 6.5 percent on Friday, citing food inflation."
    faithful = grounding_score("The Reserve Bank kept the repo rate at 6.5 percent because of food inflation.", source)
    invented = grounding_score("The central bank announced a surprise cut and new cryptocurrency regulation.", source)
    assert faithful > 0.7
    assert invented < 0.4
    assert grounding_score("", source) is None


def test_keywords_and_classifier():
    kws = extract_keywords("The Reserve Bank of India kept the repo rate unchanged. Reserve Bank officials spoke.")
    assert "reserve bank" in kws
    assert classify_topic("Messi scores twice as team wins cup final") == "Sports"
    assert classify_topic("Sensex rallies as investors cheer earnings", "markets stocks") == "Business"
    assert normalize_category("tech") == "Technology"
    assert normalize_category("something odd") == "General"


def test_enrich_article_fields():
    data = enrich_article("Vaccine trial succeeds", "A vaccine trial met its goals.", None, "A vaccine trial met its goals.")
    assert set(data) == {"sentiment", "sentiment_score", "grounding_score", "reading_time_minutes", "keywords"}
    assert data["reading_time_minutes"] >= 1


# ----------------------------------------------------------------------------- monitoring
@pytest.mark.asyncio
async def test_request_id_and_templated_metrics():
    async with client() as c:
        feed = (await c.get("/api/news?page_size=1")).json()
        article_id = feed["items"][0]["id"]
        res = await c.get(f"/api/news/{article_id}", headers={"X-Request-ID": "trace-123"})
        assert res.headers["X-Request-ID"] == "trace-123"
        assert res.headers["X-Process-Time"].endswith("ms")
        metrics = (await c.get("/metrics")).text
        # Path parameters are templated so label cardinality stays bounded
        assert 'endpoint="/api/news/{article_id}"' in metrics
        assert article_id not in metrics.split("news_http_requests_total")[1][:2000]
        for name in ("news_articles_by_status", "news_cache_operations_total", "news_summary_grounding_score_avg"):
            assert name in metrics


@pytest.mark.asyncio
async def test_monitoring_overview_shape():
    async with client() as c:
        res = await c.get("/api/monitoring/overview")
        assert res.status_code == 200
        data = res.json()
        names = {s["name"] for s in data["services"]}
        assert {"Backend API", "PostgreSQL", "Redis", "AI Worker", "News Collector"} <= names
        assert data["overall_status"] in {"healthy", "degraded", "down"}
        assert {"pending", "completed"} <= set(data["pipeline"]["status_counts"])
        assert "p95_ms" in data["api"]


# ----------------------------------------------------------------------------- personalization
@pytest.mark.asyncio
async def test_bookmarks_history_for_you_and_forget():
    async with client() as c:
        await c.delete("/api/me", headers=CLIENT)
        items = (await c.get("/api/news?page_size=3")).json()["items"]
        a, b = items[0]["id"], items[1]["id"]

        assert (await c.get("/api/me/bookmarks")).status_code == 400  # header required

        assert (await c.put(f"/api/me/bookmarks/{a}", headers=CLIENT)).status_code == 201
        assert (await c.put(f"/api/me/bookmarks/{a}", headers=CLIENT)).status_code == 201  # idempotent
        assert (await c.get("/api/me/bookmarks/ids", headers=CLIENT)).json() == [a]

        res = await c.post("/api/me/events", headers=CLIENT, json={"article_id": b, "event_type": "view"})
        assert res.status_code == 201
        history = (await c.get("/api/me/history", headers=CLIENT)).json()
        assert history[0]["id"] == b

        rec = (await c.get("/api/me/for-you?limit=5", headers=CLIENT)).json()
        assert rec["personalized"] is True
        assert rec["profile"]["signals"] == 2
        assert all(item["id"] not in (a, b) for item in rec["items"])  # never recommend what was read

        bad = await c.put("/api/me/bookmarks/does-not-exist", headers=CLIENT)
        assert bad.status_code == 404

        wiped = (await c.delete("/api/me", headers=CLIENT)).json()
        assert wiped["deleted_bookmarks"] == 1 and wiped["deleted_events"] == 1
        cold = (await c.get("/api/me/for-you", headers=CLIENT)).json()
        assert cold["personalized"] is False


# ----------------------------------------------------------------------------- USPs
@pytest.mark.asyncio
async def test_perspective_lens_and_timeline():
    async with client() as c:
        article_id = (await c.get("/api/news?page_size=1")).json()["items"][0]["id"]
        lens = await c.get(f"/api/news/{article_id}/perspectives")
        assert lens.status_code == 200
        data = lens.json()
        assert data["outlets"][0]["article_id"] == article_id
        if data["available"]:
            assert len({o["source_name"] for o in data["outlets"]}) == len(data["outlets"])  # one per publisher
            assert 0 <= data["coverage_agreement_index"] <= 1
            assert "neutral_synthesis" in data["analysis"]

        tl = (await c.get(f"/api/news/{article_id}/timeline")).json()
        stamps = [e["published_at"] for e in tl["events"] if e["published_at"]]
        assert stamps == sorted(stamps)
        assert any(e["is_current"] for e in tl["events"])

        assert (await c.get("/api/news/missing-id/perspectives")).status_code == 404


@pytest.mark.asyncio
async def test_translate_validation():
    async with client() as c:
        article_id = (await c.get("/api/news?page_size=1")).json()["items"][0]["id"]
        assert (await c.get(f"/api/news/{article_id}/translate?lang=xx")).status_code == 400
        langs = (await c.get("/api/news/meta/languages")).json()
        assert {"code": "hi", "name": "Hindi"} in langs


# ----------------------------------------------------------------------------- insights & briefing
@pytest.mark.asyncio
async def test_insights_and_topics():
    async with client() as c:
        ov = (await c.get("/api/insights/overview?hours=48")).json()
        assert ov["totals"]["articles"] > 0
        assert sum(x["count"] for x in ov["category_distribution"]) == ov["totals"]["articles"]
        assert len(ov["volume_by_hour"]) >= 48
        topics = (await c.get("/api/insights/topics?hours=48")).json()
        for t in topics["topics"]:
            assert t["mentions"] >= 1 and t["spike_score"] > 0


@pytest.mark.asyncio
async def test_daily_briefing():
    async with client() as c:
        data = (await c.get("/api/briefing?refresh=true")).json()
        assert data["available"] is True
        assert data["headline"]
        refs = {s["ref"] for s in data["stories"]}
        assert all(h["ref"] in refs for h in data["highlights"] if h["ref"])


@pytest.mark.asyncio
async def test_sse_stream_snapshot():
    async with client() as c:
        res = await c.get("/api/stream/events?once=true")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert "event: hello" in res.text


@pytest.mark.asyncio
async def test_feed_sentiment_filter():
    async with client() as c:
        data = (await c.get("/api/news?sentiment=negative&page_size=50")).json()
        assert all(item["sentiment"] == "negative" for item in data["items"])
        assert (await c.get("/api/news?sentiment=angry")).status_code == 422
