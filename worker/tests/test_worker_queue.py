import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.models import Article
from app.processor import DeterministicTestProcessor
from app.queue import JobQueue
from app.worker import BackgroundWorkerService


@pytest.fixture
def test_queue(tmp_path):
    """Provides an isolated SQLite queue for testing."""
    db_file = tmp_path / "test_queue.db"
    db_url = f"sqlite:///{db_file}"
    queue = JobQueue(db_url=db_url, create_tables=True)

    # Seed test articles
    with queue.get_session() as session:
        for i in range(5):
            art = Article(
                id=f"art_test_{i}",
                title=f"Sample Test Article {i}",
                canonical_url=f"https://example.com/test-{i}",
                source_name="Test Source",
                category="Technology",
                description=f"Description for article {i}",
                content=f"Content for article {i}",
                content_hash=f"hash_{i}",
                processing_status="pending",
                processing_attempts=0,
            )
            session.add(art)
        session.commit()

    return queue


def test_claim_and_complete_lifecycle(test_queue):
    # 1. Claim pending jobs
    jobs = test_queue.claim_jobs(batch_size=2)
    assert len(jobs) == 2
    claimed_ids = [j.id for j in jobs]

    # Verify they transitioned to 'processing' with lock timestamp and attempt=1
    with test_queue.get_session() as session:
        for job_id in claimed_ids:
            art = session.scalar(select(Article).where(Article.id == job_id))
            assert art.processing_status == "processing"
            assert art.processing_attempts == 1
            assert art.locked_at is not None

    # 2. Mark completed with outputs
    for job_id in claimed_ids:
        test_queue.mark_completed(
            job_id,
            results={
                "summary": "Deterministic test summary",
                "key_takeaways": ["Point 1", "Point 2"],
            },
        )

    # Verify transition to 'completed'
    with test_queue.get_session() as session:
        for job_id in claimed_ids:
            art = session.scalar(select(Article).where(Article.id == job_id))
            assert art.processing_status == "completed"
            assert art.completed_at is not None
            assert art.locked_at is None
            assert art.summary == "Deterministic test summary"


def test_retry_limits_and_failure(test_queue):
    # Claim 1 job
    jobs = test_queue.claim_jobs(batch_size=1)
    assert len(jobs) == 1
    job = jobs[0]

    # Fail attempt 1 (max_retries=3) -> must return to pending
    test_queue.mark_failed(job.id, error_message="Network glitch", max_retries=3)
    with test_queue.get_session() as session:
        art = session.scalar(select(Article).where(Article.id == job.id))
        assert art.processing_status == "pending"
        assert art.processing_attempts == 1
        assert "Network glitch" in art.error_message

    # Claim attempt 2
    jobs = test_queue.claim_jobs(batch_size=1)
    assert len(jobs) == 1
    test_queue.mark_failed(job.id, error_message="Rate limit 429", max_retries=3)
    with test_queue.get_session() as session:
        art = session.scalar(select(Article).where(Article.id == job.id))
        assert art.processing_status == "pending"
        assert art.processing_attempts == 2

    # Claim attempt 3
    jobs = test_queue.claim_jobs(batch_size=1)
    assert len(jobs) == 1
    test_queue.mark_failed(job.id, error_message="Permanent 500 error", max_retries=3)

    # Must transition permanently to 'failed'
    with test_queue.get_session() as session:
        art = session.scalar(select(Article).where(Article.id == job.id))
        assert art.processing_status == "failed"
        assert art.processing_attempts == 3
        assert "Permanent 500 error" in art.error_message


def test_recover_abandoned_jobs(test_queue):
    # Simulate a crashed worker: article stuck in 'processing' 10 minutes ago
    old_lock_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    with test_queue.get_session() as session:
        art = session.scalar(select(Article).where(Article.id == "art_test_0"))
        art.processing_status = "processing"
        art.locked_at = old_lock_time
        art.processing_attempts = 1
        session.commit()

    # Recover with 5-minute lease threshold
    recovered_count = test_queue.recover_abandoned_jobs(lease_timeout_seconds=300)
    assert recovered_count == 1

    # Verify article reset to 'pending' with cleared lock
    with test_queue.get_session() as session:
        art = session.scalar(select(Article).where(Article.id == "art_test_0"))
        assert art.processing_status == "pending"
        assert art.locked_at is None
        assert "Recovered" in art.error_message


def test_worker_service_batch_execution(test_queue):
    service = BackgroundWorkerService(
        queue=test_queue,
        processor=DeterministicTestProcessor(),
    )

    stats = service.process_batch(batch_size=3)
    assert stats["claimed"] == 3
    assert stats["succeeded"] == 3
    assert stats["failed"] == 0
    assert stats["retried"] == 0

    # Remaining pending articles
    with test_queue.get_session() as session:
        completed = session.scalars(
            select(Article).where(Article.processing_status == "completed")
        ).all()
        assert len(completed) == 3
        for art in completed:
            assert art.summary is not None
            assert len(art.summary) > 10
