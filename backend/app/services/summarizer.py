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
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY is not configured.")
        return None

    try:
        import groq

        client = groq.Groq(api_key=api_key, timeout=20.0)
    except Exception as e:
        logger.error(f"Failed to initialize Groq client: {e}")
        return None

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

    models_to_try = [DEFAULT_MODEL] + FALLBACK_MODELS
    for model_name in models_to_try:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=600,
            )
            raw_text = response.choices[0].message.content or ""
            # Parse JSON
            raw_clean = raw_text.strip()
            # Remove markdown fences if present
            if raw_clean.startswith("```"):
                raw_clean = re.sub(r"^```(?:json)?\s*", "", raw_clean)
                raw_clean = re.sub(r"\s*```$", "", raw_clean)

            match = re.search(r"\{.*\}", raw_clean, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if "summary" in data and "key_takeaways" in data:
                    return {
                        "summary": str(data["summary"]).strip(),
                        "key_takeaways": [str(t).strip() for t in data["key_takeaways"] if t],
                    }
        except Exception as e:
            logger.warning(f"Groq summarization failed with model '{model_name}': {e}")
            continue

    return None
