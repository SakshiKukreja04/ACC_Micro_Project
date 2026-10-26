"""
Real-time notifications over Server-Sent Events (SSE).

Readers keep one lightweight HTTP connection open; the backend pushes:
  * new_articles     — the collector stored new stories (with up to 3 headlines)
  * summaries_ready  — the AI worker finished summarising more articles
  * heartbeat        — keeps proxies from closing idle connections
SSE works through the Vite dev proxy and any HTTP load balancer, with no WebSocket upgrade.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from starlette.concurrency import run_in_threadpool

from app.core.metrics import SSE_CLIENTS
from app.db.session import SessionLocal
from app.models.article import Article

router = APIRouter(prefix="/stream", tags=["Real-time Notifications"])
logger = logging.getLogger("backend.api.stream")

POLL_SECONDS = 5
HEARTBEAT_SECONDS = 20


def _snapshot() -> Dict:
    with SessionLocal() as db:
        total = db.scalar(select(func.count(Article.id))) or 0
        completed = db.scalar(select(func.count(Article.id)).where(Article.processing_status == "completed")) or 0
        latest = db.execute(
            select(Article.id, Article.title, Article.source_name, Article.category)
            .order_by(desc(Article.collected_at))
            .limit(3)
        ).all()
    return {
        "total": total,
        "completed": completed,
        "latest": [{"id": r[0], "title": r[1], "source_name": r[2], "category": r[3]} for r in latest],
    }


def _sse(event: str, data: Dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/events")
async def event_stream(request: Request, once: bool = Query(False, description="Send the initial snapshot and close")):
    async def generator():
        SSE_CLIENTS.inc()
        try:
            try:
                state = await run_in_threadpool(_snapshot)
            except Exception as e:
                yield _sse("error", {"message": "database unavailable"})
                logger.warning(f"SSE snapshot failed: {e}")
                return
            yield "retry: 5000\n\n"
            yield _sse("hello", {"total": state["total"], "completed": state["completed"]})
            if once:
                return

            idle = 0
            while True:
                await asyncio.sleep(POLL_SECONDS)
                if await request.is_disconnected():
                    break
                try:
                    snap = await run_in_threadpool(_snapshot)
                except Exception:
                    continue
                sent = False
                if snap["total"] > state["total"]:
                    new_count = snap["total"] - state["total"]
                    yield _sse("new_articles", {"new_count": new_count, "total": snap["total"],
                                                "latest": snap["latest"][: min(3, new_count)]})
                    sent = True
                if snap["completed"] > state["completed"]:
                    yield _sse("summaries_ready", {"new_count": snap["completed"] - state["completed"],
                                                   "completed": snap["completed"]})
                    sent = True
                state = snap
                idle = 0 if sent else idle + POLL_SECONDS
                if idle >= HEARTBEAT_SECONDS:
                    yield ": heartbeat\n\n"
                    idle = 0
        finally:
            SSE_CLIENTS.dec()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
