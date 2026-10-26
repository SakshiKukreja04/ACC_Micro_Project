import argparse
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone

from app.config import settings


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname, "service": "collector", "logger": record.name, "message": record.getMessage(),
        })


_handler = logging.StreamHandler()
_handler.setFormatter(
    _JsonFormatter() if os.getenv("LOG_FORMAT", "text").lower() == "json"
    else logging.Formatter("%(asctime)s [%(levelname)s] [Collector] %(message)s")
)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), handlers=[_handler])
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("collector")

from app.metrics import start_metrics_server  # noqa: E402
from app.scheduler import NewsCollectorService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="AI News Aggregator — Independent RSS News Collector Service"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute a single news collection cycle and exit immediately",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.COLLECTION_INTERVAL_SECONDS,
        help="Polling interval in seconds for periodic collection (default: 300)",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Insert the clearly-labelled offline demo articles and exit",
    )
    args = parser.parse_args()

    service = NewsCollectorService()

    if args.seed_demo:
        from app.demo_seed import seed_demo_articles

        inserted = seed_demo_articles(service.repository)
        print(f"Seeded {inserted} demo articles (already-present demo articles are skipped).")
        sys.exit(0)

    # Graceful termination handling
    def handle_signal(sig, frame):
        logger.info(f"Received termination signal ({sig}). Shutting down gracefully...")
        service.is_running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        logger.info("Executing one-time collection run...")
        summary = service.collect_once()
        print("\n=== Collection Run Summary ===")
        print(f"Sources processed: {summary['successful_sources']}/{summary['total_sources']}")
        print(f"Raw items fetched: {summary['total_raw_entries']}")
        print(f"New articles inserted: {summary['total_inserted']}")
        print(f"Duplicate articles skipped: {summary['total_duplicates']}")
        print(f"Failed insertions: {summary['total_failed']}")
        sys.exit(0 if summary["failed_sources"] == 0 else 1)
    else:
        start_metrics_server(settings.COLLECTOR_METRICS_PORT)
        logger.info(f"Starting collector in continuous daemon mode (interval: {args.interval}s)...")
        service.run_periodic(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
