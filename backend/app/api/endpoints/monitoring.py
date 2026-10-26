"""
System Monitor API — a single JSON snapshot of the whole microservice deployment.

The backend actively probes its dependencies (PostgreSQL, Redis, FAISS, Groq) and scrapes the
Prometheus endpoints of the independent worker and collector containers, so the React dashboard
can show live health without needing Grafana credentials. Grafana/Prometheus remain the
long-term, historical view.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter
from prometheus_client import REGISTRY
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import func, select, text

from app.core import llm
from app.core.config import settings
from app.core.metrics import SERVICE_START_TIME, stats
from app.core.redis_cache import cache_info
from app.db.session import SessionLocal
from app.models.article import Article, Bookmark, ReadingEvent
from app.services.background import job_status
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Metrics"])
logger = logging.getLogger("backend.api.monitoring")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="monitor-probe")


def _scrape(url: str) -> Dict:
    """Fetch and parse a Prometheus text endpoint. Returns {'up': bool, 'latency_ms', 'samples': [...]}."""
    start = time.perf_counter()
    try:
        resp = httpx.get(url, timeout=1.5)
        resp.raise_for_status()
        samples = []
        for family in text_string_to_metric_families(resp.text):
            for s in family.samples:
                samples.append((s.name, s.labels, s.value))
        return {"up": True, "latency_ms": round((time.perf_counter() - start) * 1000, 1), "samples": samples}
    except Exception as e:
        return {"up": False, "latency_ms": None, "error": str(e)[:160], "samples": []}


def _sample(samples, name: str, **labels) -> Optional[float]:
    for n, lbl, v in samples:
        if n == name and all(lbl.get(k) == val for k, val in labels.items()):
            return v
    return None


def _sum_samples(samples, name: str, **labels) -> float:
    return sum(v for n, lbl, v in samples if n == name and all(lbl.get(k) == val for k, val in labels.items()))


def _local(name: str, labels: Optional[Dict] = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def _age(ts: Optional[float]) -> Optional[float]:
    return round(time.time() - ts, 1) if ts else None


def _worker_section(scrape: Dict) -> Dict:
    s = scrape["samples"]
    duration_sum = _sum_samples(s, "news_worker_job_duration_seconds_sum")
    duration_count = _sum_samples(s, "news_worker_job_duration_seconds_count")
    last_batch = _sample(s, "news_worker_last_batch_timestamp_seconds")
    processor = next((lbl.get("processor") for n, lbl, _ in s if n == "news_worker_info"), None)
    return {
        "reachable": scrape["up"],
        "processor": processor,
        "jobs_completed": int(_sum_samples(s, "news_worker_jobs_total", outcome="completed")),
        "jobs_retried": int(_sum_samples(s, "news_worker_jobs_total", outcome="retried")),
        "jobs_failed": int(_sum_samples(s, "news_worker_jobs_total", outcome="failed")),
        "jobs_recovered": int(_sum_samples(s, "news_worker_recovered_jobs_total")),
        "avg_job_seconds": round(duration_sum / duration_count, 3) if duration_count else None,
        "seconds_since_last_batch": _age(last_batch),
        "error": scrape.get("error"),
    }


def _collector_section(scrape: Dict) -> Dict:
    s = scrape["samples"]
    sources: Dict[str, Dict] = {}
    for n, lbl, v in s:
        src = lbl.get("source")
        if not src:
            continue
        entry = sources.setdefault(
            src, {"source": src, "fetched": 0, "inserted": 0, "duplicates": 0, "errors": 0, "last_success_age": None}
        )
        if n == "news_collector_articles_fetched_total":
            entry["fetched"] = int(v)
        elif n == "news_collector_articles_inserted_total":
            entry["inserted"] = int(v)
        elif n == "news_collector_duplicates_total":
            entry["duplicates"] = int(v)
        elif n == "news_collector_feed_errors_total":
            entry["errors"] = int(v)
        elif n == "news_collector_last_success_timestamp_seconds" and v > 0:
            entry["last_success_age"] = _age(v)
    last_cycle = _sample(s, "news_collector_last_cycle_timestamp_seconds")
    cycle_sum = _sum_samples(s, "news_collector_cycle_duration_seconds_sum")
    cycle_count = _sum_samples(s, "news_collector_cycle_duration_seconds_count")
    return {
        "reachable": scrape["up"],
        "cycles": int(cycle_count),
        "avg_cycle_seconds": round(cycle_sum / cycle_count, 2) if cycle_count else None,
        "seconds_since_last_cycle": _age(last_cycle),
        "sources": sorted(sources.values(), key=lambda x: x["source"]),
        "error": scrape.get("error"),
    }


def _pipeline_section() -> Dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        status_counts = {
            st: cnt
            for st, cnt in db.execute(
                select(Article.processing_status, func.count(Article.id)).group_by(Article.processing_status)
            ).all()
        }
        total = sum(status_counts.values())
        ingested_1h = db.scalar(select(func.count(Article.id)).where(Article.collected_at >= now - timedelta(hours=1)))
        ingested_24h = db.scalar(select(func.count(Article.id)).where(Article.collected_at >= now - timedelta(hours=24)))
        completed_1h = db.scalar(
            select(func.count(Article.id)).where(Article.completed_at >= now - timedelta(hours=1))
        )
        oldest_pending = db.scalar(
            select(func.min(Article.collected_at)).where(Article.processing_status == "pending")
        )
        recent_done = db.execute(
            select(Article.collected_at, Article.completed_at)
            .where(Article.completed_at.isnot(None), Article.completed_at >= now - timedelta(hours=24))
            .limit(500)
        ).all()
        avg_grounding = db.scalar(select(func.avg(Article.grounding_score)))
        bookmarks = db.scalar(select(func.count(Bookmark.id)))
        readers = db.scalar(select(func.count(func.distinct(ReadingEvent.client_id))))

    latencies = []
    for collected, completed in recent_done:
        if collected and completed:
            if collected.tzinfo is None:
                collected = collected.replace(tzinfo=timezone.utc)
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=timezone.utc)
            latencies.append(max(0.0, (completed - collected).total_seconds()))

    if oldest_pending is not None and oldest_pending.tzinfo is None:
        oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)

    return {
        "total_articles": total,
        "status_counts": {st: status_counts.get(st, 0) for st in ("pending", "processing", "completed", "failed")},
        "ingested_last_hour": ingested_1h or 0,
        "ingested_last_24h": ingested_24h or 0,
        "completed_last_hour": completed_1h or 0,
        "oldest_pending_age_seconds": round((now - oldest_pending).total_seconds(), 1) if oldest_pending else None,
        "avg_ingest_to_summary_seconds": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "avg_grounding_score": round(float(avg_grounding), 3) if avg_grounding is not None else None,
        "bookmarks": bookmarks or 0,
        "active_readers": readers or 0,
    }


def _status(ok: bool, degraded: bool = False) -> str:
    if not ok:
        return "down"
    return "degraded" if degraded else "up"


@router.get("/overview")
def monitoring_overview():
    """Aggregated live health of every service in the deployment (used by the System Monitor tab)."""
    started = time.perf_counter()
    worker_future = _executor.submit(_scrape, settings.WORKER_METRICS_URL)
    collector_future = _executor.submit(_scrape, settings.COLLECTOR_METRICS_URL)
    prometheus_future = _executor.submit(_scrape, f"{settings.PROMETHEUS_INTERNAL_URL}/metrics")

    services: List[Dict] = []
    services.append(
        {"name": "Backend API", "kind": "FastAPI", "status": "up",
         "detail": f"v{settings.VERSION} · uptime {int(time.time() - SERVICE_START_TIME)}s", "latency_ms": None}
    )

    # PostgreSQL
    pipeline: Dict = {}
    db_start = time.perf_counter()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ms = round((time.perf_counter() - db_start) * 1000, 1)
        services.append({"name": "PostgreSQL", "kind": "Database", "status": "up", "detail": "SELECT 1 ok", "latency_ms": db_ms})
        pipeline = _pipeline_section()
    except Exception as e:
        services.append({"name": "PostgreSQL", "kind": "Database", "status": "down", "detail": str(e)[:120], "latency_ms": None})

    # Redis
    redis_start = time.perf_counter()
    cache = cache_info()
    services.append(
        {"name": "Redis", "kind": "Cache", "status": _status(cache.get("connected", False)),
         "detail": f"{cache.get('keys', 0)} keys · {cache.get('used_memory_human', '-')}" if cache.get("connected") else "unreachable — API serving uncached",
         "latency_ms": round((time.perf_counter() - redis_start) * 1000, 1) if cache.get("connected") else None}
    )
    hits = _local("news_cache_operations_total", {"result": "hit"})
    misses = _local("news_cache_operations_total", {"result": "miss"})
    cache["hit_ratio"] = round(hits / (hits + misses), 3) if (hits + misses) else None
    cache["hits"], cache["misses"] = int(hits), int(misses)

    # FAISS
    store = VectorStoreService._instance
    vectors = store.index.ntotal if store else 0
    total_articles = pipeline.get("total_articles", 0)
    services.append(
        {"name": "FAISS Vector Index", "kind": "Vector DB", "status": _status(store is not None, degraded=store is not None and vectors < total_articles),
         "detail": f"{vectors}/{total_articles} articles embedded" if store else "loading embedding model…", "latency_ms": None}
    )

    # Groq
    llm_stats = stats.llm_summary()
    llm_errors = sum(op["errors"] for op in llm_stats["operations"])
    services.append(
        {"name": "Groq LLM", "kind": "AI Inference",
         "status": "degraded" if not llm.is_configured() else _status(True, degraded=llm_stats["calls"] > 0 and llm_errors / llm_stats["calls"] > 0.5),
         "detail": "GROQ_API_KEY not set — deterministic fallbacks active" if not llm.is_configured() else f"{llm_stats['calls']} calls in last hour",
         "latency_ms": None}
    )

    worker_scrape = worker_future.result()
    worker = _worker_section(worker_scrape)
    stale_worker = worker["seconds_since_last_batch"] is not None and worker["seconds_since_last_batch"] > 120
    services.append(
        {"name": "AI Worker", "kind": "Background job", "status": _status(worker_scrape["up"], degraded=stale_worker),
         "detail": (f"{worker['jobs_completed']} jobs done · processor={worker['processor']}" if worker_scrape["up"] else "metrics endpoint unreachable"),
         "latency_ms": worker_scrape["latency_ms"]}
    )

    collector_scrape = collector_future.result()
    collector = _collector_section(collector_scrape)
    failing = [s["source"] for s in collector["sources"] if s["errors"] and not s["last_success_age"]]
    services.append(
        {"name": "News Collector", "kind": "Ingestion daemon", "status": _status(collector_scrape["up"], degraded=bool(failing)),
         "detail": (f"{collector['cycles']} cycles · {len(collector['sources'])} sources" + (f" · {len(failing)} failing" if failing else "")) if collector_scrape["up"] else "metrics endpoint unreachable",
         "latency_ms": collector_scrape["latency_ms"]}
    )

    prom = prometheus_future.result()
    services.append(
        {"name": "Prometheus", "kind": "Monitoring", "status": _status(prom["up"]),
         "detail": "scraping all targets" if prom["up"] else "not reachable (optional)", "latency_ms": prom["latency_ms"]}
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "uptime_seconds": int(time.time() - SERVICE_START_TIME),
        "overall_status": "down" if any(s["status"] == "down" and s["name"] in ("PostgreSQL", "Backend API") for s in services)
        else ("degraded" if any(s["status"] != "up" for s in services) else "healthy"),
        "services": services,
        "api": {**stats.request_summary(600), "series": stats.latency_series()},
        "pipeline": pipeline,
        "worker": worker,
        "collector": collector,
        "llm": {**llm_stats, "configured": llm.is_configured(), "model_chain": llm.model_chain()},
        "cache": cache,
        "vector": {
            "vectors": vectors,
            "embedding_model": VectorStoreService.embedder_name,
            "dimensions": 384,
            "jobs": job_status,
        },
        "links": {"grafana": settings.GRAFANA_PUBLIC_URL, "prometheus": settings.PROMETHEUS_PUBLIC_URL},
        "probe_ms": round((time.perf_counter() - started) * 1000, 1),
    }
