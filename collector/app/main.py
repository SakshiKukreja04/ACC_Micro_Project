import argparse
import logging
import signal
import sys
from app.config import settings
from app.scheduler import NewsCollectorService

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [Collector] %(message)s",
)
logger = logging.getLogger("collector")


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
    args = parser.parse_args()

    service = NewsCollectorService()

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
        logger.info(f"Starting collector in continuous daemon mode (interval: {args.interval}s)...")
        service.run_periodic(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
