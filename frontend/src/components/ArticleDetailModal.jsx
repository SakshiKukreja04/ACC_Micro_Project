import React, { useState, useEffect } from 'react';
import apiService from '../services/api';

export function ArticleDetailModal({ article, onClose, onSelectRelated, onGenerateSummary }) {
  const [relatedList, setRelatedList] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [explanation, setExplanation] = useState(null);
  const [loadingExplain, setLoadingExplain] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);

  useEffect(() => {
    if (!article) return;
    setExplanation(null);
    let isMounted = true;

    async function loadRelated() {
      setLoadingRelated(true);
      try {
        const data = await apiService.getRelatedNews(article.id, { topK: 4 });
        if (isMounted) setRelatedList(data || []);
      } catch (err) {
        console.error('Failed to load related stories:', err);
      } finally {
        if (isMounted) setLoadingRelated(false);
      }
    }

    loadRelated();
    return () => {
      isMounted = false;
    };
  }, [article?.id]);

  const handleExplain = async () => {
    if (!article || loadingExplain) return;
    setLoadingExplain(true);
    try {
      const data = await apiService.explainArticle(article.id);
      setExplanation(data.explanation || 'No explanation generated.');
    } catch (err) {
      setExplanation('Could not load AI explanation at this time.');
    } finally {
      setLoadingExplain(false);
    }
  };

  const handleGenerateSummary = async () => {
    if (!article || isSummarizing) return;
    setIsSummarizing(true);
    try {
      if (onGenerateSummary) {
        await onGenerateSummary(article.id);
      }
    } catch (err) {
      console.error('Failed to generate summary:', err);
    } finally {
      setIsSummarizing(false);
    }
  };

  if (!article) return null;

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-content modal-detail" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close article modal">
          ✕
        </button>

        <div className="modal-top-tags">
          <span className="source-badge">{article.source_name}</span>
          <span className="category-tag">{article.category}</span>
          {article.published_at && (
            <span className="modal-date">
              {new Date(article.published_at).toLocaleString('en-US', {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
            </span>
          )}
        </div>

        <h2 id="modal-title" className="modal-headline">
          {article.title}
        </h2>

        {/* AI Summary and Key Takeaways Panel */}
        <section className="modal-ai-panel">
          <div className="modal-panel-header">
            <span className="ai-sparkle">✨</span>
            <span className="panel-title">AI Editorial Briefing</span>
          </div>

          {article.summary ? (
            <div>
              <p className="modal-summary-text">{article.summary}</p>
              {Array.isArray(article.key_takeaways) && article.key_takeaways.length > 0 && (
                <div className="modal-takeaways-block">
                  <strong className="takeaways-label">Key Takeaways:</strong>
                  <ul className="modal-takeaways-list">
                    {article.key_takeaways.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="ai-generate-prompt" style={{ padding: '8px 0' }}>
              <button
                className="btn-summarize-ondemand"
                onClick={handleGenerateSummary}
                disabled={isSummarizing}
              >
                {isSummarizing ? (
                  <>
                    <span className="spinner-dot"></span>
                    <span>Synthesizing Summary with Groq...</span>
                  </>
                ) : (
                  <>
                    <span className="sparkle-icon">✨</span>
                    <span>Generate AI Summary & Key Takeaways</span>
                  </>
                )}
              </button>
            </div>
          )}
        </section>

        {/* Article Full Body */}
        <section className="modal-body-section">
          <h4 className="section-title">Full Coverage & Notes</h4>
          <p className="modal-full-text">
            {article.content || article.description || 'Full content text is not provided by this RSS feed.'}
          </p>
        </section>

        {/* Educational Explainer Section */}
        <section className="modal-explainer-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
            <h4 className="section-title" style={{ margin: 0 }}>Plain-English Explainer</h4>
            {!explanation && (
              <button
                className="btn-secondary"
                onClick={handleExplain}
                disabled={loadingExplain}
                style={{ fontSize: '12px', padding: '5px 12px' }}
              >
                {loadingExplain ? 'Analyzing with Groq...' : '💡 Explain This Context'}
              </button>
            )}
          </div>

          {loadingExplain && (
            <div className="explainer-loading">Consulting LLM to break down background and significance...</div>
          )}

          {explanation && (
            <div className="explainer-content">
              <p>{explanation}</p>
            </div>
          )}
        </section>

        {/* Semantically Related News Section */}
        <section className="modal-related-section">
          <h4 className="section-title">Related Stories (FAISS Vector Similarity)</h4>
          {loadingRelated ? (
            <div className="explainer-loading">Finding conceptually related articles...</div>
          ) : relatedList.length === 0 ? (
            <p className="empty-subtext">No other stories in the current collection exceeded the similarity threshold.</p>
          ) : (
            <div className="modal-related-grid">
              {relatedList.map((rel) => (
                <div key={rel.id} className="related-mini-card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span className="source-badge" style={{ fontSize: '11px', padding: '2px 8px' }}>
                      {rel.source_name}
                    </span>
                    <span className="similarity-pill">
                      {Math.round(rel.similarity_score * 100)}% match
                    </span>
                  </div>
                  <h5 className="related-title">
                    <button
                      className="title-link-btn"
                      onClick={() => onSelectRelated(rel)}
                    >
                      {rel.title}
                    </button>
                  </h5>
                  <p className="related-desc">
                    {rel.summary || (rel.description ? `${rel.description.slice(0, 100)}...` : '')}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Footer Actions */}
        <div className="modal-footer">
          <a
            href={article.canonical_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-card-primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <span>Read Original Publisher Story</span>
            <span>↗</span>
          </a>
          <button className="btn-secondary" onClick={onClose}>
            Close Window
          </button>
        </div>
      </div>
    </div>
  );
}

export default ArticleDetailModal;
