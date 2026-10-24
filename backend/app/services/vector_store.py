import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import faiss
import numpy as np
from filelock import FileLock

logger = logging.getLogger("backend.services.vector_store")

EMBEDDING_DIM = 384
DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class FallbackEmbedder:
    """Deterministic 384-dimensional fallback embedder in case model fails to load."""

    def __init__(self, dim: int = EMBEDDING_DIM):
        self.dim = dim

    def embed(self, texts: List[str]):
        import hashlib

        vectors = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            words = text.lower().split()
            if not words:
                words = ["empty"]
            for i, word in enumerate(words):
                h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h % 2 == 0) else -1.0
                vec[idx] += sign * (1.0 / (1.0 + (i * 0.05)))
            norm = np.linalg.norm(vec)
            if norm > 1e-6:
                vec = vec / norm
            vectors.append(vec)
        return iter(vectors)


class VectorStoreService:
    """FAISS-backed vector store for semantic news search and related story clustering."""

    _instance: Optional["VectorStoreService"] = None
    _shared_embedder = None
    _singleton_lock = threading.Lock()
    _embedder_lock = threading.Lock()

    def __init__(self, storage_dir: Optional[str] = None):
        self._lock = threading.RLock()
        if storage_dir is None:
            # Default to backend/data/faiss_index or data/faiss_index relative to project root
            base_dir = Path(__file__).resolve().parent.parent.parent
            storage_dir = os.getenv("FAISS_INDEX_DIR", str(base_dir / "data" / "faiss_index"))

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.storage_dir / "index.faiss"
        self.metadata_file = self.storage_dir / "metadata.json"
        self.lock_file = self.storage_dir / "index.lock"

        self.dim = EMBEDDING_DIM
        self.embedder = None
        self._init_embedder()

        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.dim)
        self.id_list: List[str] = []
        self.id_to_idx: Dict[str, int] = {}

        self.load_index()

    def _init_embedder(self):
        """Initialize the fastembed TextEmbedding model once with graceful fallback."""
        if VectorStoreService._shared_embedder is not None:
            self.embedder = VectorStoreService._shared_embedder
            return

        with VectorStoreService._embedder_lock:
            if VectorStoreService._shared_embedder is None:
                try:
                    from fastembed import TextEmbedding

                    VectorStoreService._shared_embedder = TextEmbedding(model_name=DEFAULT_MODEL_NAME)
                    logger.info(f"Loaded fastembed model: {DEFAULT_MODEL_NAME}")
                except Exception as e:
                    logger.warning(f"Could not load fastembed model: {e}. Using deterministic fallback embedder.")
                    VectorStoreService._shared_embedder = FallbackEmbedder(self.dim)
            self.embedder = VectorStoreService._shared_embedder

    def _get_text_representation(self, title: str, description: Optional[str] = None, content: Optional[str] = None) -> str:
        """Construct representative text for semantic vectorization."""
        parts = [title.strip()]
        if description:
            desc_clean = description.strip()
            if desc_clean and desc_clean != title.strip():
                parts.append(desc_clean[:300])
        elif content:
            parts.append(content.strip()[:300])
        return ". ".join(parts)

    def load_index(self):
        """Load FAISS index and article ID metadata from disk if available."""
        with self._lock:
            if self.index_file.exists() and self.metadata_file.exists():
                try:
                    loaded_index = faiss.read_index(str(self.index_file))
                    with open(self.metadata_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)

                    self.index = loaded_index
                    self.id_list = meta.get("id_list", [])
                    self.id_to_idx = {art_id: idx for idx, art_id in enumerate(self.id_list)}
                    logger.info(f"Loaded FAISS index with {self.index.ntotal} vectors from {self.index_file}")
                    return
                except Exception as e:
                    logger.error(f"Failed to load FAISS index from {self.index_file}: {e}. Reinitializing empty.")

            # Initialize fresh empty index
            self.index = faiss.IndexFlatIP(self.dim)
            self.id_list = []
            self.id_to_idx = {}

    def save_index(self):
        """Persist FAISS index and article ID metadata to disk using a file lock."""
        with self._lock:
            try:
                with FileLock(str(self.lock_file), timeout=5):
                    faiss.write_index(self.index, str(self.index_file))
                    with open(self.metadata_file, "w", encoding="utf-8") as f:
                        json.dump({"id_list": self.id_list}, f, indent=2)
                    logger.info(f"Persisted FAISS index with {self.index.ntotal} vectors to {self.index_file}")
            except Exception as e:
                logger.warning(f"FileLock bypassed during save: {e}. Writing directly.")
                faiss.write_index(self.index, str(self.index_file))
                with open(self.metadata_file, "w", encoding="utf-8") as f:
                    json.dump({"id_list": self.id_list}, f, indent=2)

    def add_articles(self, articles: List[Dict[str, Any]]) -> int:
        """
        Embed and index new articles.
        Skips articles that are already present in the index.
        Returns the number of newly added articles.
        """
        articles_to_add = [a for a in articles if a.get("id") and a["id"] not in self.id_to_idx]
        if not articles_to_add:
            return 0

        texts = [
            self._get_text_representation(
                title=a.get("title", ""),
                description=a.get("description"),
                content=a.get("content"),
            )
            for a in articles_to_add
        ]

        try:
            embeddings_gen = self.embedder.embed(texts)
            embeddings = np.array(list(embeddings_gen), dtype=np.float32)
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}. Using fallback.")
            fallback = FallbackEmbedder(self.dim)
            embeddings = np.array(list(fallback.embed(texts)), dtype=np.float32)

        # Normalize vectors for cosine similarity (Inner Product = Cosine on normalized vectors)
        faiss.normalize_L2(embeddings)

        with self._lock:
            start_idx = self.index.ntotal
            self.index.add(embeddings)
            for i, a in enumerate(articles_to_add):
                art_id = str(a["id"])
                self.id_list.append(art_id)
                self.id_to_idx[art_id] = start_idx + i

        self.save_index()
        logger.info(f"Successfully added {len(articles_to_add)} articles to FAISS index. Total: {self.index.ntotal}")
        return len(articles_to_add)

    def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> List[Tuple[str, float]]:
        """
        Perform semantic search for a query string.
        Returns list of (article_id, cosine_similarity_score).
        """
        if self.index.ntotal == 0 or not query.strip():
            return []

        try:
            query_vec_gen = self.embedder.embed([query.strip()])
            query_vec = np.array(list(query_vec_gen), dtype=np.float32)
        except Exception as e:
            logger.error(f"Query embedding generation failed: {e}. Using fallback.")
            fallback = FallbackEmbedder(self.dim)
            query_vec = np.array(list(fallback.embed([query.strip()])), dtype=np.float32)

        faiss.normalize_L2(query_vec)

        k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_vec, k)

        results: List[Tuple[str, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.id_list):
                continue
            cos_score = float(score)
            if cos_score >= min_score:
                results.append((self.id_list[idx], cos_score))

        return results

    def find_related(self, article_id: str, top_k: int = 5, min_score: float = 0.45) -> List[Tuple[str, float]]:
        """
        Find related articles for a given article ID using FAISS vector similarity.
        Excludes the query article itself.
        """
        if self.index.ntotal <= 1:
            return []

        if article_id not in self.id_to_idx:
            return []

        art_idx = self.id_to_idx[article_id]
        # Reconstruct normalized vector from index
        target_vec = np.zeros((1, self.dim), dtype=np.float32)
        self.index.reconstruct(art_idx, target_vec[0])

        k = min(top_k + 1, self.index.ntotal)
        scores, indices = self.index.search(target_vec, k)

        results: List[Tuple[str, float]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.id_list):
                continue
            found_id = self.id_list[idx]
            if found_id == article_id:
                continue  # Skip self
            cos_score = float(score)
            if cos_score >= min_score:
                results.append((found_id, cos_score))
            if len(results) >= top_k:
                break

        return results

    def sync_from_database(self, db) -> int:
        """
        Scan database for articles not yet indexed in FAISS and index them.
        Returns the number of articles added.
        """
        from app.models.article import Article
        from sqlalchemy import select

        articles = db.scalars(select(Article)).all()
        article_dicts = [a.to_dict() for a in articles]
        return self.add_articles(article_dicts)

    def cluster_articles(self, db, threshold: float = 0.82) -> Dict[str, str]:
        """
        Compute story clusters for articles in database where pairwise similarity >= threshold.
        Assigns cluster_id to related stories and commits to DB.
        Returns a mapping of article_id -> cluster_id.
        """
        from app.models.article import Article
        from sqlalchemy import select

        if self.index.ntotal < 2:
            return {}

        # Ensure index is up to date with DB
        self.sync_from_database(db)

        # Union-Find / Disjoint Set Union (DSU) for clustering
        parent: Dict[str, str] = {art_id: art_id for art_id in self.id_list}

        def find(u: str) -> str:
            path = []
            while parent[u] != u:
                path.append(u)
                u = parent[u]
            for node in path:
                parent[node] = u
            return u

        def union(u: str, v: str):
            root_u = find(u)
            root_v = find(v)
            if root_u != root_v:
                # Deterministic root: pick lexicographically smaller ID
                if root_u < root_v:
                    parent[root_v] = root_u
                else:
                    parent[root_u] = root_v

        # For each article, find top nearest neighbors
        for art_id in self.id_list:
            related = self.find_related(art_id, top_k=10, min_score=threshold)
            for other_id, score in related:
                union(art_id, other_id)

        # Form clusters: only group when cluster size > 1
        clusters_by_root: Dict[str, List[str]] = {}
        for art_id in self.id_list:
            root = find(art_id)
            clusters_by_root.setdefault(root, []).append(art_id)

        cluster_assignments: Dict[str, str] = {}
        for root, members in clusters_by_root.items():
            if len(members) > 1:
                cluster_label = f"cluster_{root[:8]}"
                for m in members:
                    cluster_assignments[m] = cluster_label

        # Update in database
        updated_count = 0
        all_articles = db.scalars(select(Article)).all()
        for art in all_articles:
            target_cluster = cluster_assignments.get(art.id)
            if art.cluster_id != target_cluster:
                art.cluster_id = target_cluster
                updated_count += 1

        if updated_count > 0:
            db.commit()
            logger.info(f"Assigned clusters to {updated_count} articles in database.")

        return cluster_assignments


def get_vector_store() -> VectorStoreService:
    """Dependency / Singleton provider for VectorStoreService."""
    if VectorStoreService._instance is None:
        with VectorStoreService._singleton_lock:
            if VectorStoreService._instance is None:
                VectorStoreService._instance = VectorStoreService()
    return VectorStoreService._instance
