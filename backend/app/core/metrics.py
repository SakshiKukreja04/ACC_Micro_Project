"""
Central Prometheus metrics registry + HTTP instrumentation middleware for the backend API.

Every metric the backend exports lives here so that endpoints, services and the
middleware share one definition. A small in-process rolling window is kept as well,
so the in-app "System Monitor" can show live latency / error-rate figures without
having to query Prometheus.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from prometheus_client import Counter, Gauge, Histogram, Info
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

# --------------------------------------------------------------------------- HTTP
HTTP_REQUESTS_TOTAL = Counter(
    "news_http_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "news_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_IN_PROGRESS = Gauge("news_http_requests_in_progress", "HTTP requests currently being served")

# --------------------------------------------------------------------------- Cache
CACHE_OPERATIONS = Counter(
    "news_cache_operations_total",
    "Redis cache lookups by result",
    ["result"],  # hit | miss | error | bypass
)
REDIS_UP = Gauge("news_redis_up", "Redis connectivity (1 = connected, 0 = unavailable)")

# --------------------------------------------------------------------------- LLM / AI
LLM_REQUESTS = Counter(
    "news_llm_requests_total",
    "Groq LLM calls by operation and outcome",
    ["operation", "outcome"],  # outcome: success | error | fallback | unconfigured
)
LLM_DURATION = Histogram(
    "news_llm_request_duration_seconds",
    "Groq LLM call latency in seconds",
    ["operation"],
    buckets=(0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 15.0, 30.0),
)
RAG_QUERIES = Counter("news_rag_queries_total", "RAG chatbot questions answered", ["grounded"])
RAG_RETRIEVED_DOCS = Histogram(
    "news_rag_retrieved_documents", "Documents retrieved per RAG query", buckets=(0, 1, 2, 3, 4, 6, 8, 10)
)
SEMANTIC_SEARCHES = Counter("news_semantic_searches_total", "FAISS semantic search queries")

# --------------------------------------------------------------------------- Data / pipeline
ARTICLES_TOTAL = Gauge("news_articles_total", "Total news articles stored in PostgreSQL", ["category"])
ARTICLES_BY_STATUS = Gauge("news_articles_by_status", "Articles by AI processing status", ["status"])
ARTICLES_BY_SENTIMENT = Gauge("news_articles_by_sentiment", "Articles by sentiment label", ["sentiment"])
ARTICLES_INGESTED_LAST_HOUR = Gauge("news_articles_ingested_last_hour", "Articles collected in the last hour")
AVG_GROUNDING_SCORE = Gauge("news_summary_grounding_score_avg", "Average Fact-Grounding score of AI summaries")
FAISS_VECTORS_TOTAL = Gauge("news_faiss_vectors_total", "Total vector embeddings indexed in FAISS")
VECTOR_SYNC_DURATION = Histogram(
    "news_vector_sync_duration_seconds", "Duration of FAISS sync/cluster jobs", ["job"],
    buckets=(0.05, 0.1, 0.5, 1, 2, 5, 10, 30, 60),
)
VECTOR_SYNC_ADDED = Counter("news_vector_sync_added_total", "Articles embedded into FAISS by the sync job")
STORY_CLUSTERS = Gauge("news_story_clusters_total", "Number of multi-article story clusters")
DATABASE_HEALTH = Gauge("news_database_up", "Database connectivity health (1 = connected, 0 = degraded)")

# --------------------------------------------------------------------------- Readers
SSE_CLIENTS = Gauge("news_sse_clients", "Readers connected to the live event stream")
READER_EVENTS = Counter("news_reader_events_total", "Reader interactions", ["event_type"])
BOOKMARKS_TOTAL = Gauge("news_bookmarks_total", "Saved bookmarks across all readers")

APP_INFO = Info("news_backend", "Backend build information")

SERVICE_START_TIME = time.time()


# --------------------------------------------------------------------------- Rolling window
class RollingStats:
    """Thread-safe rolling window of recent requests / LLM calls for the in-app monitor."""

    def __init__(self, window_seconds: int = 600, max_items: int = 20000):
        self.window = window_seconds
        self._requests: Deque[Tuple[float, float, int, str]] = deque(maxlen=max_items)
        self._llm: Deque[Tuple[float, float, str, str]] = deque(maxlen=2000)
        self._lock = threading.Lock()

    def record_request(self, duration: float, status: int, endpoint: str) -> None:
        with self._lock:
            self._requests.append((time.time(), duration, status, endpoint))

    def record_llm(self, duration: float, operation: str, outcome: str) -> None:
        with self._lock:
            self._llm.append((time.time(), duration, operation, outcome))

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        k = max(0, min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1)))))
        return values[k]

    def request_summary(self, seconds: Optional[int] = None) -> Dict:
        horizon = time.time() - (seconds or self.window)
        with self._lock:
            recent = [r for r in self._requests if r[0] >= horizon and r[3] not in IGNORED_PATHS]
        durations = [r[1] for r in recent]
        errors = sum(1 for r in recent if r[2] >= 500)
        span_min = (seconds or self.window) / 60.0
        top: Dict[str, List[float]] = {}
        for _, d, _, ep in recent:
            top.setdefault(ep, []).append(d)
        endpoints = sorted(
            (
                {
                    "endpoint": ep,
                    "requests": len(ds),
                    "p95_ms": round(self._percentile(ds, 95) * 1000, 1),
                    "avg_ms": round(sum(ds) / len(ds) * 1000, 1),
                }
                for ep, ds in top.items()
            ),
            key=lambda e: e["requests"],
            reverse=True,
        )[:8]
        return {
            "window_seconds": seconds or self.window,
            "requests": len(recent),
            "requests_per_minute": round(len(recent) / span_min, 2),
            "error_rate": round(errors / len(recent), 4) if recent else 0.0,
            "p50_ms": round(self._percentile(durations, 50) * 1000, 1),
            "p95_ms": round(self._percentile(durations, 95) * 1000, 1),
            "p99_ms": round(self._percentile(durations, 99) * 1000, 1),
            "top_endpoints": endpoints,
        }

    def latency_series(self, buckets: int = 30, bucket_seconds: int = 20) -> List[Dict]:
        now = time.time()
        start = now - buckets * bucket_seconds
        with self._lock:
            recent = [r for r in self._requests if r[0] >= start and r[3] not in IGNORED_PATHS]
        series = []
        for i in range(buckets):
            lo, hi = start + i * bucket_seconds, start + (i + 1) * bucket_seconds
            ds = [r[1] for r in recent if lo <= r[0] < hi]
            series.append(
                {
                    "t": int(hi),
                    "requests": len(ds),
                    "p95_ms": round(self._percentile(ds, 95) * 1000, 1) if ds else 0.0,
                }
            )
        return series

    def llm_summary(self) -> Dict:
        horizon = time.time() - 3600
        with self._lock:
            recent = [r for r in self._llm if r[0] >= horizon]
        by_op: Dict[str, Dict] = {}
        for _, d, op, outcome in recent:
            entry = by_op.setdefault(op, {"operation": op, "calls": 0, "errors": 0, "_d": []})
            entry["calls"] += 1
            if outcome != "success":
                entry["errors"] += 1
            if outcome == "success":
                entry["_d"].append(d)
        ops = []
        for entry in by_op.values():
            ds = entry.pop("_d")
            entry["avg_ms"] = round(sum(ds) / len(ds) * 1000, 1) if ds else 0.0
            ops.append(entry)
        return {"window_seconds": 3600, "calls": len(recent), "operations": ops}


IGNORED_PATHS = {"/metrics", "/health", "/api/health", "/api/stream/events", "/api/monitoring/overview"}
stats = RollingStats()


def _route_template(request: Request) -> str:
    """
    Templated path (e.g. /api/news/{article_id}/related) to keep label cardinality bounded.
    Built from the full request path + matched path params, so it works whether or not the
    framework keeps include_router prefixes on route objects.
    """
    if request.scope.get("route") is None:
        return "unmatched"
    path = request.scope.get("path", "")
    params = request.scope.get("path_params") or {}
    if not params:
        return path
    parts = path.split("/")
    for name, value in params.items():
        value = str(value)
        parts = [f"{{{name}}}" if seg == value else seg for seg in parts]
    return "/".join(parts)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records request count, latency and in-flight requests; adds X-Request-ID and X-Process-Time headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status_code = 500
        HTTP_IN_PROGRESS.inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            HTTP_IN_PROGRESS.dec()
            endpoint = _route_template(request)
            method = request.method
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
            if endpoint != "/api/stream/events":  # long-lived stream would skew latency
                HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
            stats.record_request(duration, status_code, endpoint)
            request_id_ctx.reset(token)
            try:
                response.headers["X-Request-ID"] = request_id  # type: ignore[possibly-undefined]
                response.headers["X-Process-Time"] = f"{duration * 1000:.1f}ms"
            except Exception:
                pass
