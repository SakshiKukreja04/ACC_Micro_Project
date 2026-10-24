import os
import tempfile
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.article import Article
from app.services.vector_store import VectorStoreService, get_vector_store

temp_db_path = os.path.join(tempfile.gettempdir(), "test_vector_store.db")
if os.path.exists(temp_db_path):
    try:
        os.remove(temp_db_path)
    except Exception:
        pass

SQLALCHEMY_DATABASE_URL = f"sqlite:///{temp_db_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    articles = [
        Article(
            id="art-ai-1",
            title="Google DeepMind announces breakthrough in quantum computing algorithms",
            canonical_url="https://news.example.com/deepmind-quantum",
            source_name="Tech Journal",
            category="Technology",
            description="A novel algorithmic approach scales fault-tolerant quantum error correction.",
            content="Researchers have developed a quantum simulator that speeds up computations by 100x.",
            content_hash="hash-ai-1",
            processing_status="completed",
            summary="DeepMind announced a major quantum error correction algorithm.",
            key_takeaways=["100x speedup in quantum simulation", "Fault-tolerant scaling"],
        ),
        Article(
            id="art-ai-2",
            title="Quantum computers achieve quantum supremacy in chemical synthesis",
            canonical_url="https://news.example.com/quantum-chemistry",
            source_name="Science Daily",
            category="Technology",
            description="Quantum algorithm models complex molecular bonds faster than classical supercomputers.",
            content="Chemists used quantum processors to simulate catalyst reactions accurately.",
            content_hash="hash-ai-2",
            processing_status="completed",
            summary="Quantum processors simulate molecular bonds at unprecedented speeds.",
            key_takeaways=["Catalyst reaction simulation", "Supremacy over classical supercomputers"],
        ),
        Article(
            id="art-biz-1",
            title="Central Bank raises interest rates to curb persistent inflation",
            canonical_url="https://news.example.com/central-bank-rates",
            source_name="Financial Times",
            category="Business",
            description="Policymakers increased benchmark rates by 25 basis points amid rising consumer prices.",
            content="Markets reacted with volatility as bond yields spiked following the rate hike.",
            content_hash="hash-biz-1",
            processing_status="completed",
            summary="Central Bank increased benchmark rates by 25 bps.",
            key_takeaways=["25 bps rate increase", "Bond market volatility"],
        ),
    ]
    for a in articles:
        db.add(a)
    db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    if os.path.exists(temp_db_path):
        try:
            os.remove(temp_db_path)
        except Exception:
            pass


def test_vector_store_initialization_and_indexing():
    """Verify VectorStore initializes, computes embeddings, and persists to disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStoreService(storage_dir=tmpdir)
        assert store.index.ntotal == 0

        articles = [
            {"id": "test-1", "title": "Breakthrough in AI models", "description": "Large language models improve reasoning"},
            {"id": "test-2", "title": "Stock market hits record high", "description": "Wall street rallies on tech earnings"},
        ]

        added = store.add_articles(articles)
        assert added == 2
        assert store.index.ntotal == 2

        # Verify duplicate prevention: adding the same articles again adds 0
        added_repeat = store.add_articles(articles)
        assert added_repeat == 0
        assert store.index.ntotal == 2

        # Verify reloading index from disk preserves data
        reloaded_store = VectorStoreService(storage_dir=tmpdir)
        assert reloaded_store.index.ntotal == 2
        assert "test-1" in reloaded_store.id_to_idx
        assert "test-2" in reloaded_store.id_to_idx


def test_vector_store_semantic_search():
    """Verify semantic search ranks semantically related articles higher."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStoreService(storage_dir=tmpdir)
        articles = [
            {"id": "ai-doc", "title": "Autonomous AI agents solve complex reasoning tasks", "description": "AI models automate programming workflows"},
            {"id": "food-doc", "title": "Organic farming practices produce higher yield tomatoes", "description": "Agriculture experts analyze soil nutrients"},
        ]
        store.add_articles(articles)

        results = store.search("artificial intelligence software engineer", top_k=2)
        assert len(results) >= 1
        top_match_id, top_score = results[0]
        assert top_match_id == "ai-doc"
        assert top_score > 0.0


def test_vector_store_related_articles():
    """Verify related articles excludes query article and finds closest neighbor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = VectorStoreService(storage_dir=tmpdir)
        articles = [
            {"id": "q1", "title": "Quantum computing advances in qubit stability", "description": "Superconducting qubits show longer coherence times"},
            {"id": "q2", "title": "New error mitigation methods for quantum processors", "description": "Researchers stabilize superconducting qubits"},
            {"id": "sports", "title": "World Cup championship finals preview", "description": "Football teams prepare for stadium match"},
        ]
        store.add_articles(articles)

        related = store.find_related("q1", top_k=2, min_score=0.2)
        assert len(related) >= 1
        # Target article q1 must NOT be in related matches
        related_ids = [r[0] for r in related]
        assert "q1" not in related_ids
        # q2 should be top related
        assert related_ids[0] == "q2"


@pytest.mark.asyncio
async def test_api_sync_embeddings_and_search():
    """Test FastAPI endpoints for embedding sync, semantic search, and related news."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Sync embeddings
        sync_resp = await client.post("/api/news/sync-embeddings")
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["status"] == "success"
        assert sync_data["total_vectors_in_index"] >= 3

        # 2. Semantic search
        search_resp = await client.get("/api/search/semantic?q=quantum+physics+and+algorithms&top_k=2")
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["total"] >= 1
        top_result = search_data["items"][0]
        assert "quantum" in top_result["title"].lower()

        # 3. Related news endpoint
        related_resp = await client.get("/api/news/art-ai-1/related")
        assert related_resp.status_code == 200
        related_items = related_resp.json()
        assert len(related_items) >= 1
        assert related_items[0]["id"] == "art-ai-2"
        assert related_items[0]["similarity_score"] > 0.0


@pytest.mark.asyncio
async def test_api_clustering():
    """Test clustering endpoint assigns clusters to related stories."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cluster_resp = await client.post("/api/news/cluster?threshold=0.60")
        assert cluster_resp.status_code == 200
        cluster_data = cluster_resp.json()
        assert cluster_data["status"] == "success"


@pytest.mark.asyncio
async def test_api_chat_rag_ask():
    """Test RAG news chatbot answers user query with grounded citations."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        chat_resp = await client.post(
            "/api/chat/ask",
            json={"question": "What is the latest with quantum computing?", "top_k": 2},
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert "question" in chat_data
        assert "answer" in chat_data
        assert len(chat_data["sources"]) >= 1
        assert any("quantum" in s["title"].lower() for s in chat_data["sources"])


@pytest.mark.asyncio
async def test_api_chat_explain():
    """Test article explanation endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        explain_resp = await client.get("/api/chat/explain/art-ai-1")
        assert explain_resp.status_code == 200
        explain_data = explain_resp.json()
        assert explain_data["article_id"] == "art-ai-1"
        assert "explanation" in explain_data
