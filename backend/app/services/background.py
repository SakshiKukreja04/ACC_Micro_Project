"""
Background maintenance loop running inside the backend container.

* Every EMBED_SYNC_INTERVAL_SECONDS: embed newly collected articles into FAISS
* Every CLUSTER_INTERVAL_SECONDS: re-run DSU story clustering and invalidate feed caches

Previously embeddings were only created when the index was empty, so articles collected
after start-up were invisible to semantic search, RAG and recommendations.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict

from app.core.config import settings
from app.core.metrics import STORY_CLUSTERS, VECTOR_SYNC_ADDED, VECTOR_SYNC_DURATION
from app.core.redis_cache import cache_delete_pattern
from app.db.session import SessionLocal

logger = logging.getLogger("backend.background")

job_status: Dict[str, Dict] = {
    "embedding_sync": {"last_run": None, "last_added": 0, "last_error": None, "runs": 0},
    "story_clustering": {"last_run": None, "clusters": 0, "last_error": None, "runs": 0},
}


def run_embedding_sync() -> int:
    from app.services.vector_store import get_vector_store

    start = time.perf_counter()
    with SessionLocal() as db:
        added = get_vector_store().sync_from_database(db)
    VECTOR_SYNC_DURATION.labels(job="embedding_sync").observe(time.perf_counter() - start)
    if added:
        VECTOR_SYNC_ADDED.inc(added)
    job_status["embedding_sync"].update(last_run=time.time(), last_added=added, last_error=None)
    job_status["embedding_sync"]["runs"] += 1
    return added


def run_clustering() -> int:
    from app.services.vector_store import get_vector_store

    start = time.perf_counter()
    store = get_vector_store()
    with SessionLocal() as db:
        assignments = store.cluster_articles(db, threshold=store.threshold("cluster"))
    clusters = len(set(assignments.values()))
    STORY_CLUSTERS.set(clusters)
    VECTOR_SYNC_DURATION.labels(job="story_clustering").observe(time.perf_counter() - start)
    job_status["story_clustering"].update(last_run=time.time(), clusters=clusters, last_error=None)
    job_status["story_clustering"]["runs"] += 1
    cache_delete_pattern("news_feed:*")
    return clusters


class BackgroundJobs:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.ENABLE_BACKGROUND_JOBS or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="vector-maintenance", daemon=True)
        self._thread.start()
        logger.info("Background vector maintenance started.")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        last_cluster = 0.0
        # Small delay so the API is serving (and passing health checks) before heavy model loading
        self._stop.wait(3)
        while not self._stop.is_set():
            try:
                added = run_embedding_sync()
                if added:
                    logger.info(f"Embedding sync indexed {added} new articles.")
            except Exception as e:
                job_status["embedding_sync"]["last_error"] = str(e)[:200]
                logger.warning(f"Embedding sync failed: {e}")

            if time.time() - last_cluster >= settings.CLUSTER_INTERVAL_SECONDS:
                try:
                    run_clustering()
                    last_cluster = time.time()
                except Exception as e:
                    job_status["story_clustering"]["last_error"] = str(e)[:200]
                    logger.warning(f"Story clustering failed: {e}")
                    last_cluster = time.time()

            self._stop.wait(settings.EMBED_SYNC_INTERVAL_SECONDS)


background_jobs = BackgroundJobs()
