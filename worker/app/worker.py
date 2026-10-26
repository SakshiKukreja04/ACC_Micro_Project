import logging
import os
import time
from typing import Any, Dict, Optional

from app.config import settings
from app.enrichment import classify_topic, enrich_article, normalize_category
from app.metrics import (
    BATCHES_TOTAL,
    GROUNDING,
    JOB_DURATION,
    JOBS_TOTAL,
    LAST_BATCH_TS,
    QUEUE_DEPTH,
    RECOVERED_TOTAL,
    WORKER_INFO,
)
from app.processor import BaseArticleProcessor, DeterministicTestProcessor
from app.queue import ArticleJob, JobQueue

logger = logging.getLogger("worker.service")


class BackgroundWorkerService:
    """
    Independent background worker that polls PostgreSQL for pending jobs,
    claims them via row-level locks, executes AI processing + enrichment, and tracks completion.

    Pipeline per article:
      1. Groq LLM summary + key takeaways (or deterministic extractive fallback)
      2. Enrichment: sentiment (VADER), Fact-Grounding score, keywords, reading time
      3. Category refinement: LLM-suggested or keyword-classified canonical category
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
            groq_key = os.getenv("GROQ_API_KEY", "")
            if groq_key and not any(b in groq_key.lower() for b in ("placeholder", "dummy", "your_")):
                try:
                    from app.summarizer import GroqSummarizerProcessor

                    self.processor = GroqSummarizerProcessor(api_key=groq_key)
                    logger.info("Worker configured with GroqSummarizerProcessor.")
                except Exception as e:
                    logger.warning(f"Could not initialize Groq processor: {e}. Using deterministic fallback.")
                    self.processor = DeterministicTestProcessor()
            else:
                logger.warning("GROQ_API_KEY not set — using deterministic extractive summaries.")
                self.processor = DeterministicTestProcessor()
        self.processor_name = "groq" if type(self.processor).__name__ == "GroqSummarizerProcessor" else "deterministic"
        WORKER_INFO.info({"processor": self.processor_name, "batch_size": str(settings.WORKER_BATCH_SIZE)})
        self.is_running = False

    @staticmethod
    def enrich(job: ArticleJob, results: Dict[str, Any]) -> Dict[str, Any]:
        """Add sentiment, grounding, keywords, reading time and a canonical category to processor output."""
        enriched = dict(results)
        enriched.update(enrich_article(job.title, job.description, job.content, results.get("summary")))

        suggested = results.get("suggested_category")
        if suggested and normalize_category(suggested) != "General":
            enriched["category"] = normalize_category(suggested)
        else:
            current = normalize_category(job.category)
            if current == "General":
                enriched["category"] = classify_topic(job.title, f"{job.description or ''} {job.content or ''}", "General")
        enriched.pop("suggested_category", None)
        enriched.pop("model", None)
        if enriched.get("grounding_score") is not None:
            GROUNDING.observe(enriched["grounding_score"])
        return enriched

    def update_queue_depth(self) -> None:
        for status, count in self.queue.status_counts().items():
            QUEUE_DEPTH.labels(status=status).set(count)

    def process_batch(self, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Run a single batch processing iteration:
        1. Recover abandoned jobs past lease timeout.
        2. Claim pending jobs safely with row lock.
        3. Execute processing outside transaction.
        4. Record completed results or failures.
        """
        batch_limit = batch_size or settings.WORKER_BATCH_SIZE

        recovered = self.queue.recover_abandoned_jobs(
            lease_timeout_seconds=settings.WORKER_LEASE_TIMEOUT_SECONDS
        )
        if recovered:
            RECOVERED_TOTAL.inc(recovered)

        claimed_jobs = self.queue.claim_jobs(batch_size=batch_limit)
        batch_stats = {
            "recovered": recovered,
            "claimed": len(claimed_jobs),
            "succeeded": 0,
            "retried": 0,
            "failed": 0,
            "details": [],
        }

        if claimed_jobs:
            logger.info(f"Worker claimed {len(claimed_jobs)} pending jobs for processing.")

        for job in claimed_jobs:
            job_start = time.time()
            try:
                results = self.processor.process(job)
                results = self.enrich(job, results)
                self.queue.mark_completed(job.id, results)
                duration = round(time.time() - job_start, 3)
                JOB_DURATION.observe(duration)
                JOBS_TOTAL.labels(outcome="completed").inc()

                batch_stats["succeeded"] += 1
                batch_stats["details"].append(
                    {"job_id": job.id, "status": "completed", "duration_sec": duration}
                )
                logger.info(
                    f"Job {job.id} ('{job.title[:35]}...') completed in {duration}s "
                    f"[sentiment={results.get('sentiment')}, grounding={results.get('grounding_score')}]"
                )
            except Exception as e:
                duration = round(time.time() - job_start, 3)
                is_failed = job.processing_attempts >= settings.WORKER_MAX_RETRIES
                status_desc = "failed" if is_failed else "retried"
                batch_stats[status_desc] += 1
                JOBS_TOTAL.labels(outcome=status_desc).inc()

                self.queue.mark_failed(
                    article_id=job.id,
                    error_message=str(e),
                    max_retries=settings.WORKER_MAX_RETRIES,
                )
                batch_stats["details"].append(
                    {"job_id": job.id, "status": status_desc, "error": str(e)[:200], "duration_sec": duration}
                )
                logger.error(f"Job {job.id} error during processing after {duration}s: {e}")

        BATCHES_TOTAL.inc()
        LAST_BATCH_TS.set_to_current_time()
        try:
            self.update_queue_depth()
        except Exception:
            pass
        return batch_stats

    def run_daemon(self, poll_interval: Optional[int] = None) -> None:
        """Run continuous daemon processing loop."""
        interval = poll_interval or settings.WORKER_POLL_INTERVAL_SECONDS
        logger.info(
            f"AI Worker daemon started. Polling every {interval}s (batch size: {settings.WORKER_BATCH_SIZE}, "
            f"processor: {self.processor_name})."
        )
        self.is_running = True

        while self.is_running:
            try:
                stats = self.process_batch()
                if stats["claimed"] > 0:
                    logger.info(
                        f"Batch summary: {stats['succeeded']} completed, "
                        f"{stats['retried']} retried, {stats['failed']} permanently failed."
                    )
                    if stats["succeeded"] == stats["claimed"]:
                        continue  # healthy batch and more work may be waiting — poll again immediately
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}", exc_info=True)

            try:
                time.sleep(interval)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Worker daemon stopped by signal.")
                self.is_running = False
                break
