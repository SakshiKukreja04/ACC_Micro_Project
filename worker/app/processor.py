import abc
import logging
from typing import Any, Dict
from app.queue import ArticleJob

logger = logging.getLogger("worker.processor")


class BaseArticleProcessor(abc.ABC):
    """Abstract interface for article background processors."""

    @abc.abstractmethod
    def process(self, job: ArticleJob) -> Dict[str, Any]:
        """Process an article job and return dictionary with result fields."""
        pass


class DeterministicTestProcessor(BaseArticleProcessor):
    """
    Fallback editorial processor that synthesizes clean summaries from article descriptions.
    Used when external LLM API is unavailable.
    """

    def process(self, job: ArticleJob) -> Dict[str, Any]:
        logger.debug(f"Synthesizing editorial summary for article: {job.id} ('{job.title[:30]}...')")
        desc = (job.description or job.content or "").strip()
        summary_text = desc[:280] + ("..." if len(desc) > 280 else "") if desc else f"Reporting from {job.source_name} covering {job.title}."
        return {
            "summary": summary_text,
            "key_takeaways": [
                f"Source: {job.source_name}",
                f"Topic: {job.category}",
                "Full story available at publisher link",
            ],
            "cluster_id": None,
        }
