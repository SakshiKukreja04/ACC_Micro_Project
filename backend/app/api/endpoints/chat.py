import json
import logging
import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.article import Article
from app.schemas.article import (
    ArticleResponse,
    ChatRequest,
    ChatResponse,
    SourceArticleRef,
)
from app.services.vector_store import get_vector_store

router = APIRouter(prefix="/chat", tags=["RAG News Chatbot"])
logger = logging.getLogger("backend.api.chat")

GROQ_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


def call_groq_completion(prompt: str, system_prompt: str) -> Optional[str]:
    """Call Groq LLM API with model fallback sequence."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        from groq import Groq

        client = Groq(api_key=api_key)
        for model in GROQ_MODELS:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_completion_tokens=600,
                )
                answer = response.choices[0].message.content
                if answer and answer.strip():
                    return answer.strip()
            except Exception as model_err:
                logger.warning(f"Model '{model}' failed: {model_err}. Trying next fallback.")
                continue
    except Exception as e:
        logger.error(f"Groq API client error: {e}")

    return None


@router.post("/ask", response_model=ChatResponse)
def ask_news_question(
    req: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Retrieval-Augmented Generation (RAG) Question Answering over collected news.
    1. Semantically retrieves top context articles using FAISS.
    2. Grounds the Groq LLM response strictly in retrieved news facts.
    3. Returns citations with clickable source article references.
    """
    clean_q = req.question.strip()
    if not clean_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question must not be empty",
        )

    store = get_vector_store()
    if store.index.ntotal == 0:
        store.sync_from_database(db)

    # Retrieve top_k semantically matched articles
    matches = store.search(clean_q, top_k=req.top_k, min_score=0.25)
    if not matches:
        return ChatResponse(
            question=clean_q,
            answer="I could not find any news articles in our database related to your question. Please try asking about another topic covered in the news feed.",
            sources=[],
        )

    matched_ids = [m[0] for m in matches]
    score_map = dict(matches)

    articles = db.scalars(select(Article).where(Article.id.in_(matched_ids))).all()
    art_dict = {a.id: a for a in articles}

    # Build context and source references
    context_lines = []
    sources: List[SourceArticleRef] = []

    for i, art_id in enumerate(matched_ids, 1):
        if art_id not in art_dict:
            continue
        art = art_dict[art_id]
        body = art.summary or art.description or art.content or ""
        context_lines.append(
            f"[{i}] \"{art.title}\" (Source: {art.source_name}, Category: {art.category})\n{body[:400]}"
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

    system_prompt = (
        "You are an AI News Analyst on the Cloud Computing News Platform. "
        "Your task is to answer the user's question clearly, objectively, and factually, "
        "using ONLY the provided news articles. "
        "Cite the numbered sources like [1] or [2] when stating facts from them. "
        "If the provided articles do not contain enough information to answer the question, state so honestly."
    )

    user_prompt = f"Retrieved News Articles:\n{context_str}\n\nUser Question:\n{clean_q}\n\nProvide a comprehensive, factual answer with citations:"

    llm_answer = call_groq_completion(user_prompt, system_prompt)

    if not llm_answer:
        # Fallback synthesis if API is unavailable
        top_art = art_dict.get(matched_ids[0])
        llm_answer = (
            f"Based on our latest indexed reports (e.g. \"{top_art.title}\" from {top_art.source_name}), "
            f"the primary coverage indicates: {top_art.summary or top_art.description or 'No further summary available'}. "
            f"[Referenced from source [1]]."
        )

    return ChatResponse(
        question=clean_q,
        answer=llm_answer,
        sources=sources,
    )


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
        "You are an expert news educator. Explain this news story in simple terms for a student: "
        "1. What happened? 2. Why does it matter? 3. Key background context."
    )
    user_prompt = f"Article Title: {article.title}\nSource: {article.source_name}\nDescription: {article.description}\nContent: {article.content}"

    explanation = call_groq_completion(user_prompt, system_prompt)
    if not explanation:
        explanation = f"This report from {article.source_name} discusses '{article.title}'. Main overview: {article.summary or article.description or 'No further details available.'}"

    return {
        "article_id": article.id,
        "title": article.title,
        "source_name": article.source_name,
        "explanation": explanation,
    }
