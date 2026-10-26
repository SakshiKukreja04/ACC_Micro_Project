import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("backend.services.summarizer")

DEFAULT_MODEL = "qwen/qwen3.8-27b"
FALLBACK_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]


class SummaryResult(BaseModel):
    summary: str = Field(..., description="Concise 2-3 sentence factual summary")
    key_takeaways: List[str] = Field(..., description="Bullet points of key takeaways")


def generate_article_summary(
    title: str,
    source_name: str,
    category: str,
    description: Optional[str] = None,
    content: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Generate an AI summary and key takeaways for an article using Groq LLM.
    Returns dict with 'summary' and 'key_takeaways' or None on failure.
    """
    body = (content or description or "").strip()
    if len(body) > 4000:
        body = body[:4000] + "... [truncated]"

    prompt = f"""Title: {title}
Source: {source_name}
Category: {category}

Article Text:
{body}

Instructions:
1. Provide a concise, engaging, neutral 2-3 sentence summary strictly based on the article.
2. Provide 3 to 4 key takeaway bullet points.
3. Return ONLY a valid JSON object matching this structure:
{{
  "summary": "...",
  "key_takeaways": ["...", "...", "..."]
}}"""

    system_prompt = (
        "You are an expert news editor and analyst. "
        "Create clear, factual, reader-friendly summaries. "
        "Output strictly valid JSON with no markdown fences or preambles."
    )

    from app.core import llm

    data = llm.complete_json(prompt, system_prompt, operation="summarize", max_tokens=600)
    if data and data.get("summary") and data.get("key_takeaways"):
        takeaways = data["key_takeaways"]
        if isinstance(takeaways, str):
            takeaways = [takeaways]
        return {
            "summary": str(data["summary"]).strip(),
            "key_takeaways": [str(t).strip() for t in takeaways if t][:5],
        }
    return None
