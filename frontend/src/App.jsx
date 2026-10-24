import React, { useState, useEffect, useCallback } from 'react';
import apiService from './services/api';
import Navbar from './components/Navbar';
import SearchBar from './components/SearchBar';
import CategoryFilter from './components/CategoryFilter';
import NewsCard from './components/NewsCard';
import ArticleDetailModal from './components/ArticleDetailModal';
import LoadingSkeleton from './components/LoadingSkeleton';
import EmptyState from './components/EmptyState';
import ChatbotPanel from './components/ChatbotPanel';
import ArchitecturePanel from './components/ArchitecturePanel';
import './App.css';

export function App() {
  const [activeTab, setActiveTab] = useState('feed'); // 'feed' | 'trending' | 'semantic' | 'chat' | 'cloud'
  const [articles, setArticles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Dual Theme Mode: 'light' or 'dark' (Defaulting to warm editorial light mode)
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('nexus_news_theme') || 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('nexus_news_theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  };

  // Filter & Search state
  const [categories, setCategories] = useState(['All', 'World', 'Business', 'AI', 'Science', 'Technology', 'Politics']);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeSearchTerm, setActiveSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Selected article for Detail modal
  const [activeArticle, setActiveArticle] = useState(null);

  // Semantic Search state
  const [semanticQuery, setSemanticQuery] = useState('');
  const [semanticResults, setSemanticResults] = useState([]);
  const [semanticLoading, setSemanticLoading] = useState(false);

  // Health probe
  const [isHealthy, setIsHealthy] = useState(true);
  const [healthData, setHealthData] = useState(null);

  // Fetch Categories on mount
  useEffect(() => {
    async function loadCategories() {
      try {
        const catData = await apiService.getCategories();
        if (Array.isArray(catData) && catData.length > 0) {
          const names = ['All', ...catData.map((c) => c.category)];
          setCategories(names);
        }
      } catch (err) {
        console.warn('Could not load dynamic categories, using defaults:', err);
      }
    }

    async function checkHealth() {
      try {
        const h = await apiService.getHealth();
        setIsHealthy(h.status === 'healthy');
        setHealthData(h);
      } catch {
        setIsHealthy(false);
      }
    }

    loadCategories();
    checkHealth();
  }, []);

  // Fetch News Feed (Top 6 articles per category / page)
  const PAGE_SIZE = 6;

  const fetchArticles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (activeTab === 'trending') {
        const data = await apiService.getTrending(PAGE_SIZE);
        setArticles(data || []);
        setTotalPages(1);
        setTotalCount(data.length || 0);
      } else if (activeSearchTerm) {
        const data = await apiService.searchNews(activeSearchTerm, {
          page,
          pageSize: PAGE_SIZE,
          category: selectedCategory,
        });
        setArticles(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      } else {
        const data = await apiService.getNewsFeed({
          page,
          pageSize: PAGE_SIZE,
          category: selectedCategory,
        });
        setArticles(data.items || []);
        setTotalPages(data.total_pages || 1);
        setTotalCount(data.total || 0);
      }
    } catch (err) {
      setError(err.message || 'Failed to load news articles from backend.');
    } finally {
      setLoading(false);
    }
  }, [activeTab, page, selectedCategory, activeSearchTerm]);

  useEffect(() => {
    if (activeTab === 'feed' || activeTab === 'trending') {
      fetchArticles();
    }
  }, [fetchArticles, activeTab]);

  // On-demand AI Summarization Handler
  const handleGenerateSummary = async (articleId) => {
    try {
      const res = await apiService.generateSummary(articleId);
      if (res && res.summary) {
        // Update articles list
        setArticles((prev) =>
          prev.map((a) =>
            a.id === articleId
              ? { ...a, summary: res.summary, key_takeaways: res.key_takeaways }
              : a
          )
        );
        // If the article is open in the modal, update it too
        setActiveArticle((prev) =>
          prev && prev.id === articleId
            ? { ...prev, summary: res.summary, key_takeaways: res.key_takeaways }
            : prev
        );
      }
      return res;
    } catch (err) {
      console.error('Failed to generate summary for article:', articleId, err);
      throw err;
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
      const data = await apiService.semanticSearch(query, { topK: 6 });
      setSemanticResults(data.items || []);
    } catch (err) {
      console.error('Semantic search failed:', err);
    } finally {
      setSemanticLoading(false);
    }
  };

  return (
    <div className="app-container">
      {/* Top Editorial Masthead & Navigation */}
      <Navbar
        activeTab={activeTab}
        onSelectTab={(tab) => {
          setActiveTab(tab);
          setPage(1);
        }}
        isHealthy={isHealthy}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      {/* Main Content Area */}
      <main id="main-content">
        {/* NEWS FEED & TRENDING TABS */}
        {(activeTab === 'feed' || activeTab === 'trending') && (
          <div>
            {/* Editorial Header */}
            <header className="hero-section">
              <div className="hero-date-line">
                <span>{new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</span>
                <span className="divider-dot">•</span>
                <span>Top Curated Editorial Edition</span>
              </div>
              <h1 className="hero-title">
                {activeTab === 'trending' ? (
                  <>Trending & High-Prominence <span className="hero-accent">Stories</span></>
                ) : (
                  <>Verified Global Reporting & <span className="hero-accent">Editorial Briefs</span></>
                )}
              </h1>
              <p className="hero-subtitle">
                {activeTab === 'trending'
                  ? 'Real-time multi-source analysis highlighting the most prominent global coverage right now.'
                  : 'Independent RSS collection from BBC News, NPR, Ars Technica, and The Verge. Synthesized with Groq high-speed LLM and dense vector search.'}
              </p>
            </header>

            {/* Filter & Search Bar */}
            <div className="control-bar">
              <CategoryFilter
                categories={categories}
                selectedCategory={selectedCategory}
                onSelectCategory={handleCategorySelect}
              />

              {activeTab === 'feed' && (
                <SearchBar
                  value={searchQuery}
                  onChange={setSearchQuery}
                  onSubmit={handleSearchSubmit}
                  onClear={handleSearchClear}
                />
              )}
            </div>

            {/* Error Message */}
            {error && (
              <div className="error-banner" role="alert">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>⚠️</span>
                  <span>{error}</span>
                </div>
                <button className="btn-secondary" onClick={fetchArticles} style={{ fontSize: '12px' }}>
                  Retry Request
                </button>
              </div>
            )}

            {/* Active Search / Filter Indicator */}
            {(activeSearchTerm || selectedCategory) && (
              <div className="filter-status-row">
                <span>
                  Showing top stories for {activeSearchTerm && <strong>"{activeSearchTerm}"</strong>}
                  {activeSearchTerm && selectedCategory && ' in '}
                  {selectedCategory && <span className="category-pill-active">{selectedCategory}</span>}
                  {` (${totalCount} stories indexed)`}
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

            {/* News Cards Grid or Loading Skeleton or Empty State */}
            {loading ? (
              <LoadingSkeleton count={6} />
            ) : articles.length === 0 ? (
              <EmptyState
                message={
                  activeSearchTerm
                    ? `No stories matched "${activeSearchTerm}". Try another keyword or browse all categories.`
                    : 'No stories available in this category at the moment.'
                }
                onReset={() => {
                  handleSearchClear();
                  setSelectedCategory('');
                }}
              />
            ) : (
              <div className="news-grid" aria-label="Articles list">
                {articles.map((art) => (
                  <NewsCard
                    key={art.id}
                    article={art}
                    onOpenDetail={(item) => setActiveArticle(item)}
                    onOpenRelated={(item) => setActiveArticle(item)}
                    onSummaryGenerated={handleGenerateSummary}
                  />
                ))}
              </div>
            )}

            {/* Pagination Controls */}
            {activeTab === 'feed' && totalPages > 1 && !loading && (
              <nav className="pagination" aria-label="Pagination Navigation">
                <button
                  className="page-btn"
                  onClick={() => {
                    setPage((p) => Math.max(p - 1, 1));
                    window.scrollTo({ top: 120, behavior: 'smooth' });
                  }}
                  disabled={page <= 1}
                  id="btn-prev-page"
                >
                  ← Previous
                </button>
                <span className="pagination-info">
                  Page <strong>{page}</strong> of <strong>{totalPages}</strong>
                  <span className="pagination-total"> ({totalCount} total stories)</span>
                </span>
                <button
                  className="page-btn"
                  onClick={() => {
                    setPage((p) => Math.min(p + 1, totalPages));
                    window.scrollTo({ top: 120, behavior: 'smooth' });
                  }}
                  disabled={page >= totalPages}
                  id="btn-next-page"
                >
                  Next →
                </button>
              </nav>
            )}
          </div>
        )}

        {/* SEMANTIC VECTOR SEARCH TAB */}
        {activeTab === 'semantic' && (
          <div className="tab-container-narrow">
            <header className="hero-section" style={{ padding: '32px 0 24px' }}>
              <h1 className="hero-title" style={{ fontSize: '36px' }}>
                Dense Vector <span className="hero-accent">Semantic Discovery</span>
              </h1>
              <p className="hero-subtitle">
                Explore news stories by concepts and deep contextual meaning using 384-dimensional embeddings in FAISS.
              </p>
            </header>

            <form onSubmit={handleSemanticSearch} className="semantic-form">
              <input
                type="text"
                className="chat-input"
                placeholder="Search ideas (e.g., 'quantum breakthrough', 'central bank rate cuts', 'autonomous space missions')..."
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                aria-label="Semantic search query"
              />
              <button type="submit" className="btn-primary" disabled={semanticLoading || !semanticQuery.trim()}>
                {semanticLoading ? 'Computing...' : 'Vector Search'}
              </button>
            </form>

            {semanticLoading ? (
              <div className="explainer-loading" style={{ margin: '40px auto', textAlign: 'center' }}>
                Projecting query embedding into dense vector space and matching via inner product cosine similarity...
              </div>
            ) : semanticResults.length > 0 ? (
              <div className="semantic-results-list">
                {semanticResults.map((item) => (
                  <article key={item.id} className="news-card semantic-item">
                    <div className="card-top">
                      <div className="card-meta-left">
                        <span className="source-badge">{item.source_name}</span>
                        <span className="category-tag">{item.category}</span>
                      </div>
                      <span className="similarity-pill">
                        {Math.round((item.similarity_score || 0) * 100)}% Match
                      </span>
                    </div>

                    <h3 className="card-title">
                      <button className="title-button" onClick={() => setActiveArticle(item)}>
                        {item.title}
                      </button>
                    </h3>

                    <p className="card-desc">
                      {item.summary || item.description || 'No excerpt available.'}
                    </p>

                    <div className="card-actions">
                      <button className="btn-secondary" onClick={() => setActiveArticle(item)}>
                        View Details & Related
                      </button>
                      <a
                        href={item.canonical_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-action-ghost"
                      >
                        Original Source ↗
                      </a>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-subtext" style={{ textAlign: 'center', marginTop: '40px' }}>
                Type any natural language inquiry above to search semantic concepts across our corpus.
              </div>
            )}
          </div>
        )}

        {/* ASK AI (RAG) CHAT TAB */}
        {activeTab === 'chat' && <ChatbotPanel />}

        {/* SYSTEM ARCHITECTURE TAB */}
        {activeTab === 'cloud' && <ArchitecturePanel healthData={healthData} />}
      </main>

      {/* ARTICLE DETAIL MODAL */}
      {activeArticle && (
        <ArticleDetailModal
          article={activeArticle}
          onClose={() => setActiveArticle(null)}
          onSelectRelated={(relatedArticle) => setActiveArticle(relatedArticle)}
          onGenerateSummary={handleGenerateSummary}
        />
      )}
    </div>
  );
}

export default App;
