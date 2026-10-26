"""Structured logging with per-request correlation IDs.

LOG_FORMAT=json emits one JSON object per line (ready for Loki / ELK / CloudWatch);
LOG_FORMAT=text keeps human-friendly lines for local development.
"""
from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if os.getenv("LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonFormatter(service))
    else:
        handler.setFormatter(
            logging.Formatter(f"%(asctime)s [%(levelname)s] [{service}] [req:%(request_id)s] %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Keep noisy libraries quiet
    for noisy in ("httpx", "httpcore", "urllib3", "faiss", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
