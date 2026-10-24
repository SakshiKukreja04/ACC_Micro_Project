import argparse
import logging
import signal
import sys
from app.config import settings
from app.worker import BackgroundWorkerService

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [AI-Worker] %(message)s",
)
logger = logging.getLogger("worker")


def main():
    parser = argparse.ArgumentParser(
        description="AI News Aggregator — Independent Background AI Worker"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process a single batch of pending jobs and exit immediately",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.WORKER_BATCH_SIZE,
        help="Maximum jobs to claim per batch",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=settings.WORKER_POLL_INTERVAL_SECONDS,
        help="Polling interval in seconds between checks",
    )
    args = parser.parse_args()

    service = BackgroundWorkerService()

    def handle_signal(sig, frame):
        logger.info(f"Received termination signal ({sig}). Shutting down worker gracefully...")
        service.is_running = False
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.once:
        logger.info("Executing one-time worker batch run...")
        stats = service.process_batch(batch_size=args.batch_size)
        print("\n=== Worker Batch Run Summary ===")
        print(f"Jobs claimed: {stats['claimed']}")
        print(f"Jobs succeeded: {stats['succeeded']}")
        print(f"Jobs retried: {stats['retried']}")
        print(f"Jobs permanently failed: {stats['failed']}")
        print(f"Abandoned jobs recovered: {stats['recovered']}")
        sys.exit(0)
    else:
        logger.info("Starting background worker in continuous daemon mode...")
        service.run_daemon(poll_interval=args.interval)


if __name__ == "__main__":
    main()
