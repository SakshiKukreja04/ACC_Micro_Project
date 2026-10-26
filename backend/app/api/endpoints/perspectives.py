"""
USP endpoints built on top of the FAISS story graph.

* Perspective Lens   GET /api/news/{id}/perspectives
    How do different publishers cover the *same* story? Shared facts, each outlet's distinct angle,
    per-source sentiment, a Coverage Agreement Index and a neutral synthesis.
* Story Timeline     GET /api/news/{id}/timeline
    Chronological evolution of a story across sources.
* Translation        GET /api/news/{id}/translate?lang=hi
    Multilingual summaries (Indian + global languages) via Groq, cached in Redis for 24h.
"""
from __future__ import annotations

import hashlib
import itertools
import logging
import re
from datetime import timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.core.redis_cache import cache_get, cache_set
from app.db.session import get_db
from app.models.article import Article
from app.services.enrichment import analyze_sentiment, extract_keywords

router = APIRouter(prefix="/news", tags=["Perspective Lens & Story Intelligence"])
logger = logging.getLogger("backend.api.perspectives")

LANGUAGES = {
    "hi": "Hindi", "mr": "Marathi", "ta": "Tamil", "te": "Telugu", "bn": "Bengali", "gu": "Gujarati",
    "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi", "ur": "Urdu",
    "es": "Spanish", "fr": "French", "de": "German", "ar": "Arabic", "ja": "Japanese", "zh": "Chinese (Simplified)",
}


def _get_article(db: Session, article_id: str) -> Article:
    art = db.get(Article, article_id)
    if not art:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Article '{article_id}' not found")
    return art


def _story_set(db: Session, base: Article, min_score: Optional[float], kind: str, top_k: int) -> List[tuple[Article, float]]:
    """Base article + same-cluster articles + FAISS neighbours above the (calibrated) threshold."""
    from app.services.vector_store import get_vector_store

    store = get_vector_store()
    if base.id not in store.id_to_idx:
        store.add_articles([base.to_dict()])
    threshold = min_score if min_score is not None else store.threshold(kind)

    # Real similarity for every neighbour; include those above threshold plus DSU cluster members
    neighbour_scores = dict(store.find_related(base.id, top_k=max(top_k, 30), min_score=0.0))
    cluster_ids = (
        set(db.scalars(select(Article.id).where(Article.cluster_id == base.cluster_id)).all())
        if base.cluster_id else set()
    )
    scores: Dict[str, float] = {base.id: 1.0}
    for aid, score in neighbour_scores.items():
        if score >= threshold or aid in cluster_ids:
            scores[aid] = score
    for aid in cluster_ids - set(scores):
        scores[aid] = threshold
    if len(scores) > top_k + 1:
        scores = dict(sorted(scores.items(), key=lambda kv: -kv[1])[: top_k + 1])

    arts = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(list(scores)))).all()}
    return [(arts[i], s) for i, s in sorted(scores.items(), key=lambda kv: -kv[1]) if i in arts]


def _first_sentence(text: Optional[str], limit: int = 220) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"


def _sentiment(art: Article) -> tuple[str, float]:
    if art.sentiment and art.sentiment_score is not None:
        return art.sentiment, float(art.sentiment_score)
    return analyze_sentiment(art.content or art.description or "", title=art.title)


@router.get("/{article_id}/perspectives")
def perspective_lens(
    article_id: str,
    max_sources: int = Query(5, ge=2, le=8),
    min_score: Optional[float] = Query(None, ge=0.1, le=0.99, description="Default: calibrated to the embedding model"),
    db: Session = Depends(get_db),
):
    base = _get_article(db, article_id)
    story = _story_set(db, base, min_score=min_score, kind="lens", top_k=15)

    # One article per publisher (the most similar), base article first
    per_source: Dict[str, tuple[Article, float]] = {}
    for art, score in story:
        if art.source_name not in per_source:
            per_source[art.source_name] = (art, score)
    coverage = list(per_source.values())[:max_sources]

    cache_key = "perspective:" + hashlib.sha1("|".join(sorted(a.id for a, _ in coverage)).encode()).hexdigest()
    cached = cache_get(cache_key)
    if cached:
        return cached

    outlets = []
    keyword_sets: Dict[str, set] = {}
    for art, score in coverage:
        label, sscore = _sentiment(art)
        kws = art.keywords if isinstance(art.keywords, list) and art.keywords else extract_keywords(
            f"{art.title}. {art.description or ''} {art.content or ''}", top_n=8
        )
        keyword_sets[art.source_name] = set(kws)
        outlets.append({
            "article_id": art.id, "source_name": art.source_name, "title": art.title,
            "canonical_url": art.canonical_url,
            "published_at": art.published_at.isoformat() if art.published_at else None,
            "similarity": round(score, 3), "sentiment": label, "sentiment_score": round(sscore, 3),
            "keywords": kws[:8], "lead": _first_sentence(art.summary or art.description),
        })

    if len(outlets) < 2:
        result = {
            "available": False,
            "message": "Only one publisher has covered this story so far. The Perspective Lens activates "
                       "automatically once another outlet reports on it.",
            "base_article_id": base.id, "outlets": outlets,
        }
        return result

    # Shared vs. distinctive vocabulary
    all_kw = list(keyword_sets.values())
    shared = sorted({k for k in set().union(*all_kw) if sum(k in s for s in all_kw) >= 2})
    for o in outlets:
        others = set().union(*(s for src, s in keyword_sets.items() if src != o["source_name"]))
        o["distinct_focus"] = [k for k in o["keywords"] if k not in others][:4]

    pairs = list(itertools.combinations(all_kw, 2))
    jaccard = [len(a & b) / len(a | b) for a, b in pairs if a | b]
    agreement = round(sum(jaccard) / len(jaccard), 3) if jaccard else 0.0
    scores = [o["sentiment_score"] for o in outlets]
    tone_spread = round(max(scores) - min(scores), 3)

    analysis = None
    if llm.is_configured():
        listing = "\n\n".join(
            f"[{i + 1}] {o['source_name']} — \"{o['title']}\"\n{(c[0].summary or c[0].description or c[0].content or '')[:700]}"
            for i, (o, c) in enumerate(zip(outlets, coverage))
        )
        analysis = llm.complete_json(
            prompt=(
                f"These reports from different publishers cover the same news story:\n\n{listing}\n\n"
                "Compare the coverage. Return JSON with keys:\n"
                '  "consensus": list of 2-4 facts that several sources agree on,\n'
                '  "differences": list of objects {"source": name, "angle": one sentence on what this outlet '
                "emphasises or omits relative to the others},\n"
                '  "framing_note": one sentence about overall differences in tone or framing,\n'
                '  "neutral_synthesis": a balanced 2-3 sentence account using only facts above.\n'
                "Use only the information given. Do not invent facts."
            ),
            system_prompt="You are a media analyst who compares news coverage objectively and without political bias.",
            operation="perspective_lens",
            max_tokens=800,
        )

    if not analysis:
        most_neutral = min(outlets, key=lambda o: abs(o["sentiment_score"]))
        analysis = {
            "consensus": [f"Every account mentions {', '.join(shared[:6])}."] if shared else [],
            "differences": [],  # distinctive keywords are shown per outlet instead
            "framing_note": (
                f"Tone differs noticeably: {max(outlets, key=lambda o: o['sentiment_score'])['source_name']} is the most "
                f"upbeat and {min(outlets, key=lambda o: o['sentiment_score'])['source_name']} the most critical."
                if tone_spread >= 0.5 else "The outlets use a broadly similar tone."
            ),
            "neutral_synthesis": f"{most_neutral['lead']} (lead from {most_neutral['source_name']}, the most neutral-toned report)",
            "generated_by": "deterministic-fallback",
        }
    else:
        analysis["generated_by"] = "groq-llm"

    result = {
        "available": True,
        "base_article_id": base.id,
        "outlets": outlets,
        "shared_keywords": shared[:12],
        "coverage_agreement_index": agreement,
        "tone_spread": tone_spread,
        "analysis": analysis,
    }
    cache_set(cache_key, result, expire_seconds=3600)
    return result


@router.get("/{article_id}/timeline")
def story_timeline(
    article_id: str,
    min_score: Optional[float] = Query(None, ge=0.1, le=0.99, description="Default: calibrated to the embedding model"),
    db: Session = Depends(get_db),
):
    base = _get_article(db, article_id)
    story = _story_set(db, base, min_score=min_score, kind="timeline", top_k=20)

    events = []
    for art, score in story:
        ts = art.published_at or art.collected_at
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        label, sscore = _sentiment(art)
        events.append({
            "article_id": art.id, "title": art.title, "source_name": art.source_name,
            "published_at": ts.isoformat() if ts else None, "_ts": ts,
            "similarity": round(score, 3), "is_current": art.id == base.id,
            "sentiment": label, "lead": _first_sentence(art.summary or art.description, 180),
        })
    events.sort(key=lambda e: e["_ts"] or base.collected_at)
    span_hours = None
    dated = [e["_ts"] for e in events if e["_ts"]]
    if len(dated) >= 2:
        span_hours = round((max(dated) - min(dated)).total_seconds() / 3600, 1)
    for e in events:
        e.pop("_ts")
    return {
        "base_article_id": base.id,
        "events": events,
        "sources": sorted({e["source_name"] for e in events}),
        "first_reported_by": events[0]["source_name"] if events else None,
        "span_hours": span_hours,
    }


@router.get("/{article_id}/translate")
def translate_article(
    article_id: str,
    lang: str = Query(..., description="Target language code, e.g. hi, mr, ta, es, fr"),
    db: Session = Depends(get_db),
):
    lang = lang.lower().strip()
    if lang not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language '{lang}'. Supported: {sorted(LANGUAGES)}")
    art = _get_article(db, article_id)

    cache_key = f"translate:{article_id}:{lang}:{hashlib.sha1((art.summary or art.description or '').encode()).hexdigest()[:10]}"
    cached = cache_get(cache_key)
    if cached:
        return {**cached, "cached": True}

    if not llm.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Translation needs the Groq LLM. Set GROQ_API_KEY in .env and restart the backend.",
        )

    body = art.summary or art.description or art.content or ""
    takeaways = art.key_takeaways if isinstance(art.key_takeaways, list) else []
    data = llm.complete_json(
        prompt=(
            f"Translate this news brief into {LANGUAGES[lang]}. Keep names, numbers and facts exact.\n\n"
            f"Title: {art.title}\nSummary: {body[:1500]}\nKey takeaways: {takeaways}\n\n"
            'Return JSON: {"title": "...", "summary": "...", "key_takeaways": ["..."]}'
        ),
        system_prompt="You are a professional news translator. Output valid JSON only.",
        operation="translate",
        max_tokens=900,
    )
    if not data or not data.get("summary"):
        raise HTTPException(status_code=502, detail="The translation service did not return a usable result. Try again.")

    result = {
        "article_id": art.id, "language": lang, "language_name": LANGUAGES[lang],
        "title": data.get("title") or art.title, "summary": data.get("summary"),
        "key_takeaways": [str(t) for t in (data.get("key_takeaways") or [])][:6],
    }
    cache_set(cache_key, result, expire_seconds=86400)
    return {**result, "cached": False}


@router.get("/meta/languages", tags=["Perspective Lens & Story Intelligence"])
def supported_languages():
    return [{"code": k, "name": v} for k, v in LANGUAGES.items()]
