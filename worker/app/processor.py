import abc
import logging
import re
from collections import Counter
from typing import Any, Dict, List

from app.enrichment import STOPWORDS
from app.queue import ArticleJob

logger = logging.getLogger("worker.processor")

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")


class BaseArticleProcessor(abc.ABC):
    """Abstract interface for article background processors."""

    @abc.abstractmethod
    def process(self, job: ArticleJob) -> Dict[str, Any]:
        """Process an article job and return dictionary with result fields."""
        pass


class DeterministicTestProcessor(BaseArticleProcessor):
    """
    Extractive summarizer used when the Groq API is unavailable (no key, outage, quota).

    Scores every sentence by the frequency of its content words (a lightweight TextRank-style
    heuristic), keeps the best 2 sentences in their original order as the summary and turns the
    next best sentences into key takeaways. Fully offline and deterministic.
    """

    @staticmethod
    def _sentences(text: str) -> List[str]:
        return [s.strip() for s in _SENT_RE.split(text) if len(s.strip().split()) >= 5]

    @staticmethod
    def _dedupe(sentences: List[str]) -> List[str]:
        """Drop sentences that largely repeat an earlier one (RSS descriptions often restate the lead)."""
        kept, kept_sets = [], []
        for s in sentences:
            words = {w.lower() for w in _WORD_RE.findall(s) if w.lower() not in STOPWORDS}
            if not words:
                continue
            if any(len(words & k) / max(1, min(len(words), len(k))) >= 0.6 for k in kept_sets):
                continue
            kept.append(s)
            kept_sets.append(words)
        return kept

    def process(self, job: ArticleJob) -> Dict[str, Any]:
        content = (job.content or "").strip()
        description = (job.description or "").strip()
        text = content if description and description[:60] in content else " ".join(t for t in [description, content] if t)
        sentences = self._dedupe(self._sentences(text) + self._sentences(description))

        if not sentences:
            fallback = (job.description or job.content or "").strip()
            summary = fallback[:280] + ("..." if len(fallback) > 280 else "") if fallback else (
                f"Reporting from {job.source_name} covering {job.title}."
            )
            return {
                "summary": summary,
                "key_takeaways": [f"Reported by {job.source_name}", f"Topic: {job.category}",
                                  "Full story available at publisher link"],
                "cluster_id": None,
            }

        freq = Counter(
            w.lower() for w in _WORD_RE.findall(f"{job.title} {text}") if w.lower() not in STOPWORDS and len(w) > 2
        )
        title_words = {w.lower() for w in _WORD_RE.findall(job.title)}

        def score(idx_sentence):
            idx, sentence = idx_sentence
            words = [w.lower() for w in _WORD_RE.findall(sentence) if w.lower() not in STOPWORDS]
            if not words:
                return 0.0
            base = sum(freq[w] for w in words) / len(words)
            overlap = len(title_words & set(words)) * 0.5
            position = 1.0 / (1 + idx * 0.3)  # lead sentences matter in news writing
            return base + overlap + position

        ranked = sorted(enumerate(sentences), key=score, reverse=True)
        top = sorted(ranked[:2], key=lambda p: p[0])
        summary = " ".join(s for _, s in top)
        if len(summary) > 420:
            summary = summary[:417].rsplit(" ", 1)[0] + "..."

        takeaways = []
        for _, s in ranked[2:5]:
            takeaways.append(s if len(s) <= 160 else s[:157].rsplit(" ", 1)[0] + "...")
        if len(takeaways) < 2:
            takeaways.extend([f"Reported by {job.source_name}", f"Topic: {job.category}"][: 3 - len(takeaways)])

        return {"summary": summary, "key_takeaways": takeaways, "cluster_id": None}
