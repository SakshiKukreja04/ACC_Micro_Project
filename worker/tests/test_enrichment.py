from app.processor import DeterministicTestProcessor
from app.queue import ArticleJob
from app.worker import BackgroundWorkerService


def _job(**kw):
    base = dict(
        id="j1", title="Velora AI releases open model", canonical_url="https://x/1", source_name="Demo Wire",
        category="General", processing_attempts=1, published_at=None,
        description="Velora AI released an open model that topped a reasoning benchmark.",
        content=(
            "Velora AI released an open model that topped a reasoning benchmark on Tuesday. "
            "The model runs on a single graphics card, which helps universities. "
            "Regulators said they are studying how rules apply to open AI models. "
            "Competitors are expected to respond with their own releases."
        ),
    )
    base.update(kw)
    return ArticleJob(**base)


def test_extractive_summary_has_no_repeated_sentences():
    out = DeterministicTestProcessor().process(_job())
    sentences = [s.strip() for s in out["summary"].split(". ") if s.strip()]
    assert len(sentences) == len(set(sentences))
    assert out["summary"].count("topped a reasoning benchmark") == 1
    assert 2 <= len(out["key_takeaways"]) <= 3


def test_enrich_adds_signals_and_canonical_category():
    job = _job()
    result = BackgroundWorkerService.enrich(job, {"summary": "Velora AI released an open model.", "key_takeaways": ["a", "b"]})
    assert result["sentiment"] in {"positive", "neutral", "negative"}
    assert 0 <= result["grounding_score"] <= 1
    assert result["category"] == "Technology"  # 'General' feed classified by keywords
    assert result["keywords"]


def test_llm_suggested_category_wins_when_canonical():
    result = BackgroundWorkerService.enrich(_job(), {"summary": "x y z", "key_takeaways": [], "suggested_category": "science"})
    assert result["category"] == "Science"
    assert "suggested_category" not in result
