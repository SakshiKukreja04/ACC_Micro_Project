import React, { useState, useEffect, useCallback } from 'react';
import apiService from './services/api';
import Navbar, { TABS } from './components/Navbar';
import SearchBar from './components/SearchBar';
import CategoryFilter from './components/CategoryFilter';
import NewsCard from './components/NewsCard';
import ArticleDetailModal from './components/ArticleDetailModal';
import LoadingSkeleton from './components/LoadingSkeleton';
import EmptyState from './components/EmptyState';
import ChatbotPanel from './components/ChatbotPanel';
import BriefingCard from './components/BriefingCard';
import ForYouPanel from './components/ForYouPanel';
import SavedPanel from './components/SavedPanel';
import InsightsPanel from './components/InsightsPanel';
import MonitorPanel from './components/MonitorPanel';
import LiveToast from './components/LiveToast';
import './App.css';
import './features.css';

const PAGE_SIZE = 9;
const TONES = [
  { id: '', label: 'Any tone' },
  { id: 'positive', label: 'Positive' },
  { id: 'neutral', label: 'Neutral' },
  { id: 'negative', label: 'Negative' },
];

function initialTab() {
  const hash = window.location.hash.replace('#', '');
  return TABS.some((t) => t.id === hash) ? hash : 'feed';
}

export function App() {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('nexus_news_theme') || 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('nexus_news_theme', theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  // Filters & search
  const [categories, setCategories] = useState(['All']);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [tone, setTone] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearchTerm, setActiveSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  const [activeArticle, setActiveArticle] = useState(null);
  const [modalClosures, setModalClosures] = useState(0);
  const [bookmarkIds, setBookmarkIds] = useState(() => new Set());

  // Semantic search
  const [semanticQuery, setSemanticQuery] = useState('');
  const [semanticResults, setSemanticResults] = useState([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [semanticSearched, setSemanticSearched] = useState(false);

  // Health & live events
  const [isHealthy, setIsHealthy] = useState(true);
  const [isLive, setIsLive] = useState(false);
  const [liveEvent, setLiveEvent] = useState(null);

  const selectTab = (tab) => {
    setActiveTab(tab);
    setPage(1);
    window.history.replaceState(null, '', `#${tab}`);
    window.scrollTo({ top: 0 });
  };

  const loadCategories = useCallback(async () => {
    try {
      const catData = await apiService.getCategories();
      if (Array.isArray(catData) && catData.length > 0) {
        setCategories(['All', ...catData.map((c) => c.category)]);
      }
    } catch {
      /* keep defaults */
    }
  }, []);

  useEffect(() => {
    loadCategories();
    apiService
      .getHealth()
      .then((h) => setIsHealthy(h.status === 'healthy'))
      .catch(() => setIsHealthy(false));
    apiService
      .getBookmarkIds()
      .then((ids) => setBookmarkIds(new Set(ids)))
      .catch(() => {});

    const unsubscribe = apiService.subscribeEvents({
      open: () => {
        setIsLive(true);
        setIsHealthy(true);
      },
      error: () => setIsLive(false),
      new_articles: (evt) => {
        setLiveEvent((prev) => (prev ? { ...evt, new_count: prev.new_count + evt.new_count } : evt));
        loadCategories();
      },
    });
    return unsubscribe;
  }, [loadCategories]);

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (activeTab === 'trending') {
        const data = await apiService.getTrending(12, selectedCategory);
        setArticles(data || []);
        setTotalPages(1);
        setTotalCount(data.length || 0);
      } else if (activeSearchTerm) {
        const data = await apiService.searchNews(activeSearchTerm, { page, pageSize: PAGE_SIZE, category: selectedCategory });
        setArticles(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      } else {
        const data = await apiService.getNewsFeed({ page, pageSize: PAGE_SIZE, category: selectedCategory, sentiment: tone });
        setArticles(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      }
    } catch (err) {
      setError(`Couldn't load stories: ${err.message}. Check that the backend is running, then retry.`);
    } finally {
      setLoading(false);
    }
  }, [activeTab, page, selectedCategory, activeSearchTerm, tone]);

  useEffect(() => {
    if (activeTab === 'feed' || activeTab === 'trending') fetchArticles();
  }, [fetchArticles, activeTab, reloadKey]);

  const updateArticleEverywhere = (articleId, patch) => {
    setArticles((prev) => prev.map((a) => (a.id === articleId ? { ...a, ...patch } : a)));
    setActiveArticle((prev) => (prev && prev.id === articleId ? { ...prev, ...patch } : prev));
  };

  const handleGenerateSummary = async (articleId) => {
    const res = await apiService.generateSummary(articleId);
    if (res && res.summary) {
      const { id: _id, title: _title, cached: _cached, ...patch } = res;
      updateArticleEverywhere(articleId, patch);
    }
    return res;
  };

  const toggleBookmark = async (article) => {
    const id = article.id;
    const saved = bookmarkIds.has(id);
    const apply = (shouldHave) =>
      setBookmarkIds((prev) => {
        const next = new Set(prev);
        if (shouldHave) next.add(id);
        else next.delete(id);
        return next;
      });
    apply(!saved);
    try {
      if (saved) await apiService.removeBookmark(id);
      else await apiService.addBookmark(id);
    } catch {
      apply(saved);
    }
  };

  const openArticleById = async (id) => {
    try {
      setActiveArticle(await apiService.getArticle(id));
    } catch {
      /* article may have been removed */
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    setActiveSearchTerm(searchQuery.trim());
  };

  const handleSearchClear = () => {
    setSearchQuery('');
    setActiveSearchTerm('');
    setPage(1);
  };

  const handleCategorySelect = (cat) => {
    setSelectedCategory(cat);
    setPage(1);
  };

  const handleSemanticSearch = async (e) => {
    e.preventDefault();
    const query = semanticQuery.trim();
    if (!query) return;
    setSemanticLoading(true);
    try {
      const data = await apiService.semanticSearch(query, { topK: 8 });
      setSemanticResults(data.items || []);
    } catch {
      setSemanticResults([]);
    } finally {
      setSemanticSearched(true);
      setSemanticLoading(false);
    }
  };

  const showLiveStories = () => {
    setLiveEvent(null);
    handleSearchClear();
    setSelectedCategory('');
    setTone('');
    selectTab('feed');
    setReloadKey((k) => k + 1);
  };

  const cardProps = {
    onOpenDetail: (item) => setActiveArticle(item),
    onOpenRelated: (item) => setActiveArticle(item),
    onSummaryGenerated: handleGenerateSummary,
    onToggleBookmark: toggleBookmark,
  };

  return (
    <div className="app-container">
      <a href="#main-content" className="skip-link">Skip to stories</a>
      <Navbar
        activeTab={activeTab}
        onSelectTab={selectTab}
        isHealthy={isHealthy}
        isLive={isLive}
        savedCount={bookmarkIds.size}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === 'light' ? 'dark' : 'light'))}
      />

      <main id="main-content">
        {(activeTab === 'feed' || activeTab === 'trending') && (
          <div>
            <header className="hero-section">
              <div className="hero-date-line">
                <span>{new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</span>
              </div>
              <h1 className="hero-title">
                {activeTab === 'trending' ? 'Stories with the widest coverage' : 'Today’s reporting, summarised'}
              </h1>
              <p className="hero-subtitle">
                {activeTab === 'trending'
                  ? 'Ranked by recency and by how many different outlets are covering the same story.'
                  : 'Collected from RSS feeds and news APIs, summarised by AI, and checked against the source text.'}
              </p>
            </header>

            {activeTab === 'feed' && !activeSearchTerm && page === 1 && (
              <BriefingCard category={selectedCategory} onOpenArticleById={openArticleById} />
            )}

            <div className="control-bar">
              <CategoryFilter categories={categories} selectedCategory={selectedCategory} onSelectCategory={handleCategorySelect} />
              {activeTab === 'feed' && (
                <SearchBar value={searchQuery} onChange={setSearchQuery} onSubmit={handleSearchSubmit} onClear={handleSearchClear} />
              )}
            </div>

            {activeTab === 'feed' && !activeSearchTerm && (
              <div className="tone-filter" role="group" aria-label="Filter by tone">
                {TONES.map((t) => (
                  <button
                    key={t.id || 'any'}
                    type="button"
                    className={`tone-chip ${t.id ? `sentiment-${t.id}` : ''} ${tone === t.id ? 'active' : ''}`}
                    aria-pressed={tone === t.id}
                    onClick={() => {
                      setTone(t.id);
                      setPage(1);
                    }}
                  >
                    {t.id && <span className="sentiment-dot" aria-hidden="true" />}
                    {t.label}
                  </button>
                ))}
              </div>
            )}

            {error && (
              <div className="error-banner" role="alert">
                <span>{error}</span>
                <button className="btn-secondary" onClick={fetchArticles} style={{ fontSize: '12px' }}>Retry</button>
              </div>
            )}

            {(activeSearchTerm || selectedCategory) && (
              <div className="filter-status-row">
                <span>
                  {totalCount} {totalCount === 1 ? 'story' : 'stories'}
                  {activeSearchTerm && <> matching <strong>“{activeSearchTerm}”</strong></>}
                  {selectedCategory && <> in <span className="category-pill-active">{selectedCategory}</span></>}
                </span>
                <button
                  className="clear-filters-btn"
                  onClick={() => {
                    handleSearchClear();
                    setSelectedCategory('');
                  }}
                >
                  Clear filters ✕
                </button>
              </div>
            )}

            {loading ? (
              <LoadingSkeleton count={6} />
            ) : articles.length === 0 ? (
              <EmptyState
                message={
                  activeSearchTerm
                    ? `No stories match “${activeSearchTerm}”. Try fewer words, or use Discover to search by meaning.`
                    : 'No stories match these filters yet. The collector checks feeds every few minutes.'
                }
                onReset={() => {
                  handleSearchClear();
                  setSelectedCategory('');
                  setTone('');
                }}
              />
            ) : (
              <div className="news-grid" aria-label="Stories">
                {articles.map((art) => (
                  <NewsCard key={art.id} article={art} isSaved={bookmarkIds.has(art.id)} {...cardProps} />
                ))}
              </div>
            )}

            {activeTab === 'feed' && totalPages > 1 && !loading && (
              <nav className="pagination" aria-label="Pagination">
                <button className="page-btn" onClick={() => { setPage((p) => Math.max(p - 1, 1)); window.scrollTo({ top: 120, behavior: 'smooth' }); }} disabled={page <= 1} id="btn-prev-page">
                  ← Previous
                </button>
                <span className="pagination-info">
                  Page <strong>{page}</strong> of <strong>{totalPages}</strong>
                  <span className="pagination-total"> ({totalCount} stories)</span>
                </span>
                <button className="page-btn" onClick={() => { setPage((p) => Math.min(p + 1, totalPages)); window.scrollTo({ top: 120, behavior: 'smooth' }); }} disabled={page >= totalPages} id="btn-next-page">
                  Next →
                </button>
              </nav>
            )}
          </div>
        )}

        {activeTab === 'foryou' && (
          <ForYouPanel {...cardProps} onOpenDetail={(a) => setActiveArticle(a)} bookmarkIds={bookmarkIds} refreshKey={modalClosures} />
        )}

        {activeTab === 'semantic' && (
          <div className="tab-container-narrow">
            <header className="hero-section" style={{ padding: '32px 0 24px' }}>
              <h1 className="hero-title" style={{ fontSize: '36px' }}>Search by meaning</h1>
              <p className="hero-subtitle">
                Describe what you’re looking for in your own words. Results are matched by meaning, so they don’t need to share your exact keywords.
              </p>
            </header>

            <form onSubmit={handleSemanticSearch} className="semantic-form">
              <input
                type="text"
                className="chat-input"
                placeholder="e.g. countries agreeing to cut pollution, or loans getting more expensive"
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                aria-label="Describe what you are looking for"
              />
              <button type="submit" className="btn-primary" disabled={semanticLoading || !semanticQuery.trim()}>
                {semanticLoading ? 'Searching…' : 'Search'}
              </button>
            </form>

            {semanticLoading ? (
              <div className="explainer-loading" style={{ margin: '40px auto', textAlign: 'center' }}>Matching your description against every story…</div>
            ) : semanticResults.length > 0 ? (
              <div className="semantic-results-list">
                {semanticResults.map((item) => (
                  <article key={item.id} className="news-card semantic-item">
                    <div className="card-top">
                      <div className="card-meta-left">
                        <span className="source-badge">{item.source_name}</span>
                        <span className="category-tag">{item.category}</span>
                      </div>
                      <span className="similarity-pill">{Math.round((item.similarity_score || 0) * 100)}% match</span>
                    </div>
                    <h3 className="card-title">
                      <button className="title-button" onClick={() => setActiveArticle(item)}>{item.title}</button>
                    </h3>
                    <p className="card-desc">{item.summary || item.description || 'No excerpt available.'}</p>
                    <div className="card-actions">
                      <button className="btn-secondary" onClick={() => setActiveArticle(item)}>Open story</button>
                      <a href={item.canonical_url} target="_blank" rel="noopener noreferrer" className="btn-action-ghost">Original ↗</a>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-subtext" style={{ textAlign: 'center', marginTop: '40px' }}>
                {semanticSearched ? 'Nothing close enough in meaning. Try describing the topic differently.' : 'Results appear here, ranked by how closely they match your description.'}
              </div>
            )}
          </div>
        )}

        {activeTab === 'chat' && <ChatbotPanel />}

        {activeTab === 'insights' && (
          <InsightsPanel
            onOpenArticleById={openArticleById}
            onPickCategory={(cat) => {
              setSelectedCategory(cat);
              selectTab('feed');
            }}
          />
        )}

        {activeTab === 'saved' && (
          <SavedPanel
            {...cardProps}
            bookmarkIds={bookmarkIds}
            onForgotten={() => setBookmarkIds(new Set())}
          />
        )}

        {activeTab === 'monitor' && <MonitorPanel />}
      </main>

      {activeArticle && (
        <ArticleDetailModal
          article={activeArticle}
          onClose={() => {
            setActiveArticle(null);
            setModalClosures((c) => c + 1);
          }}
          onSelectRelated={(rel) => setActiveArticle(rel)}
          onOpenArticleById={openArticleById}
          onGenerateSummary={handleGenerateSummary}
          isSaved={bookmarkIds.has(activeArticle.id)}
          onToggleBookmark={toggleBookmark}
        />
      )}

      <LiveToast event={liveEvent} onRefresh={showLiveStories} onDismiss={() => setLiveEvent(null)} />
    </div>
  );
}

export default App;
