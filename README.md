# AI-Based News Aggregator and Summarizer

> **Advanced Cloud Computing (ACC) Micro-Project**  
> A containerized, microservices-based cloud platform that collects news from real-world RSS feeds, generates AI summaries and key takeaways using Groq LLM, groups related stories via FAISS vector similarity and Disjoint Set Union (DSU) clustering, and enables semantic search and retrieval-augmented question answering (RAG).

---

## 1. Executive Summary & Cloud Architecture

This project implements a scalable, resilient microservices system following cloud-native principles. It avoids monolithic single-points-of-failure and third-party message brokers by leveraging a database-backed job queue with row-level locks, persistent vector indices, in-memory caching, and multi-tier containerization.

### Microservices Topology

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                CLIENT / BROWSER TIER                                    │
│                                                                                         │
│        React 18 + Vite 5 Frontend Dashboard (Port 5173)                                  │
│        - Live News Feed, Category Pills, Keyword Search                                │
│        - AI Briefing & Takeaways, Context Explainer                                    │
│        - FAISS Vector Semantic Search Tab                                              │
│        - News-Grounded RAG Chatbot with Citation Links                                 │
│        - Cloud Architecture & Health Status Gauge                                      │
└───────────────────────────────────────────┬─────────────────────────────────────────────┘
                                            │ HTTP / REST (/api/*)
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CORE API GATEWAY                                        │
│                                                                                         │
│        FastAPI Asynchronous Backend (Port 8000)                                         │
│        - REST Endpoints (/api/news, /api/categories, /api/search, /api/trending)        │
│        - Semantic Vector Endpoints (/api/search/semantic, /api/news/{id}/related)       │
│        - News-Grounded RAG Endpoint (/api/chat/ask, /api/chat/explain/{id})             │
│        - Cloud Observability: Prometheus (/metrics) & Health Probe (/health)            │
│        - In-Memory / Redis Caching Layer (45s TTL for feed reads)                       │
└──────────────┬────────────────────────────┬─────────────────────────────┬───────────────┘
               │                            │                             │
               ▼                            ▼                             ▼
┌──────────────────────────────┐ ┌───────────────────────────┐ ┌──────────────────────────┐
│     PERSISTENCE TIER         │ │     VECTOR & CACHE TIER   │ │    BACKGROUND ENGINES    │
│                              │ │                           │ │                          │
│ Supabase PostgreSQL 16 (SSL) │ │ FAISS Vector Index (384d) │ │ RSS Collector Daemon     │
│ - 89+ verified articles      │ │ - BAAI/bge-small-en-v1.5  │ │ - Feedparser + HTTPX     │
│ - Alembic schema migrations  │ │ - Inner Product (Cosine)  │ │ - BBC, NPR, Ars Technica │
│ - Content hash deduplication │ │                           │ │                          │
│ - Worker Job Queue states:   │ │ Redis 7 In-Memory Cache   │ │ AI Worker Daemon         │
│   pending/processing/done    │ │ - News feed cache         │ │ - Groq API (Qwen 27B)    │
│   (SELECT FOR UPDATE SKIP    │ │ - Graceful offline fall-  │ │ - Automatic retry limits │
│    LOCKED)                   │ │   back                    │ │ - Lease timeout recovery │
└──────────────────────────────┘ └───────────────────────────┘ └──────────────────────────┘
```

---

## 2. Detailed Phase-by-Phase Implementation Review

### Phase 1 — Project Skeleton & Container Topology
- **Multi-Service Architecture:** Established cleanly separated directories for `frontend/`, `backend/`, `collector/`, `worker/`, and `monitoring/`.
- **Environment Configuration:** Implemented `.env.example` and `.env` handling secrets, percent-encoded database URLs, and port mappings.
- **Docker Compose:** Defined `docker-compose.yml` with health checks, network isolation (`news-network`), and volume persistence.

### Phase 2 — RSS Collection & Persistent Storage
- **Publisher Feeds:** Automated collection from BBC World, NPR News, Ars Technica, BBC Business, and The Verge.
- **Normalization Pipeline:** Sanitized HTML markup, resolved tracking query parameters (`utm_*`) to canonical URLs, and extracted timestamps normalized to UTC.
- **Idempotency & Deduplication:** Generates deterministic SHA-256 hashes of normalized titles and content. Enforces `ON CONFLICT (canonical_url) DO NOTHING` in PostgreSQL.
- **Live Ingest:** Successfully collected **89 verified real-world news articles** into Supabase PostgreSQL.

### Phase 3 — FastAPI REST News API
- **REST Endpoints:**
  - `GET /api/news`: Paginated feed with category, source, status, and date range filters.
  - `GET /api/news/{id}`: Single article detail lookup.
  - `GET /api/categories`: Dynamic category counts.
  - `GET /api/search`: Parameterized SQL pattern search.
  - `GET /api/trending`: Recency & cross-source prominence ranking.
  - `GET /health`: Deep database probe returning connection health.
- **Pydantic v2 Models:** Type-safe request validation and response serialization.

### Phase 4 — Worker Job Queue & Lease Management
- **Message-Broker-Free Queue:** Uses PostgreSQL row-level locks via `SELECT ... FOR UPDATE SKIP LOCKED`.
- **Worker Leases:** Acquires short transactions with lease timestamps (`locked_at`). Automatically recovers abandoned jobs if a worker crashes before completion.
- **Retry Policy:** Increments `processing_attempts` with a maximum threshold (default: 3 retries) before marking jobs `failed`.

### Phase 5 — Groq AI Summarization
- **LPU Acceleration:** Connects to Groq API with primary model `qwen/qwen3.8-27b` and automatic fallbacks to `openai/gpt-oss-120b` and `openai/gpt-oss-20b`.
- **Structured JSON Synthesis:** Produces high-quality concise summaries and bulleted key takeaways in ~1.2 seconds per story.

### Phase 6 — Vector Indexing, Semantic Search & Story Clustering
- **Embeddings:** Generates 384-dimensional dense vectors using `BAAI/bge-small-en-v1.5` on ONNX Runtime with an in-memory normalized fallback embedder.
- **FAISS Vector Index:** Implements `IndexFlatIP` with L2 normalized vectors for exact Cosine Similarity.
- **Thread & Process Safety:** Uses `threading.RLock()` and single-writer file locking (`FileLock`) for index persistence under `data/faiss_index/`.
- **Story Clustering:** Groups related articles with cosine similarity $\ge 0.80$ into deterministic story clusters using Disjoint Set Union (DSU).

### Phase 7 — News-Grounded RAG Chatbot
- **Grounded Answering:** `POST /api/chat/ask` semantically retrieves top-4 context articles from FAISS, prompts Groq LLM with strict evidence constraints, and formats answers with numbered source citations `[1]`, `[2]`.
- **Plain-English Explainer:** `GET /api/chat/explain/{id}` provides background context, historical significance, and simplified concepts for non-expert readers.

### Phase 8 — React + Vite Editorial Dashboard
- **Componentized Frontend:** Built with React 18 and Vite 5 using a modular architecture (`Navbar`, `SearchBar`, `CategoryFilter`, `NewsCard`, `ArticleDetailModal`, `LoadingSkeleton`, `EmptyState`, `ChatbotPanel`, `ArchitecturePanel`).
- **Design System:** Professional dark-mode news palette with typography tokens, responsive grid layouts for desktop/tablet/mobile, and glassmorphic modal overlays.

### Phase 9 — Caching, Metrics & Cloud Readiness
- **Redis Caching:** Integrates Redis with 45-second TTL on news feed queries, featuring seamless in-memory fallback if Redis is offline.
- **Prometheus Observability:** Exposes `GET /metrics` reporting request counters, latency histograms, article gauges, and vector index size.

---

## 3. Verified REST API Specification

| Method | Route | Description | Caching / Performance |
|---|---|---|---|
| `GET` | `/health` | Service and Supabase PostgreSQL connectivity check | Real-time probe |
| `GET` | `/metrics` | Prometheus metrics scraping endpoint | Exposition format |
| `GET` | `/api/news` | Paginated news feed with category, source, status, and date filters | Redis cached (45s TTL) |
| `GET` | `/api/news/{id}` | Detailed article view with AI summary and takeaways | Database query |
| `POST` | `/api/news/{id}/summarize` | On-demand Groq AI summarization (generates & caches summary) | Live Groq LLM + Supabase write |
| `GET` | `/api/news/{id}/related` | Top semantically similar articles ranked by cosine similarity | FAISS vector search |
| `POST` | `/api/news/sync-embeddings`| Sync newly collected PostgreSQL articles into FAISS | Single-writer locked |
| `POST` | `/api/news/cluster` | Cluster related stories using Disjoint Set Union ($\ge 0.80$) | Background clustering |
| `GET` | `/api/categories` | Categories list with live article counts | Aggregated query |
| `GET` | `/api/search?q={query}` | Parametrized keyword search across title, description, content | SQL injection safe |
| `GET` | `/api/search/semantic?q={}`| Vector search by concept/meaning | FAISS inner product |
| `GET` | `/api/trending` | Prominence & recency ranking | Deterministic algorithm |
| `POST` | `/api/chat/ask` | News-grounded RAG question answering | Groq LLM + FAISS |
| `GET` | `/api/chat/explain/{id}` | Plain-English background explainer | Groq educational prompt |

---

## 4. How to Run the Application

You can run the application either using **Docker Compose** (all services containerized) or **Locally** (standalone services).

### Option A: Running with Docker Compose (Recommended for Cloud Deployment)

#### 1. Ensure Docker Desktop is Running
Make sure Docker Desktop is launched on your machine.

#### 2. Configure Environment Variables
Verify your `.env` file exists in the project root:
```bash
# Ensure .env has your Supabase connection and Groq API key:
GROQ_API_KEY=gsk_your_groq_api_key
SUPABASE_DB_URL=postgresql://postgres.ecsxnzxccnbwypmscshv:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require
```

#### 3. Build and Start All Containers
```bash
docker compose up --build -d
```
*This starts: `news-postgres`, `news-redis`, `news-backend`, `news-frontend`, `news-collector`, and `news-worker`.*

#### 4. Verify Container Status
```bash
docker compose ps
```
All services should report `Up (healthy)` or `Up`.

#### 5. Apply Database Migrations (First Run Only)
```bash
docker compose exec backend alembic upgrade head
```

#### 6. Access the Application
- **Frontend Dashboard:** [http://localhost:5173](http://localhost:5173)
- **FastAPI Interactive Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Backend Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

#### 7. Stop Containers
```bash
docker compose down
```

---

### Option B: Running Locally (Standalone Development)

If you prefer to run services directly on your host machine without Docker:

#### 1. Free Up Ports (If Needed)
If port 5173 or 8000 is reported as already in use:
```powershell
# In PowerShell:
Get-Process -Name node, python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName
# Stop existing node or python instances if necessary:
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
```

#### 2. Run Backend API Server
```bash
python -m uvicorn app.main:app --app-dir backend --reload --port 8000 --host 0.0.0.0
```
- Available at [http://localhost:8000](http://localhost:8000)

#### 3. Run Frontend Development Server
In a new terminal:
```bash
cd frontend
npm run dev
```
- Available at [http://localhost:5173](http://localhost:5173)

#### 4. Run News RSS Collector Daemon (Collects Real-World Feeds)
In a separate terminal:
```powershell
powershell -Command "$env:PYTHONPATH='collector'; python -m app.main"
```

#### 5. Run AI Summarizer Background Worker
In a separate terminal:
```powershell
powershell -Command "$env:PYTHONPATH='worker'; python -m app.main"
```

---

## 5. Verification & Testing Matrix

The project includes 36 automated unit, integration, and end-to-end tests across all microservices:

```bash
# 1. Run Backend, Vector Store & RAG Chat Test Suite (20 tests)
python -m pytest backend/tests -v

# 2. Run Collector Test Suite (12 tests)
powershell -Command "$env:PYTHONPATH='collector'; python -m pytest collector/tests -v"

# 3. Run Worker Test Suite (4 tests)
powershell -Command "$env:PYTHONPATH='worker'; python -m pytest worker/tests -v"
```

### Test Results Breakdown (100% Passing)

| Test Module | Coverage Area | Tests | Status |
|---|---|---|---|
| `backend/tests/test_api.py` | Health probe, pagination, categories, search, trending, `/metrics` | 11 | ✅ 11/11 Passed |
| `backend/tests/test_vector_store.py` | FAISS indexing, reload persistence, semantic search, clustering, RAG chat | 7 | ✅ 7/7 Passed |
| `backend/tests/test_health.py` | Root discovery dictionary, health status reporting | 2 | ✅ 2/2 Passed |
| `collector/tests/test_fetcher.py` | Feedparser handling, HTTP timeouts, network resilience | 4 | ✅ 4/4 Passed |
| `collector/tests/test_normalizer.py` | HTML sanitation, canonical URLs, SHA-256 deduplication | 5 | ✅ 5/5 Passed |
| `collector/tests/test_pipeline.py` | End-to-end collection pipeline and duplicate rejection | 1 | ✅ 1/1 Passed |
| `collector/tests/test_repository.py` | PostgreSQL repository insert idempotency | 2 | ✅ 2/2 Passed |
| `worker/tests/test_worker_queue.py` | PostgreSQL `SKIP LOCKED` claims, lease timeouts, retry limits, batching | 4 | ✅ 4/4 Passed |
| **Total** | **Full System Verification** | **36** | **✅ 36/36 Passed (100%)** |

---

## 6. Academic Cloud Computing Rubric Alignment

| Rubric Dimension | Project Implementation Evidence |
|---|---|
| **Containerization** | Multi-stage Dockerfiles for backend, frontend, collector, and worker. Multi-service Docker Compose with network segmentation and volumes. |
| **Microservices Decoupling** | Independent processes: Collector runs as an autonomous ingest daemon; Worker executes independently; FastAPI serves client traffic; React runs on a dedicated frontend server. |
| **Database & Schema Governance** | Supabase PostgreSQL 16 with SSL encryption, connection pooling, and versioned Alembic migrations (`0001_create_articles_table.py`, `0002_add_worker_lease_columns.py`). |
| **Safe Job Queueing** | Concurrency control via PostgreSQL `FOR UPDATE SKIP LOCKED`, preventing double-processing and race conditions without heavy message broker dependencies. |
| **Vector Search & RAG** | High-performance FAISS vector index with 384-dimensional dense ONNX embeddings, cosine similarity ranking, Disjoint Set Union story clustering, and Groq LLM retrieval-augmented answering. |
| **Resilience & Caching** | Redis 7 caching with 45s TTL and graceful offline fallback; database connection failure handling with HTTP 503 degraded status. |
| **Cloud Observability** | Standard Prometheus exposition format at `/metrics` tracking request latency, throughput, and database health. |
