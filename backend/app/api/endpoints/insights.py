"""
News Insights: analytics across the whole corpus.

* /api/insights/overview  -> category mix, sentiment by source & category, hourly ingestion volume, totals
* /api/insights/topics    -> trending-topic detection: keywords whose frequency spiked in the current
                             window compared with the previous window of the same length
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redis_cache import cache_get, cache_set
from app.db.session import get_db
from app.models.article import Article
from app.services.enrichment import extract_keywords

router = APIRouter(prefix="/insights", tags=["Insights & Analytics"])


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@router.get("/overview")
def insights_overview(hours: int = Query(48, ge=6, le=720), db: Session = Depends(get_db)):
    cache_key = f"insights:overview:{hours}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(
            Article.category, Article.source_name, Article.sentiment, Article.sentiment_score,
            Article.collected_at, Article.published_at, Article.summary.isnot(None),
            Article.grounding_score, Article.reading_time_minutes, Article.cluster_id,
        )
    ).all()

    categories: Counter = Counter()
    by_source: Dict[str, Dict] = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0, "scores": []})
    by_category: Dict[str, Dict] = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0, "scores": []})
    volume: Counter = Counter()
    summarized = 0
    grounding, reading = [], []
    clusters = set()
    start = now - timedelta(hours=hours)

    for cat, src, sent, score, collected, published, has_summary, ground, rt, cluster in rows:
        categories[cat] += 1
        if sent:
            by_source[src][sent] += 1
            by_category[cat][sent] += 1
        if score is not None:
            by_source[src]["scores"].append(score)
            by_category[cat]["scores"].append(score)
        ts = _aware(published) or _aware(collected)
        if ts and ts >= start:
            volume[ts.replace(minute=0, second=0, microsecond=0)] += 1
        summarized += 1 if has_summary else 0
        if ground is not None:
            grounding.append(ground)
        if rt:
            reading.append(rt)
        if cluster:
            clusters.add(cluster)

    def _pack(name_key: str, data: Dict[str, Dict]) -> List[Dict]:
        out = []
        for name, d in data.items():
            total = d["positive"] + d["neutral"] + d["negative"]
            out.append({
                name_key: name, "positive": d["positive"], "neutral": d["neutral"], "negative": d["negative"],
                "total": total, "avg_score": round(sum(d["scores"]) / len(d["scores"]), 3) if d["scores"] else 0.0,
            })
        return sorted(out, key=lambda x: x["total"], reverse=True)

    hours_series = []
    cursor = start.replace(minute=0, second=0, microsecond=0)
    while cursor <= now:
        hours_series.append({"hour": cursor.isoformat(), "count": volume.get(cursor, 0)})
        cursor += timedelta(hours=1)

    result = {
        "totals": {
            "articles": len(rows),
            "summarized": summarized,
            "sources": len({r[1] for r in rows}),
            "story_clusters": len(clusters),
            "avg_grounding_score": round(sum(grounding) / len(grounding), 3) if grounding else None,
            "avg_reading_minutes": round(sum(reading) / len(reading), 1) if reading else None,
        },
        "category_distribution": [{"category": c, "count": n} for c, n in categories.most_common()],
        "sentiment_by_source": _pack("source", by_source),
        "sentiment_by_category": _pack("category", by_category),
        "volume_by_hour": hours_series,
        "window_hours": hours,
    }
    cache_set(cache_key, result, expire_seconds=60)
    return result


@router.get("/topics")
def trending_topics(
    hours: int = Query(24, ge=1, le=168, description="Length of the current window"),
    limit: int = Query(15, ge=1, le=40),
    db: Session = Depends(get_db),
):
    """
    Trending-topic detection. For every keyword we compare document frequency in the current
    window with the previous window of equal length:
        spike = log(1 + current) * (current + 1) / (previous + 1)
    Brand-new topics and sudden surges float to the top; evergreen words do not.
    """
    cache_key = f"insights:topics:{hours}:{limit}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    now = datetime.now(timezone.utc)
    cur_start, prev_start = now - timedelta(hours=hours), now - timedelta(hours=2 * hours)
    rows = db.execute(
        select(Article.id, Article.title, Article.description, Article.keywords, Article.published_at,
               Article.collected_at, Article.source_name, Article.category)
        .where(func.coalesce(Article.published_at, Article.collected_at) >= prev_start)
    ).all()

    current: Counter = Counter()
    previous: Counter = Counter()
    examples: Dict[str, List[Dict]] = defaultdict(list)
    sources: Dict[str, set] = defaultdict(set)
    categories: Dict[str, Counter] = defaultdict(Counter)

    for art_id, title, desc, keywords, published, collected, source, category in rows:
        ts = _aware(published) or _aware(collected)
        kws = keywords if isinstance(keywords, list) and keywords else extract_keywords(f"{title}. {desc or ''}")
        for kw in set(kws[:8]):
            if ts and ts >= cur_start:
                current[kw] += 1
                sources[kw].add(source)
                categories[kw][category] += 1
                if len(examples[kw]) < 3:
                    examples[kw].append({"id": art_id, "title": title, "source_name": source})
            else:
                previous[kw] += 1

    topics = []
    for kw, cnt in current.items():
        if cnt < 2 and len(current) > 20:
            continue
        prev = previous.get(kw, 0)
        spike = math.log1p(cnt) * (cnt + 1) / (prev + 1)
        topics.append({
            "topic": kw,
            "mentions": cnt,
            "previous_mentions": prev,
            "growth": None if prev == 0 else round((cnt - prev) / prev, 2),
            "is_new": prev == 0,
            "spike_score": round(spike, 3),
            "source_count": len(sources[kw]),
            "category": categories[kw].most_common(1)[0][0] if categories[kw] else None,
            "examples": examples[kw],
        })
    topics.sort(key=lambda t: (t["spike_score"], t["source_count"]), reverse=True)
    result = {"window_hours": hours, "generated_at": now.isoformat(), "topics": topics[:limit]}
    cache_set(cache_key, result, expire_seconds=120)
    return result
