"""
Instrumented Groq LLM client shared by every AI feature in the backend.

* Model fallback chain (configurable with GROQ_MODELS, comma separated)
* Models that report "not found / decommissioned" are skipped for the rest of the process lifetime
* Reasoning traces (<think>…</think>) are stripped from answers
* Every call is measured: news_llm_requests_total / news_llm_request_duration_seconds
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.metrics import LLM_DURATION, LLM_REQUESTS, stats

logger = logging.getLogger("backend.core.llm")

DEFAULT_MODELS = [
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

_dead_models: set[str] = set()
_lock = threading.Lock()
_client = None
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def model_chain() -> List[str]:
    configured = os.getenv("GROQ_MODELS") or os.getenv("GROQ_MODEL")
    models = [m.strip() for m in configured.split(",")] if configured else DEFAULT_MODELS
    return [m for m in models if m and m not in _dead_models] or models


def is_configured() -> bool:
    key = os.getenv("GROQ_API_KEY", "")
    return bool(key) and not any(bad in key.lower() for bad in ("your_", "placeholder", "dummy"))


def _get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                from groq import Groq

                _client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=float(os.getenv("GROQ_TIMEOUT", "25")))
    return _client


def complete(
    prompt: str,
    system_prompt: str,
    operation: str,
    max_tokens: int = 600,
    temperature: float = 0.2,
    json_mode: bool = False,
) -> Optional[str]:
    """Run a chat completion with model fallback. Returns None if the LLM is unavailable."""
    if not is_configured():
        LLM_REQUESTS.labels(operation=operation, outcome="unconfigured").inc()
        return None

    try:
        client = _get_client()
    except Exception as e:  # pragma: no cover
        logger.error(f"Groq client init failed: {e}")
        LLM_REQUESTS.labels(operation=operation, outcome="error").inc()
        return None

    for model in model_chain():
        start = time.perf_counter()
        try:
            kwargs: Dict[str, Any] = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            response = client.chat.completions.create(**kwargs)
            text = _THINK_RE.sub("", response.choices[0].message.content or "").strip()
            duration = time.perf_counter() - start
            if text:
                LLM_REQUESTS.labels(operation=operation, outcome="success").inc()
                LLM_DURATION.labels(operation=operation).observe(duration)
                stats.record_llm(duration, operation, "success")
                return text
        except Exception as e:
            duration = time.perf_counter() - start
            msg = str(e).lower()
            if any(s in msg for s in ("model_not_found", "does not exist", "decommissioned", "not supported")):
                logger.warning(f"Groq model '{model}' unavailable; removing from fallback chain.")
                _dead_models.add(model)
            else:
                logger.warning(f"Groq call failed for operation={operation} model={model}: {e}")
            LLM_REQUESTS.labels(operation=operation, outcome="error").inc()
            stats.record_llm(duration, operation, "error")
            continue
    return None


def complete_json(prompt: str, system_prompt: str, operation: str, max_tokens: int = 700) -> Optional[Dict]:
    """Like complete() but parses a JSON object out of the answer."""
    raw = complete(prompt, system_prompt, operation, max_tokens=max_tokens, json_mode=True)
    if raw is None:
        # Some models reject response_format; retry once without it
        raw = complete(prompt, system_prompt, operation, max_tokens=max_tokens, json_mode=False)
    if not raw:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
