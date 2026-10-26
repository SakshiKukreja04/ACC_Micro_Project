"""Prometheus metrics for the AI worker (served on WORKER_METRICS_PORT, default 9101)."""
import logging

from prometheus_client import Counter, Gauge, Histogram, Info, start_http_server

logger = logging.getLogger("worker.metrics")

JOBS_TOTAL = Counter("news_worker_jobs_total", "Article jobs processed by outcome", ["outcome"])
JOB_DURATION = Histogram(
    "news_worker_job_duration_seconds",
    "Time spent summarising + enriching one article",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30),
)
BATCHES_TOTAL = Counter("news_worker_batches_total", "Polling batches executed")
RECOVERED_TOTAL = Counter("news_worker_recovered_jobs_total", "Abandoned jobs recovered after lease timeout")
LAST_BATCH_TS = Gauge("news_worker_last_batch_timestamp_seconds", "Unix time of the last completed polling batch")
QUEUE_DEPTH = Gauge("news_worker_queue_depth", "Articles per processing status", ["status"])
LLM_CALLS = Counter("news_worker_llm_calls_total", "Groq calls made by the worker", ["model", "outcome"])
GROUNDING = Histogram(
    "news_worker_grounding_score", "Fact-Grounding score of generated summaries",
    buckets=(0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
WORKER_INFO = Info("news_worker", "AI worker configuration")


def start_metrics_server(port: int) -> None:
    try:
        start_http_server(port)
        logger.info(f"Worker Prometheus metrics exposed on :{port}/metrics")
    except OSError as e:
        logger.warning(f"Could not start metrics server on port {port}: {e}")
