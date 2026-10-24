import pytest
from datetime import datetime, timezone
from app.repository import ArticleRepository


@pytest.fixture
def test_repo(tmp_path):
    """Provides a fresh isolated SQLite database repository for testing."""
    db_file = tmp_path / "test_articles.db"
    db_url = f"sqlite:///{db_file}"
    repo = ArticleRepository(db_url=db_url, create_tables=True)
    return repo


def test_insert_articles_and_prevent_duplicates(test_repo):
    articles = [
        {
            "title": "Autonomous Energy Grids Unveiled",
            "canonical_url": "https://example.com/energy-1",
            "source_name": "Tech Daily",
            "category": "Energy",
            "description": "Smart grids powered by decentralized AI.",
            "content": "Full story on clean micro-generation.",
            "published_at": datetime.now(timezone.utc),
            "collected_at": datetime.now(timezone.utc),
            "content_hash": "hash_001_energy",
            "processing_status": "pending",
            "processing_attempts": 0,
        },
        {
            "title": "Quantum Sensor Reaches Millikelvin Accuracy",
            "canonical_url": "https://example.com/quantum-1",
            "source_name": "Physics Digest",
            "category": "Physics",
            "description": "Sensors measure subatomic vibrations.",
            "content": "Cryogenic details revealed.",
            "published_at": datetime.now(timezone.utc),
            "collected_at": datetime.now(timezone.utc),
            "content_hash": "hash_002_quantum",
            "processing_status": "pending",
            "processing_attempts": 0,
        },
    ]

    # First insertion run
    res1 = test_repo.save_articles(articles)
    assert res1["inserted"] == 2
    assert res1["duplicates"] == 0
    assert res1["failed"] == 0
    assert test_repo.count_articles() == 2

    # Second insertion run with exact same articles -> must detect duplicates
    res2 = test_repo.save_articles(articles)
    assert res2["inserted"] == 0
    assert res2["duplicates"] == 2
    assert res2["failed"] == 0
    assert test_repo.count_articles() == 2


def test_save_empty_batch(test_repo):
    res = test_repo.save_articles([])
    assert res["inserted"] == 0
    assert res["duplicates"] == 0
    assert res["failed"] == 0
