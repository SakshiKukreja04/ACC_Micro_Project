import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.core.metrics import RAG_QUERIES, RAG_RETRIEVED_DOCS
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import ChatRequest, ChatResponse, SourceArticleRef
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/chat", tags=["RAG News Chatbot"])
logger = logging.getLogger("backend.api.chat")


def call_groq_completion(prompt: str, system_prompt: str, operation: str = "generic"):
    """Backward-compatible wrapper around the instrumented LLM client."""
    return llm.complete(prompt, system_prompt, operation=operation)


@router.post("/ask", response_model=ChatResponse)
def ask_news_question(
    req: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Retrieval-Augmented Generation (RAG) Question Answering over collected news.
    1. Semantically retrieves top context articles using FAISS (follow-up questions are
       expanded with the previous user turn so "what about India?" keeps its context).
    2. Grounds the Groq LLM response strictly in retrieved news facts.
    3. Returns citations with clickable source article references.
    """
    clean_q = req.question.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question must not be empty",
        )

    history = [h for h in (req.history or []) if h.content.strip()][-6:]
    previous_user = next((h.content for h in reversed(history) if h.role == "user"), "")
    retrieval_query = f"{previous_user} {clean_q}".strip() if previous_user and len(clean_q.split()) < 8 else clean_q

    store = get_vector_store()
    if store.index.ntotal == 0:
        store.sync_from_database(db)

    matches = store.search(retrieval_query, top_k=req.top_k, min_score=store.threshold("rag"))
    RAG_RETRIEVED_DOCS.observe(len(matches))
    if not matches:
        RAG_QUERIES.labels(grounded="false").inc()
        return ChatResponse(
            question=clean_q,
            answer="I could not find any news articles in our database related to your question. Please try asking about another topic covered in the news feed.",
            sources=[],
        )

    matched_ids = [m[0] for m in matches]
    score_map = dict(matches)

    articles = db.scalars(select(Article).where(Article.id.in_(matched_ids))).all()
    art_dict = {a.id: a for a in articles}

    context_lines = []
    sources: List[SourceArticleRef] = []
    for art_id in matched_ids:
        if art_id not in art_dict:
            continue
        art = art_dict[art_id]
        n = len(sources) + 1
        body = art.summary or art.description or art.content or ""
        context_lines.append(
            f"[{n}] \"{art.title}\" (Source: {art.source_name}, Category: {art.category})\n{body[:500]}"
        )
        sources.append(
            SourceArticleRef(
                id=art.id,
                title=art.title,
                canonical_url=art.canonical_url,
                source_name=art.source_name,
                similarity_score=round(score_map[art_id], 4),
            )
        )

    context_str = "\n\n".join(context_lines)
    conversation = "\n".join(f"{h.role.upper()}: {h.content[:400]}" for h in history)

    system_prompt = (
        "You are an AI News Analyst. Answer the user's question clearly, objectively, and factually, "
        "using ONLY the provided news articles. Cite the numbered sources like [1] or [2] when stating facts. "
        "If the articles do not contain enough information, say so honestly. Keep answers under 180 words."
    )
    user_prompt = (
        (f"Conversation so far:\n{conversation}\n\n" if conversation else "")
        + f"Retrieved News Articles:\n{context_str}\n\nUser Question:\n{clean_q}\n\n"
        "Provide a factual answer with citations:"
    )

    llm_answer = llm.complete(user_prompt, system_prompt, operation="rag_chat")

    if not llm_answer:
        top_art = art_dict.get(matched_ids[0])
        llm_answer = (
            f"Based on our latest indexed reports (e.g. \"{top_art.title}\" from {top_art.source_name}), "
            f"the primary coverage indicates: {top_art.summary or top_art.description or 'No further summary available'} [1]"
        )
        RAG_QUERIES.labels(grounded="fallback").inc()
    else:
        RAG_QUERIES.labels(grounded="true").inc()

    return ChatResponse(question=clean_q, answer=llm_answer, sources=sources)


@router.get("/explain/{article_id}")
def explain_article_context(
    article_id: str,
    db: Session = Depends(get_db),
):
    """
    Explain the background and significance of a specific news article in plain English.
    """
    article = db.scalar(select(Article).where(Article.id == article_id))
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article with ID '{article_id}' was not found",
        )

    system_prompt = (
        "You are an expert news educator. Explain this news story in simple terms for a student, using three "
        "short sections titled exactly 'What happened', 'Why it matters' and 'Background'. Plain text, no markdown."
    )
    user_prompt = (
        f"Article Title: {article.title}\nSource: {article.source_name}\n"
        f"Description: {article.description}\nContent: {(article.content or '')[:3000]}"
    )

    explanation = llm.complete(user_prompt, system_prompt, operation="explain")
    if not explanation:
        explanation = (
            f"What happened: {article.summary or article.description or article.title}\n\n"
            f"Why it matters: This {article.category.lower()} story from {article.source_name} is part of today's "
            f"coverage. Connect a Groq API key for a full plain-English explainer."
        )

    return {
        "article_id": article.id,
        "title": article.title,
        "source_name": article.source_name,
        "explanation": explanation,
    }
