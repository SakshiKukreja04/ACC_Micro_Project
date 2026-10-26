"""
Generates monitoring/grafana/dashboards/news-aggregator.json — the provisioned Grafana dashboard.

Run from the project root after changing panels:
    python scripts/generate_grafana_dashboard.py
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
OUT = Path(__file__).resolve().parent.parent / "monitoring" / "grafana" / "dashboards" / "news-aggregator.json"

panels = []
_id = [0]
_y = [0]


def nid():
    _id[0] += 1
    return _id[0]


def row(title):
    panels.append({"type": "row", "title": title, "id": nid(), "collapsed": False,
                   "gridPos": {"h": 1, "w": 24, "x": 0, "y": _y[0]}, "panels": []})
    _y[0] += 1


def target(expr, legend="", ref="A", instant=False):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t["instant"] = True
    return t


def stat(title, expr, x, w=3, h=4, unit="short", decimals=None, thresholds=None, description="", color_mode="value"):
    steps = thresholds or [{"color": "green", "value": None}]
    p = {
        "type": "stat", "title": title, "id": nid(), "datasource": DS, "description": description,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": [target(expr)],
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps},
                                     "color": {"mode": "thresholds"}}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": color_mode, "graphMode": "area", "justifyMode": "center", "textMode": "auto"},
    }
    if decimals is not None:
        p["fieldConfig"]["defaults"]["decimals"] = decimals
    panels.append(p)


def ts(title, targets, x, w=12, h=8, unit="short", stack=False, bars=False, description=""):
    panels.append({
        "type": "timeseries", "title": title, "id": nid(), "datasource": DS, "description": description,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": [target(e, l, chr(65 + i)) for i, (e, l) in enumerate(targets)],
        "fieldConfig": {"defaults": {
            "unit": unit,
            "custom": {"drawStyle": "bars" if bars else "line", "lineWidth": 2, "fillOpacity": 18,
                       "showPoints": "never", "stacking": {"mode": "normal" if stack else "none"},
                       "spanNulls": True},
        }, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}},
    })


def bargauge(title, expr, legend, x, w=8, h=8, unit="short"):
    panels.append({
        "type": "bargauge", "title": title, "id": nid(), "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}}, "overrides": []},
        "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"], "values": False}},
    })


def pie(title, expr, legend, x, w=8, h=8):
    panels.append({
        "type": "piechart", "title": title, "id": nid(), "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": [target(expr, legend, instant=True)],
        "options": {"pieType": "donut", "legend": {"displayMode": "table", "placement": "right", "values": ["value"]},
                    "reduceOptions": {"calcs": ["lastNotNull"], "values": False}},
        "fieldConfig": {"defaults": {"color": {"mode": "palette-classic"}}, "overrides": []},
    })


def table(title, targets, x, w=12, h=8):
    panels.append({
        "type": "table", "title": title, "id": nid(), "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": _y[0]},
        "targets": [{**target(e, l, chr(65 + i), instant=True), "format": "table"} for i, (e, l) in enumerate(targets)],
        "transformations": [{"id": "merge", "options": {}},
                            {"id": "organize", "options": {"excludeByName": {"Time": True}}}],
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"showHeader": True},
    })


def advance(h):
    _y[0] += h


RED, AMBER, GREEN = "red", "orange", "green"

# ------------------------------------------------------------------------------- 1. Overview
row("Service Health Overview")
stat("Services Up", 'sum(up{job=~"backend|worker|collector|postgres|redis"})', 0,
     thresholds=[{"color": RED, "value": None}, {"color": AMBER, "value": 4}, {"color": GREEN, "value": 5}],
     description="Backend, worker, collector, Postgres and Redis targets reachable by Prometheus (of 5)")
stat("Requests / s", "sum(rate(news_http_requests_total[2m]))", 3, unit="reqps", decimals=2)
stat("Error Rate", '(sum(rate(news_http_requests_total{status_code=~"5.."}[5m])) or vector(0)) / clamp_min(sum(rate(news_http_requests_total[5m])), 1e-9)',
     6, unit="percentunit", decimals=2,
     thresholds=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 0.01}, {"color": RED, "value": 0.05}])
stat("API p95 Latency", "histogram_quantile(0.95, sum by (le) (rate(news_http_request_duration_seconds_bucket[5m])))",
     9, unit="s", decimals=3,
     thresholds=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 0.5}, {"color": RED, "value": 1}])
stat("Articles Stored", "sum(news_articles_total)", 12, color_mode="background",
     thresholds=[{"color": "blue", "value": None}])
stat("AI Backlog (pending)", 'news_articles_by_status{status="pending"}', 15,
     thresholds=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 25}, {"color": RED, "value": 100}])
stat("Fact-Grounding (avg)", "news_summary_grounding_score_avg", 18, unit="percentunit", decimals=1,
     thresholds=[{"color": RED, "value": None}, {"color": AMBER, "value": 0.6}, {"color": GREEN, "value": 0.8}],
     description="USP: share of summary content words traceable to the source article")
stat("Cache Hit Ratio", 'sum(news_cache_operations_total{result="hit"}) / clamp_min(sum(news_cache_operations_total{result=~"hit|miss"}), 1)',
     21, unit="percentunit", decimals=1,
     thresholds=[{"color": AMBER, "value": None}, {"color": GREEN, "value": 0.3}])
advance(4)

# ------------------------------------------------------------------------------- 2. API
row("API Gateway — RED Metrics (Rate · Errors · Duration)")
ts("Request Rate by Endpoint", [("sum by (endpoint) (rate(news_http_requests_total{endpoint!~\"/metrics|/health\"}[2m]))", "{{endpoint}}")], 0, unit="reqps", stack=True)
ts("Latency Percentiles", [
    ("histogram_quantile(0.50, sum by (le) (rate(news_http_request_duration_seconds_bucket[5m])))", "p50"),
    ("histogram_quantile(0.95, sum by (le) (rate(news_http_request_duration_seconds_bucket[5m])))", "p95"),
    ("histogram_quantile(0.99, sum by (le) (rate(news_http_request_duration_seconds_bucket[5m])))", "p99"),
], 12, unit="s")
advance(8)
ts("Responses by Status Code", [("sum by (status_code) (rate(news_http_requests_total[2m]))", "{{status_code}}")], 0, w=8, unit="reqps", stack=True)
ts("Slowest Endpoints (p95)", [("topk(6, histogram_quantile(0.95, sum by (le, endpoint) (rate(news_http_request_duration_seconds_bucket[10m]))))", "{{endpoint}}")], 8, w=8, unit="s")
ts("In-flight Requests & Live Readers (SSE)", [("news_http_requests_in_progress", "in-flight"), ("news_sse_clients", "live SSE readers")], 16, w=8)
advance(8)

# ------------------------------------------------------------------------------- 3. Pipeline
row("Event-Driven Pipeline — Collector → Queue → AI Worker")
ts("Queue Depth by Status", [("news_articles_by_status", "{{status}}")], 0, w=8)
ts("Worker Throughput", [("sum by (outcome) (rate(news_worker_jobs_total[5m])) * 60 or label_replace(vector(0), \"outcome\", \"completed\", \"\", \"\")", "{{outcome}} / min")], 8, w=8, stack=True, bars=True)
ts("Worker Job Duration", [
    ("histogram_quantile(0.5, sum by (le) (rate(news_worker_job_duration_seconds_bucket[10m])))", "p50"),
    ("histogram_quantile(0.95, sum by (le) (rate(news_worker_job_duration_seconds_bucket[10m])))", "p95"),
], 16, w=8, unit="s")
advance(8)
ts("Articles Ingested per Source", [("sum by (source) (increase(news_collector_articles_inserted_total[30m]))", "{{source}}")], 0, w=12, stack=True, bars=True)
table("Collector Source Health", [
    ("sum by (source) (news_collector_articles_fetched_total)", "fetched"),
    ("sum by (source) (news_collector_articles_inserted_total)", "inserted"),
    ("sum by (source) (news_collector_feed_errors_total)", "errors"),
    ("time() - max by (source) (news_collector_last_success_timestamp_seconds)", "seconds since success"),
], 12, w=12)
advance(8)
stat("Seconds Since Worker Batch", "time() - news_worker_last_batch_timestamp_seconds", 0, w=6, unit="s",
     thresholds=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 60}, {"color": RED, "value": 180}])
stat("Seconds Since Collector Cycle", "time() - news_collector_last_cycle_timestamp_seconds", 6, w=6, unit="s",
     thresholds=[{"color": GREEN, "value": None}, {"color": AMBER, "value": 600}, {"color": RED, "value": 900}])
stat("Recovered Abandoned Jobs", "sum(news_worker_recovered_jobs_total)", 12, w=6,
     description="Jobs reclaimed after a worker crashed mid-lease (SELECT … FOR UPDATE SKIP LOCKED + lease timeout)")
stat("FAISS Vectors", "news_faiss_vectors_total", 18, w=6, thresholds=[{"color": "purple", "value": None}])
advance(4)

# ------------------------------------------------------------------------------- 4. AI
row("AI & LLM — Groq · RAG · Sentiment · Grounding")
ts("Groq Calls by Operation", [("sum by (operation, outcome) (rate(news_llm_requests_total[5m])) * 60", "{{operation}} · {{outcome}}")], 0, w=8)
ts("Groq Latency p95 by Operation", [("histogram_quantile(0.95, sum by (le, operation) (rate(news_llm_request_duration_seconds_bucket[10m])))", "{{operation}}")], 8, w=8, unit="s")
ts("RAG Chat & Semantic Search", [
    ("sum by (grounded) (rate(news_rag_queries_total[5m])) * 60", "RAG ({{grounded}}) / min"),
    ("rate(news_semantic_searches_total[5m]) * 60", "semantic searches / min"),
], 16, w=8)
advance(8)
pie("Sentiment Distribution", "news_articles_by_sentiment", "{{sentiment}}", 0)
bargauge("Articles by Category", "sort_desc(news_articles_total)", "{{category}}", 8)
ts("Summary Grounding Score (worker)", [
    ("histogram_quantile(0.5, sum by (le) (rate(news_worker_grounding_score_bucket[30m])))", "median"),
    ("news_summary_grounding_score_avg", "corpus average"),
], 16, w=8, unit="percentunit")
advance(8)

# ------------------------------------------------------------------------------- 5. Infra
row("Data & Infrastructure — PostgreSQL · Redis · Containers")
ts("PostgreSQL Connections", [('sum by (datname) (pg_stat_database_numbackends{datname!~"template.*"})', "{{datname}}")], 0, w=6)
ts("Database Size", [('pg_database_size_bytes{datname!~"template.*"}', "{{datname}}")], 6, w=6, unit="bytes")
ts("Redis Memory", [("redis_memory_used_bytes", "used")], 12, w=6, unit="bytes")
ts("Redis Ops & Cache Results", [
    ("rate(redis_commands_processed_total[2m])", "redis commands/s"),
    ("sum by (result) (rate(news_cache_operations_total[2m]))", "api cache {{result}}/s"),
], 18, w=6)
advance(8)
ts("Container CPU (cAdvisor profile)", [('sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{container_label_com_docker_compose_project!=""}[2m]))', "{{container_label_com_docker_compose_service}}")], 0, w=12, unit="percentunit",
   description="Requires: docker compose --profile cadvisor up -d")
ts("Container Memory (cAdvisor profile)", [('sum by (container_label_com_docker_compose_service) (container_memory_working_set_bytes{container_label_com_docker_compose_project!=""})', "{{container_label_com_docker_compose_service}}")], 12, w=12, unit="bytes",
   description="Requires: docker compose --profile cadvisor up -d")
advance(8)

# ------------------------------------------------------------------------------- 6. Alerts
row("Alerts")
panels.append({
    "type": "alertlist", "title": "Firing & Pending Alerts (Prometheus rules)", "id": nid(),
    "gridPos": {"h": 8, "w": 24, "x": 0, "y": _y[0]},
    "options": {"alertListOptions": {}, "showOptions": "current", "maxItems": 20, "sortOrder": 1,
                "stateFilter": {"firing": True, "pending": True, "noData": False, "normal": False, "error": True},
                "alertInstanceLabelFilter": "", "dashboardAlerts": False, "groupMode": "default",
                "viewMode": "list", "datasource": "Prometheus"},
})
advance(8)

dashboard = {
    "uid": "news-aggregator-overview",
    "title": "AI News Aggregator — Microservices Observability",
    "description": "RED metrics, event-driven pipeline, Groq LLM, RAG, sentiment, Fact-Grounding and infrastructure.",
    "tags": ["news-aggregator", "microservices", "fastapi", "ai"],
    "timezone": "browser",
    "schemaVersion": 39,
    "version": 1,
    "editable": True,
    "refresh": "10s",
    "time": {"from": "now-1h", "to": "now"},
    "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m", "5m"]},
    "templating": {"list": []},
    "annotations": {"list": []},
    "links": [
        {"title": "News Dashboard", "type": "link", "url": "http://localhost:5173", "targetBlank": True, "icon": "external link"},
        {"title": "API Docs", "type": "link", "url": "http://localhost:8000/docs", "targetBlank": True, "icon": "doc"},
        {"title": "Prometheus Alerts", "type": "link", "url": "http://localhost:9090/alerts", "targetBlank": True, "icon": "bolt"},
    ],
    "panels": panels,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(dashboard, indent=2))
print(f"Wrote {OUT} with {len(panels)} panels")
