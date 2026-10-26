"""Prometheus metrics for the RSS collector (served on COLLECTOR_METRICS_PORT, default 9102)."""
import logging

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger("collector.metrics")

FETCHED = Counter("news_collector_articles_fetched_total", "Raw feed entries fetched", ["source"])
INSERTED = Counter("news_collector_articles_inserted_total", "New articles stored", ["source"])
DUPLICATES = Counter("news_collector_duplicates_total", "Entries skipped as duplicates", ["source"])
FEED_ERRORS = Counter("news_collector_feed_errors_total", "Feed fetch / parse failures", ["source"])
FETCH_DURATION = Histogram(
    "news_collector_feed_fetch_seconds", "Time to fetch and parse one feed", ["source"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 4, 8, 15),
)
LAST_SUCCESS = Gauge("news_collector_last_success_timestamp_seconds", "Last successful fetch per source", ["source"])
CYCLE_DURATION = Histogram(
    "news_collector_cycle_duration_seconds", "Duration of a full collection cycle",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120),
)
LAST_CYCLE = Gauge("news_collector_last_cycle_timestamp_seconds", "Unix time of the last finished cycle")
SOURCES_CONFIGURED = Gauge("news_collector_sources_configured", "Number of enabled sources")
DEMO_SEEDED = Counter("news_collector_demo_articles_seeded_total", "Offline demo articles seeded")


def start_metrics_server(port: int) -> None:
    try:
        start_http_server(port)
        logger.info(f"Collector Prometheus metrics exposed on :{port}/metrics")
    except OSError as e:
        logger.warning(f"Could not start metrics server on port {port}: {e}")
