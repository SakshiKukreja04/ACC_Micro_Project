import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        # Should return 200 when Supabase is connected
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_when_database_down(monkeypatch):
    from sqlalchemy.exc import OperationalError

    # Simulate database outage
    def mock_broken_session():
        raise OperationalError("Connection refused", {}, None)

    monkeypatch.setattr("app.api.endpoints.health.SessionLocal", mock_broken_session)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        # Must report 503 and degraded/unavailable status rather than crashing or falsely reporting healthy
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "unavailable"


@pytest.mark.asyncio
async def test_get_news_feed_pagination():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/news?page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["page"] == 1
        assert data["page_size"] == 5
        assert len(data["items"]) <= 5
        assert data["total"] > 0
        assert data["total_pages"] >= 1


@pytest.mark.asyncio
async def test_get_news_feed_filtering():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Filter by technology
        response = await client.get("/api/news?category=Technology&page_size=10")
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["category"].lower() == "technology"


@pytest.mark.asyncio
async def test_get_article_details():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Fetch an existing article from the feed
        feed_res = await client.get("/api/news?page=1&page_size=1")
        assert feed_res.status_code == 200
        items = feed_res.json()["items"]
        assert len(items) > 0
        article_id = items[0]["id"]

        # 2. Fetch specific article by ID
        detail_res = await client.get(f"/api/news/{article_id}")
        assert detail_res.status_code == 200
        article = detail_res.json()
        assert article["id"] == article_id
        assert "title" in article
        assert "canonical_url" in article


@pytest.mark.asyncio
async def test_get_article_not_found():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/news/non-existent-article-uuid")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_categories():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        first_cat = data[0]
        assert "category" in first_cat
        assert "article_count" in first_cat
        assert first_cat["article_count"] > 0


@pytest.mark.asyncio
async def test_search_articles():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Search for common term like 'the' or 'a' or 'in'
        response = await client.get("/api/search?q=the&page=1&page_size=5")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_search_empty_query():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/search?q=%20%20")
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_trending_articles():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/trending?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
        if data:
            assert "trending_score" in data[0]
            assert data[0]["trending_score"] > 0
            # Verify ordering
            scores = [item["trending_score"] for item in data]
            assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_prometheus_metrics():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/metrics")
        assert response.status_code == 200
        content = response.text
        assert "news_database_up" in content
        assert "news_faiss_vectors_total" in content
