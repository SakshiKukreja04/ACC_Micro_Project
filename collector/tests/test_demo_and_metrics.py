from app.demo_seed import DEMO_ARTICLES, build_demo_articles
from app.metrics import FEED_ERRORS
from app.repository import ArticleRepository
from app.scheduler import NewsCollectorService
from app.sources import RSSFeedSource


def test_demo_articles_are_clearly_labelled_and_idempotent(tmp_path):
    repo = ArticleRepository(db_url=f"sqlite:///{tmp_path/'demo.db'}", create_tables=True)
    articles = build_demo_articles()
    assert all(a["source_name"].startswith("Demo ") for a in articles)
    assert all(a["canonical_url"].startswith("https://demo.newsroom.local/") for a in articles)
    first = repo.save_articles(articles)
    assert first["inserted"] == len(DEMO_ARTICLES)
    assert repo.save_articles(build_demo_articles())["inserted"] == 0


def test_auto_seed_only_when_empty(tmp_path, monkeypatch):
    repo = ArticleRepository(db_url=f"sqlite:///{tmp_path/'auto.db'}", create_tables=True)
    service = NewsCollectorService(repository=repo)
    monkeypatch.setenv("SEED_DEMO_DATA", "false")
    assert service.maybe_seed_demo({}) == 0
    monkeypatch.setenv("SEED_DEMO_DATA", "auto")
    assert service.maybe_seed_demo({}) > 0
    assert service.maybe_seed_demo({}) == 0  # not empty any more


def test_unreachable_feed_counts_as_failure(tmp_path, monkeypatch):
    repo = ArticleRepository(db_url=f"sqlite:///{tmp_path/'f.db'}", create_tables=True)
    service = NewsCollectorService(repository=repo)
    monkeypatch.setattr(service.fetcher, "fetch_feed_xml", lambda url: None)
    src = RSSFeedSource(name="Down Feed", url="https://down.example/rss", category="World")
    before = FEED_ERRORS.labels(source="Down Feed")._value.get()
    summary = service.collect_once(sources=[src])
    assert summary["failed_sources"] == 1
    assert FEED_ERRORS.labels(source="Down Feed")._value.get() == before + 1
