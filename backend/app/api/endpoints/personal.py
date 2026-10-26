"""
Personal reader features — privacy-first, no login.

Readers are identified by an anonymous client id (X-Client-Id header) generated in the browser.
* Bookmarks / reading list
* Reading history
* "For You" recommendations: the reader's interest vector is the recency-weighted mean of the
  FAISS embeddings of what they read or saved; FAISS returns the nearest unread stories, each with
  a "because you read …" explanation.
* One-click "forget me" that deletes every trace of the reader.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.client import get_client_id
from app.core.metrics import READER_EVENTS
from app.db.session import get_db
from app.models.article import Article, Bookmark, ReadingEvent
from app.schemas.article import ArticleResponse

router = APIRouter(prefix="/me", tags=["Personalization"])
logger = logging.getLogger("backend.api.personal")

EVENT_WEIGHTS = {"view": 1.0, "listen": 1.5, "explain": 1.5, "perspective": 1.5, "bookmark": 2.0}


class ReadingEventIn(BaseModel):
    article_id: str = Field(..., min_length=1, max_length=36)
    event_type: str = Field("view", pattern="^(view|listen|explain|perspective|translate)$")


class Recommendation(ArticleResponse):
    match_score: float
    reason: Optional[str] = None


class ForYouResponse(BaseModel):
    personalized: bool
    profile: Dict
    items: List[Recommendation]


def _get_article_or_404(db: Session, article_id: str) -> Article:
    art = db.get(Article, article_id)
    if not art:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Article '{article_id}' not found")
    return art


# ----------------------------------------------------------------------------------- bookmarks
@router.get("/bookmarks", response_model=List[ArticleResponse])
def list_bookmarks(client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Article)
        .join(Bookmark, Bookmark.article_id == Article.id)
        .where(Bookmark.client_id == client_id)
        .order_by(desc(Bookmark.created_at))
    ).scalars().all()
    return [ArticleResponse.model_validate(a) for a in rows]


@router.get("/bookmarks/ids", response_model=List[str])
def list_bookmark_ids(client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    return list(db.scalars(select(Bookmark.article_id).where(Bookmark.client_id == client_id)).all())


@router.put("/bookmarks/{article_id}", status_code=status.HTTP_201_CREATED)
def add_bookmark(article_id: str, client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    _get_article_or_404(db, article_id)
    exists = db.scalar(
        select(Bookmark.id).where(Bookmark.client_id == client_id, Bookmark.article_id == article_id)
    )
    if not exists:
        try:
            db.add(Bookmark(client_id=client_id, article_id=article_id, created_at=datetime.now(timezone.utc)))
            db.commit()
            READER_EVENTS.labels(event_type="bookmark").inc()
        except IntegrityError:
            db.rollback()
    return {"article_id": article_id, "bookmarked": True}


@router.delete("/bookmarks/{article_id}")
def remove_bookmark(article_id: str, client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    db.execute(delete(Bookmark).where(Bookmark.client_id == client_id, Bookmark.article_id == article_id))
    db.commit()
    return {"article_id": article_id, "bookmarked": False}


# ----------------------------------------------------------------------------------- history
@router.post("/events", status_code=status.HTTP_201_CREATED)
def record_event(event: ReadingEventIn, client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    _get_article_or_404(db, event.article_id)
    db.add(
        ReadingEvent(
            client_id=client_id,
            article_id=event.article_id,
            event_type=event.event_type,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    READER_EVENTS.labels(event_type=event.event_type).inc()
    return {"recorded": True}


@router.get("/history", response_model=List[ArticleResponse])
def reading_history(
    limit: int = Query(20, ge=1, le=100),
    client_id: str = Depends(get_client_id),
    db: Session = Depends(get_db),
):
    last_read = (
        select(ReadingEvent.article_id, func.max(ReadingEvent.created_at).label("last_at"))
        .where(ReadingEvent.client_id == client_id)
        .group_by(ReadingEvent.article_id)
        .subquery()
    )
    rows = db.execute(
        select(Article).join(last_read, last_read.c.article_id == Article.id).order_by(desc(last_read.c.last_at)).limit(limit)
    ).scalars().all()
    return [ArticleResponse.model_validate(a) for a in rows]


@router.delete("")
def forget_me(client_id: str = Depends(get_client_id), db: Session = Depends(get_db)):
    """Privacy control: delete every bookmark and reading event for this reader."""
    b = db.execute(delete(Bookmark).where(Bookmark.client_id == client_id)).rowcount
    e = db.execute(delete(ReadingEvent).where(ReadingEvent.client_id == client_id)).rowcount
    db.commit()
    return {"deleted_bookmarks": b, "deleted_events": e}


# ----------------------------------------------------------------------------------- For You
def _interest_signals(db: Session, client_id: str) -> Dict[str, float]:
    """article_id -> weight, combining event type weight with a recency decay."""
    now = datetime.now(timezone.utc)
    signals: Dict[str, float] = {}
    events = db.execute(
        select(ReadingEvent.article_id, ReadingEvent.event_type, ReadingEvent.created_at)
        .where(ReadingEvent.client_id == client_id)
        .order_by(desc(ReadingEvent.created_at))
        .limit(60)
    ).all()
    for art_id, etype, created in events:
        created = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - created).total_seconds() / 86400)
        signals[art_id] = signals.get(art_id, 0.0) + EVENT_WEIGHTS.get(etype, 1.0) / (1.0 + age_days)
    for art_id in db.scalars(select(Bookmark.article_id).where(Bookmark.client_id == client_id)).all():
        signals[art_id] = signals.get(art_id, 0.0) + EVENT_WEIGHTS["bookmark"]
    return signals


@router.get("/for-you", response_model=ForYouResponse)
def for_you(
    limit: int = Query(12, ge=1, le=40),
    client_id: str = Depends(get_client_id),
    db: Session = Depends(get_db),
):
    from app.api.endpoints.trending import compute_trending
    from app.services.vector_store import get_vector_store

    signals = _interest_signals(db, client_id)
    read_articles = (
        {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(list(signals)))).all()} if signals else {}
    )
    cat_counter = Counter()
    src_counter = Counter()
    for art_id, w in signals.items():
        art = read_articles.get(art_id)
        if art:
            cat_counter[art.category] += w
            src_counter[art.source_name] += w
    total_w = sum(cat_counter.values()) or 1.0
    profile = {
        "signals": len(signals),
        "top_categories": [
            {"category": c, "share": round(w / total_w, 3)} for c, w in cat_counter.most_common(4)
        ],
        "top_sources": [s for s, _ in src_counter.most_common(3)],
    }

    store = get_vector_store()
    if store.index.ntotal == 0:
        store.sync_from_database(db)

    ids = list(signals.keys())
    profile_vec = store.profile_vector(ids, [signals[i] for i in ids]) if ids else None

    if profile_vec is None:
        # Cold start: fall back to trending stories
        trending = compute_trending(db, limit)
        return ForYouResponse(
            personalized=False,
            profile=profile,
            items=[
                Recommendation(**{**t.model_dump(exclude={"trending_score"}), "match_score": 0.0,
                                  "reason": "Trending now — read a few stories to personalise this feed"})
                for t in trending
            ],
        )

    matches = store.search_vector(profile_vec, top_k=limit, min_score=store.threshold("for_you"), exclude=set(ids))
    if not matches:
        return ForYouResponse(personalized=True, profile=profile, items=[])

    match_ids = [m[0] for m in matches]
    found = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(match_ids))).all()}

    # "Because you read …": the read article whose vector is closest to each recommendation
    read_vecs: Dict[str, np.ndarray] = {}
    for rid in ids:
        idx = store.id_to_idx.get(rid)
        if idx is not None:
            v = np.zeros(store.dim, dtype=np.float32)
            store.index.reconstruct(idx, v)
            read_vecs[rid] = v

    items: List[Recommendation] = []
    for art_id, score in matches:
        art = found.get(art_id)
        if not art:
            continue
        reason = None
        idx = store.id_to_idx.get(art_id)
        if idx is not None and read_vecs:
            v = np.zeros(store.dim, dtype=np.float32)
            store.index.reconstruct(idx, v)
            best_id = max(read_vecs, key=lambda rid: float(np.dot(read_vecs[rid], v)))
            best_art = read_articles.get(best_id)
            if best_art:
                title = best_art.title if len(best_art.title) <= 70 else best_art.title[:67] + "…"
                reason = f"Because you read “{title}”"
        data = ArticleResponse.model_validate(art).model_dump()
        items.append(Recommendation(**data, match_score=round(score, 4), reason=reason))

    return ForYouResponse(personalized=True, profile=profile, items=items)
