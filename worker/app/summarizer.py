import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError
from app.config import settings
from app.processor import BaseArticleProcessor
from app.queue import ArticleJob

logger = logging.getLogger("worker.summarizer")


class ArticleSummaryOutput(BaseModel):
    summary: str = Field(..., min_length=20, description="Concise 2-3 sentence factual summary")
    key_takeaways: List[str] = Field(..., min_length=2, max_length=6, description="3 to 5 key takeaway bullet points")
    suggested_category: Optional[str] = Field(None, description="Optional refined topic category")


class GroqSummarizerProcessor(BaseArticleProcessor):
    """
    AI Summarizer using Groq API.
    Generates concise summaries and key takeaways grounded strictly in source article text.
    """

    DEFAULT_MODEL = "qwen/qwen3.8-27b"
    FALLBACK_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    _dead_models: set = set()

    @staticmethod
    def _record(model: str, outcome: str) -> None:
        try:
            from app.metrics import LLM_CALLS

            LLM_CALLS.labels(model=model, outcome=outcome).inc()
        except Exception:
            pass

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 25.0,
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY") or ""
        configured = os.getenv("GROQ_MODELS") or os.getenv("GROQ_MODEL") or ""
        self.model = model or (configured.split(",")[0].strip() if configured else self.DEFAULT_MODEL)
        self.timeout = timeout
        self.client = None

        if self.api_key and "dummy" not in self.api_key.lower() and "placeholder" not in self.api_key.lower():
            try:
                import groq
                self.client = groq.Groq(api_key=self.api_key, timeout=self.timeout)
                logger.info(f"Groq API client initialized using model '{self.model}'.")
            except Exception as e:
                logger.warning(f"Could not initialize Groq client: {e}")
        else:
            logger.warning("GROQ_API_KEY is not configured or is a placeholder. AI summarization is unconfigured.")

    def _build_prompt(self, job: ArticleJob) -> str:
        body = (job.content or job.description or "").strip()
        # Cap input length to 4000 characters for safety
        if len(body) > 4000:
            body = body[:4000] + "... [truncated for length]"

        return f"""Title: {job.title}
Source: {job.source_name}
Category: {job.category}

Article Text:
{body}

Instructions:
1. Provide a concise, neutral 2-3 sentence summary strictly based on the article above.
2. Provide 3 to 5 key takeaway bullet points.
3. Suggest the best category from: World, Politics, Business, Technology, Science, Health, Sports, Entertainment, India, General.
4. Do NOT hallucinate or add facts not present in the article.
5. Return ONLY a valid JSON object matching this structure:
{{
  "summary": "...",
  "key_takeaways": ["...", "...", "..."],
  "suggested_category": "..."
}}"""

    def process(self, job: ArticleJob) -> Dict[str, Any]:
        if not self.client:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Cannot generate AI summaries."
            )

        prompt = self._build_prompt(job)
        system_instruction = (
            "You are a professional news editor and fact-checker. "
            "Your summaries must be concise, objective, and grounded entirely in the provided text. "
            "Output valid JSON only."
        )

        models_to_try = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
        models_to_try = [m for m in models_to_try if m not in self._dead_models] or models_to_try
        last_error = None

        for model_name in models_to_try:
            for use_json_mode in (True, False):
                try:
                    kwargs = dict(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=700,
                    )
                    if use_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = self.client.chat.completions.create(**kwargs)

                    raw_text = response.choices[0].message.content or "{}"
                    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    parsed = json.loads(match.group(0) if match else raw_text)

                    # Validate structured output using Pydantic
                    validated = ArticleSummaryOutput.model_validate(parsed)
                    self._record(model_name, "success")
                    return {
                        "summary": validated.summary,
                        "key_takeaways": validated.key_takeaways,
                        "suggested_category": validated.suggested_category,
                        "model": model_name,
                    }
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    self._record(model_name, "error")
                    if any(t in err_str for t in ("model_not_found", "does not exist", "decommissioned")):
                        logger.warning(f"Model {model_name} not available, attempting fallback...")
                        self._dead_models.add(model_name)
                        break  # next model
                    if "rate_limit" in err_str or "429" in err_str:
                        raise  # let the queue retry later instead of hammering every model
                    if use_json_mode and ("response_format" in err_str or "json" in err_str):
                        continue  # retry same model without JSON mode
                    logger.warning(f"Model {model_name} failed ({e}); trying next model.")
                    break

        # pyrefly: ignore[bad-raise]
        raise last_error
