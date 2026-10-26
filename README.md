# AI-Based News Aggregator and Summarizer

> **Advanced Cloud Computing (ACC) Micro-Project** — a containerised, event-driven microservices platform that collects news from RSS feeds and news APIs, summarises and enriches every story with AI, compares how different outlets cover the same story, personalises the feed for each reader, and is fully observable with Prometheus and Grafana.

Everything runs with **one command** and **no API keys** (offline fallbacks for every AI feature). Adding a free Groq key upgrades summaries, chat, briefings, translation and the Perspective Lens analysis to LLM quality.

---

## 1. Quick start

```bash
git clone https://github.com/SakshiKukreja04/ACC_Micro_Project
cd ACC_Micro_Project
cp .env.example .env          # optional: add GROQ_API_KEY=gsk_...
docker compose up --build -d
```

| What | URL |
|---|---|
| News dashboard | http://localhost:5173 |
| System monitor (in-app) | http://localhost:5173/#monitor |
| API docs (Swagger) | http://localhost:8000/docs |
| Grafana (anonymous view, admin/admin to edit) | http://localhost:3000 |
| Prometheus targets / alerts | http://localhost:9090/targets · http://localhost:9090/alerts |
| Raw metrics | http://localhost:8000/metrics |

First start takes a few minutes: the backend downloads the 130 MB `bge-small-en-v1.5` embedding model and applies database migrations automatically; the collector then fetches feeds and the worker summarises them.

```bash
docker compose ps                              # everything Up / healthy
docker compose logs -f worker                  # watch articles being summarised
docker compose up -d --scale worker=3          # horizontal scaling of the AI worker
docker compose --profile cadvisor up -d        # add per-container CPU / memory metrics
docker compose down                            # stop (add -v to wipe data)
```

**No internet for feeds (e.g. campus Wi-Fi blocks them)?** With the default `SEED_DEMO_DATA=auto`, if no feed is reachable on first start the collector loads 32 clearly-labelled offline demo stories (every publisher is prefixed "Demo", URLs point to `demo.newsroom.local`) so every feature can still be shown. Force it any time with `docker compose exec collector python -m app.main --seed-demo`.

---

## 2. Architecture

```text
                         ┌──────────────────────────── Browser ────────────────────────────┐
                         │ React 19 + Vite dashboard  (feed · For You · Lens · Insights ·  │
                         │ Ask AI · Saved · System monitor)   ◄── SSE live notifications   │
                         └───────────────┬─────────────────────────────────────────────────┘
                                         │ REST /api/*  +  text/event-stream
┌──────────────┐   rows: pending   ┌─────▼──────────────────────┐        ┌──────────────────┐
│  Collector   │──────────────────►│  FastAPI backend           │◄──────►│ Redis 7 (cache)  │
│ RSS + NewsAPI│   PostgreSQL 16   │  REST · RAG · Lens · SSE   │        └──────────────────┘
│ + GNews      │◄─────────────────►│  FAISS index (bge-small)   │        ┌──────────────────┐
│ :9102/metrics│                   │  background embed/cluster  │◄──────►│ Groq LLM (ext.)  │
└──────────────┘                   │  Alembic migrations        │        └──────────────────┘
        ▲                          │  :8000/metrics             │
        │                          └─────────────┬──────────────┘
        │        FOR UPDATE SKIP LOCKED          │
┌───────┴──────┐  claim → summarise → enrich     │
│  AI worker ×N│◄────────────────────────────────┘ (shared PostgreSQL job queue)
│ :9101/metrics│
└──────────────┘
──────────────────────────────── Monitoring tier ─────────────────────────────────────────
 Prometheus ◄── backend · worker (DNS discovery of every replica) · collector ·
                postgres-exporter · redis-exporter · cAdvisor (optional profile)
 Grafana    ◄── provisioned datasource + 41-panel dashboard · 13 alert rules in Prometheus
```

| Container | Image / build | Role |
|---|---|---|
| `frontend` | `./frontend` (Node 20) | React dashboard, Vite proxy to the API |
| `backend` | `./backend` (Python 3.11) | REST API, RAG, Perspective Lens, personalisation, SSE, FAISS, metrics; runs migrations on start |
| `collector` | `./collector` | 12 RSS feeds + optional NewsAPI/GNews, normalisation, topic classification, dedup |
| `worker` (scalable) | `./worker` | Claims jobs with `SKIP LOCKED`, Groq/extractive summaries, sentiment, Fact-Grounding, keywords |
| `postgres` | `postgres:16-alpine` | Articles, job queue state, bookmarks, reading history |
| `redis` | `redis:7-alpine` | Feed/insight/briefing/translation cache (LRU, 256 MB) |
| `prometheus` | `prom/prometheus:v2.55.1` | Scrapes 6 jobs, evaluates 13 alert rules, 15-day retention |
| `grafana` | `grafana/grafana:11.3.0` | Provisioned dashboard (home page), anonymous viewer |
| `postgres-exporter`, `redis-exporter` | community exporters | Database and cache internals |
| `cadvisor` (profile) | `gcr.io/cadvisor/cadvisor` | Container CPU / memory |

The original slides list Amazon SQS as the queue. This build implements the same decoupling with a PostgreSQL row-lock queue (`SELECT … FOR UPDATE SKIP LOCKED` + lease timeouts + bounded retries), so it runs locally with no cloud account; swapping in SQS only changes `worker/app/queue.py`.

---

## 3. Features

### Monitoring & observability (new)
* **Instrumented HTTP middleware** — every request records `news_http_requests_total`, latency histogram and in-flight gauge with **templated endpoint labels** (`/api/news/{article_id}`), plus `X-Request-ID` / `X-Process-Time` headers. (Previously the request metrics were defined but never incremented.)
* **Structured JSON logs** with request correlation IDs (`LOG_FORMAT=json`), ready for Loki/ELK/CloudWatch.
* **Metrics in every service** — worker (`:9101`: job outcomes, duration, queue depth, recoveries, grounding histogram, LLM calls per model) and collector (`:9102`: per-source fetched / inserted / duplicates / errors, last success, cycle duration).
* **Business & AI metrics** — articles by status, sentiment and category, ingestion last hour, average Fact-Grounding score, cache hit/miss, Groq calls and latency per operation, RAG retrieval sizes, FAISS vectors, story clusters, live SSE readers.
* **Grafana dashboard** (auto-provisioned, 41 panels): service health, RED metrics, pipeline, AI/LLM, PostgreSQL, Redis, container resources, live alert list. Regenerate with `python scripts/generate_grafana_dashboard.py`.
* **13 Prometheus alert rules**: service down, no worker replica running, DB/Redis unavailable, error rate > 5 %, p95 > 1 s, AI backlog, worker stalled, job failures, collector stale, failing feed, LLM errors, low grounding.
* **In-app System Monitor** (`/#monitor`): the backend actively probes PostgreSQL, Redis, FAISS and Groq and scrapes the worker/collector/Prometheus endpoints, showing live service tiles, API p95/p99, error rate, sparklines, the collector→queue→worker flow, per-source feed health, cache hit ratio and LLM usage — no Grafana login needed.
* **Horizontal scaling ready** — the worker has no fixed container name and Prometheus discovers every replica via DNS.

### Unique selling points
1. **Perspective Lens** — for any story, finds coverage of the same event by other publishers (FAISS similarity + DSU story clusters), plots each outlet on a **tone scale**, shows what each outlet mentions that others don't, the facts they share, a **Coverage Agreement Index** and tone gap, and a balanced account (LLM-written with Groq; deterministic otherwise).
2. **Fact-Grounding score** — every AI summary is checked against its source: the share of the summary's content words traceable to the article. Shown as a badge on each card, averaged in Grafana, and alerted on when it drops. A cheap, model-independent hallucination signal.
3. **Story Timeline** — how a story developed across outlets in chronological order, and who reported it first.
4. **Privacy-first personalisation** — "For You" recommendations from the reader's own reading vector (recency-weighted mean of FAISS embeddings of what they opened, listened to or saved), each with a **"Because you read …"** explanation. No account: an anonymous browser ID, plus one-click **Erase my data**.
5. **Listen & read in your language** — text-to-speech of any briefing, and translation of summaries into 10 Indian and 6 global languages (Hindi, Marathi, Tamil, Telugu, Bengali, Gujarati, Kannada, Malayalam, Punjabi, Urdu, Spanish, French, German, Arabic, Japanese, Chinese), cached for 24 h.
6. **Works fully offline** — extractive summariser, lexical embeddings with calibrated thresholds, demo dataset: the demo never breaks because of a missing key or blocked network.

### Additional features
* **AI Daily Briefing** — a one-minute digest of the top stories with clickable `[n]` citations (cached 30 min).
* **Sentiment analysis** on every article (sentence-averaged VADER, headline weighted), tone filter on the feed.
* **Insights** — rising-topic detection (keyword spike vs. previous window), coverage by category, tone by publisher and category, stories per hour.
* **Real-time notifications** — Server-Sent Events push "N new stories" toasts when the collector stores articles.
* **Bookmarks & reading history** (Saved tab).
* **RAG chat with follow-up memory** — previous turns are used for retrieval and answering.
* **Better trending** — multi-source coverage boost and cluster diversity.
* **Topic classification** into 10 canonical categories (keywords + LLM refinement) instead of raw feed tags.
* **More sources** — 12 RSS feeds (BBC World/Business/Science/Health/Sport/Entertainment, NPR, Ars Technica, The Verge, The Hindu, Times of India, Al Jazeera), optional **NewsAPI / GNews**, and `EXTRA_RSS_FEEDS` / `DISABLED_RSS_FEEDS` without code changes.
* **Automatic FAISS maintenance** — new articles are embedded every 60 s and stories re-clustered every 5 min (previously embeddings were only built when the index was empty). The index records which model built it and rebuilds if the model changes.

### Fixes to the original code
* Frontend container pointed the browser at `http://localhost:8000/news` (missing `/api`) — now uses the Vite proxy.
* `status` query parameter shadowed `fastapi.status`, breaking error responses on the news feed.
* Request metrics were never recorded; `/metrics` initialised the embedding model on every scrape.
* Failed feeds were counted as successful collections.
* Redis was disabled forever after one failed connection; it now retries every 30 s.
* Migrations were manual and failed if a service had already created the table; they are now idempotent and run on backend start.
* The worker's abandoned-lease message logged `None` instead of the original lock time.
* `.btn-card-primary` was used but never styled.

---

## 4. API reference

| Method | Route | Purpose |
|---|---|---|
| GET | `/health`, `/metrics` | Health probe, Prometheus metrics |
| GET | `/api/monitoring/overview` | Aggregated live health of all services |
| GET | `/api/news` | Feed (filters: category, source, status, cluster_id, **sentiment**, dates) |
| GET | `/api/news/{id}` · `/related` | Article detail · FAISS-similar stories |
| POST | `/api/news/{id}/summarize` | On-demand summary + enrichment |
| GET | `/api/news/{id}/perspectives` | **Perspective Lens** |
| GET | `/api/news/{id}/timeline` | **Story Timeline** |
| GET | `/api/news/{id}/translate?lang=hi` | Translated summary · `/api/news/meta/languages` |
| GET | `/api/trending` · `/api/categories` | Trending (coverage-boosted) · categories |
| GET | `/api/search?q=` · `/api/search/semantic?q=` | Keyword · meaning-based search |
| GET | `/api/briefing` | AI Daily Briefing |
| POST | `/api/chat/ask` | RAG chat (with `history` for follow-ups) |
| GET | `/api/chat/explain/{id}` | Plain-English explainer |
| GET | `/api/insights/overview` · `/api/insights/topics` | Analytics · rising topics |
| GET/PUT/DELETE | `/api/me/bookmarks[/{id}]` | Reading list (`X-Client-Id` header) |
| POST/GET | `/api/me/events` · `/api/me/history` | Reading history |
| GET | `/api/me/for-you` | Personalised recommendations with reasons |
| DELETE | `/api/me` | Erase all reader data |
| GET | `/api/stream/events` | Server-Sent Events (`new_articles`, `summaries_ready`) |
| POST | `/api/news/sync-embeddings` · `/api/news/cluster` | Manual FAISS sync / clustering |

---

## 5. Configuration

All settings live in `.env` (see `.env.example`). The important ones:

| Variable | Default | Effect |
|---|---|---|
| `GROQ_API_KEY` | empty | Enables LLM summaries, chat, briefing, Lens analysis, translation |
| `GROQ_MODELS` | built-in chain | Comma-separated model fallback order |
| `SEED_DEMO_DATA` | `auto` | `auto` / `true` / `false` offline demo stories |
| `NEWSAPI_KEY`, `GNEWS_API_KEY` | empty | Extra sources (polled hourly to respect free quotas) |
| `EXTRA_RSS_FEEDS` | empty | `Name|URL|Category;…` |
| `EMBEDDING_BACKEND` | `fastembed` | `fallback` skips the model download |
| `SUPABASE_DB_URL` | empty | Use Supabase instead of the local PostgreSQL container |
| `LOG_FORMAT` | `json` | `text` for human-readable logs |
| `WORKER_BATCH_SIZE`, `COLLECTION_INTERVAL_SECONDS` | 10, 300 | Throughput tuning |

---

## 6. Running without Docker

```bash
# Postgres + Redis running locally, then:
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt -r worker/requirements.txt -r collector/requirements.txt
cd backend && alembic upgrade head && uvicorn app.main:app --port 8000      # terminal 1
PYTHONPATH=worker python -m app.main                                          # terminal 2 (repo root)
PYTHONPATH=collector python -m app.main                                       # terminal 3 (repo root)
cd frontend && npm install && npm run dev                                     # terminal 4
```
On PowerShell set the path with `$env:PYTHONPATH='worker'; python -m app.main`. Locally the backend expects worker/collector metrics at `localhost:9101` / `localhost:9102` — set `WORKER_METRICS_URL` and `COLLECTOR_METRICS_URL` accordingly.

---

## 7. Tests

```bash
cd backend && python -m pytest tests -q          # 33 tests (needs DB with articles; seed with --seed-demo)
cd .. && PYTHONPATH=worker python -m pytest worker/tests -q        # 7 tests
PYTHONPATH=collector python -m pytest collector/tests -q          # 15 tests
```
New tests cover enrichment (sentiment ordering, grounding detects invented summaries, classifier), templated metrics and request IDs, the monitor endpoint, the full bookmark → history → For You → erase flow, Perspective Lens/Timeline invariants, insights, briefing citations, SSE, the sentiment filter, extractive-summary deduplication, demo seeding and feed-failure accounting. One vector-store test is skipped automatically when the offline lexical embedder is active because it needs true semantic understanding.

---

## 8. Suggested viva demo (5 minutes)

1. `docker compose ps` — 10 containers healthy. Open **Grafana** (home dashboard) and **Prometheus → Targets** (6 jobs up; cAdvisor only with its profile).
2. Dashboard → **Top stories**: AI briefing with citations, tone filter, grounding badges.
3. Open the climate or interest-rate story → **Other outlets**: tone scale, outlet columns, agreement index. Then **Timeline**, **Listen**, **Read in Hindi**.
4. Open two or three stories → **For you** shows recommendations with "Because you read …". **Saved → Erase my data** resets it.
5. **Insights**: rising topics and tone by publisher. **Ask AI**: ask a question, then a follow-up.
6. **System**: live service tiles and pipeline. Run `docker compose stop worker` — the AI Worker tile turns red within seconds and the `NoWorkerRunning` alert goes pending, then firing, in Prometheus. `docker compose start worker` recovers it.
7. `docker compose up -d --scale worker=3` — Prometheus discovers three worker targets; `SKIP LOCKED` guarantees no article is processed twice.
