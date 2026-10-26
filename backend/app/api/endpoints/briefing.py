"""
AI Daily Briefing — a 60-second, newsroom-style digest of the most important stories right now.
Built from the trending ranking, synthesised by Groq with numbered citations, cached for 30 minutes.
Falls back to an extractive briefing when no LLM key is configured.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.endpoints.trending import compute_trending
from app.core import llm
from app.core.redis_cache import cache_get, cache_set
from app.db.session import get_db

router = APIRouter(prefix="/briefing", tags=["AI Daily Briefing"])


def _first_sentence(text: Optional[str]) -> str:
    text = (text or "").strip()
    return re.split(r"(?<=[.!?])\s+", text)[0] if text else ""


@router.get("")
def daily_briefing(
    category: Optional[str] = Query(None, description="Optional category focus"),
    refresh: bool = Query(False, description="Bypass the 30-minute cache"),
    db: Session = Depends(get_db),
):
    cache_key = f"briefing:{(category or 'all').lower()}"
    if not refresh:
        cached = cache_get(cache_key)
        if cached:
            return {**cached, "cached": True}

    stories = compute_trending(db, limit=8, category=category)
    if not stories:
        return {"available": False, "headline": "No stories collected yet", "overview": "", "highlights": [], "stories": []}

    refs = [
        {"ref": i + 1, "id": s.id, "title": s.title, "source_name": s.source_name, "category": s.category,
         "canonical_url": s.canonical_url}
        for i, s in enumerate(stories)
    ]

    briefing = None
    if llm.is_configured():
        listing = "\n".join(
            f"[{i + 1}] ({s.category}, {s.source_name}) {s.title} — {(s.summary or s.description or '')[:350]}"
            for i, s in enumerate(stories)
        )
        briefing = llm.complete_json(
            prompt=(
                f"Today's top stories:\n{listing}\n\n"
                "Write a crisp morning news briefing. Return JSON with keys:\n"
                '  "headline": a single compelling line capturing the day,\n'
                '  "overview": 3 sentences connecting the biggest themes, citing stories like [1] or [3],\n'
                '  "highlights": list of 4-6 objects {"text": one-sentence takeaway, "ref": story number}.\n'
                "Only use the facts provided."
            ),
            system_prompt="You are the editor of a respected daily news briefing. Be neutral, factual and concise.",
            operation="daily_briefing",
            max_tokens=700,
        )

    if briefing and briefing.get("overview"):
        generated_by = "groq-llm"
        highlights = []
        for h in briefing.get("highlights") or []:
            if isinstance(h, dict) and h.get("text"):
                try:
                    ref = int(h.get("ref")) if h.get("ref") is not None else None
                except (TypeError, ValueError):
                    ref = None
                highlights.append({"text": str(h["text"]), "ref": ref if ref and 1 <= ref <= len(refs) else None})
    else:
        generated_by = "extractive-fallback"
        lead = stories[0]
        briefing = {
            "headline": lead.title,
            "overview": " ".join(
                f"{_first_sentence(s.summary or s.description)} [{i + 1}]" for i, s in enumerate(stories[:3])
                if _first_sentence(s.summary or s.description)
            ),
        }
        highlights = [{"text": s.title, "ref": i + 1} for i, s in enumerate(stories[:6])]

    result = {
        "available": True,
        "headline": briefing.get("headline") or stories[0].title,
        "overview": briefing.get("overview", ""),
        "highlights": highlights,
        "stories": refs,
        "category": category,
        "generated_by": generated_by,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set(cache_key, result, expire_seconds=1800)
    return {**result, "cached": False}
