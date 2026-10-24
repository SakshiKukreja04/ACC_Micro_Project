import logging
import os
import time
from typing import Any, Dict, Optional
from app.config import settings
from app.processor import BaseArticleProcessor, DeterministicTestProcessor
from app.queue import JobQueue

logger = logging.getLogger("worker.service")


class BackgroundWorkerService:
    """
    Independent background worker that polls PostgreSQL for pending jobs,
    claims them via row-level locks, executes processing, and tracks completion.
    """

    def __init__(
        self,
        queue: Optional[JobQueue] = None,
        processor: Optional[BaseArticleProcessor] = None,
    ):
        self.queue = queue or JobQueue()
        if processor:
            self.processor = processor
        else:
            groq_key = settings.model_dump().get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
            if groq_key and "placeholder" not in groq_key.lower() and "dummy" not in groq_key.lower():
                try:
                    from app.summarizer import GroqSummarizerProcessor
                    self.processor = GroqSummarizerProcessor(api_key=groq_key)
                    logger.info("Worker configured with GroqSummarizerProcessor.")
                except Exception as e:
                    logger.warning(f"Could not initialize Groq processor: {e}. Using deterministic fallback.")
                    self.processor = DeterministicTestProcessor()
            else:
                self.processor = DeterministicTestProcessor()
        self.is_running = False

    def process_batch(self, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Run a single batch processing iteration:
        1. Recover abandoned jobs past lease timeout.
        2. Claim pending jobs safely with row lock.
        3. Execute processing outside transaction.
        4. Record completed results or failures.
        """
        batch_limit = batch_size or settings.WORKER_BATCH_SIZE

        # 1. Recover abandoned jobs
        recovered = self.queue.recover_abandoned_jobs(
            lease_timeout_seconds=settings.WORKER_LEASE_TIMEOUT_SECONDS
        )

        # 2. Claim pending jobs
        claimed_jobs = self.queue.claim_jobs(batch_size=batch_limit)
        batch_stats = {
            "recovered": recovered,
            "claimed": len(claimed_jobs),
            "succeeded": 0,
            "retried": 0,
            "failed": 0,
            "details": [],
        }

        if not claimed_jobs:
            return batch_stats

        logger.info(f"Worker claimed {len(claimed_jobs)} pending jobs for processing.")

        # 3. Process claimed jobs individually
        for job in claimed_jobs:
            job_start = time.time()
            try:
                results = self.processor.process(job)
                self.queue.mark_completed(job.id, results)
                duration = round(time.time() - job_start, 3)

                batch_stats["succeeded"] += 1
                batch_stats["details"].append(
                    {"job_id": job.id, "status": "completed", "duration_sec": duration}
                )
                logger.info(f"Job {job.id} ('{job.title[:35]}...') completed in {duration}s.")
            except Exception as e:
                duration = round(time.time() - job_start, 3)
                is_failed = job.processing_attempts >= settings.WORKER_MAX_RETRIES
                if is_failed:
                    batch_stats["failed"] += 1
                    status_desc = "failed"
                else:
                    batch_stats["retried"] += 1
                    status_desc = "retried"

                self.queue.mark_failed(
                    article_id=job.id,
                    error_message=str(e),
                    max_retries=settings.WORKER_MAX_RETRIES,
                )
                batch_stats["details"].append(
                    {
                        "job_id": job.id,
                        "status": status_desc,
                        "error": str(e)[:200],
                        "duration_sec": duration,
                    }
                )
                logger.error(
                    f"Job {job.id} error during processing after {duration}s: {e}"
                )

        return batch_stats

    def run_daemon(self, poll_interval: Optional[int] = None) -> None:
        """Run continuous daemon processing loop."""
        interval = poll_interval or settings.WORKER_POLL_INTERVAL_SECONDS
        logger.info(f"AI Worker daemon started. Polling every {interval}s (batch size: {settings.WORKER_BATCH_SIZE}).")
        self.is_running = True

        while self.is_running:
            try:
                stats = self.process_batch()
                if stats["claimed"] > 0:
                    logger.info(
                        f"Batch summary: {stats['succeeded']} completed, "
                        f"{stats['retried']} retried, {stats['failed']} permanently failed."
                    )
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}", exc_info=True)

            # Sleep interval
            try:
                time.sleep(interval)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Worker daemon stopped by signal.")
                self.is_running = False
                break
