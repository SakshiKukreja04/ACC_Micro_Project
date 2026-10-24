import React, { useState } from 'react';

function formatPublishedDate(dateStr) {
  if (!dateStr) return 'Recently';
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const diffHours = Math.round((now - d) / (1000 * 60 * 60));
    if (diffHours >= 0 && diffHours < 1) return 'Just now';
    if (diffHours >= 1 && diffHours < 24) return `${diffHours}h ago`;
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return 'Recently';
  }
}

function getSourceClass(sourceName) {
  const s = (sourceName || '').toLowerCase();
  if (s.includes('bbc')) return 'source-bbc';
  if (s.includes('npr')) return 'source-npr';
  if (s.includes('ars')) return 'source-ars';
  if (s.includes('verge')) return 'source-verge';
  return 'source-default';
}

export function NewsCard({ article, onOpenDetail, onOpenRelated, onSummaryGenerated }) {
  const [isSummarizing, setIsSummarizing] = useState(false);

  const {
    id,
    title,
    source_name,
    category,
    published_at,
    description,
    canonical_url,
    summary,
    key_takeaways,
  } = article;

  const handleSummarizeClick = async (e) => {
    e.stopPropagation();
    if (isSummarizing) return;
    setIsSummarizing(true);
    try {
      if (onSummaryGenerated) {
        await onSummaryGenerated(id);
      }
    } catch (err) {
      console.error('Failed to generate summary:', err);
    } finally {
      setIsSummarizing(false);
    }
  };

  return (
    <article className="news-card" tabIndex="0">
      <div>
        {/* Top Metadata */}
        <div className="card-top">
          <div className="card-meta-left">
            <span className={`source-badge ${getSourceClass(source_name)}`}>
              {source_name}
            </span>
            <span className="category-tag">{category}</span>
          </div>
          <time className="publish-time" dateTime={published_at}>
            {formatPublishedDate(published_at)}
          </time>
        </div>

        {/* Headline */}
        <h3 className="card-title">
          <button
            className="title-button"
            onClick={() => onOpenDetail(article)}
            title="Read full article details"
          >
            {title}
          </button>
        </h3>

        {/* Excerpt */}
        <p className="card-desc">
          {description ? (description.length > 175 ? `${description.slice(0, 175)}...` : description) : 'Click below for coverage details.'}
        </p>

        {/* AI Summary Section: Either show summary or an on-demand Generate button */}
        {summary ? (
          <div className="ai-summary-box">
            <div className="ai-summary-header">
              <span className="ai-badge-label">Editorial AI Briefing</span>
            </div>
            <p className="ai-summary-text">{summary}</p>
            {Array.isArray(key_takeaways) && key_takeaways.length > 0 && (
              <ul className="takeaways-list" aria-label="Key Takeaways">
                {key_takeaways.slice(0, 3).map((takeaway, idx) => (
                  <li key={idx}>{takeaway}</li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="ai-generate-prompt">
            <button
              className="btn-summarize-ondemand"
              onClick={handleSummarizeClick}
              disabled={isSummarizing}
              title="Generate summary using Groq LLM"
            >
              {isSummarizing ? (
                <>
                  <span className="spinner-dot"></span>
                  <span>Summarizing with Groq...</span>
                </>
              ) : (
                <>
                  <span className="sparkle-icon">✨</span>
                  <span>Generate AI Summary</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Card Actions */}
      <div className="card-actions">
        <button
          className="btn-card-primary"
          onClick={() => onOpenDetail(article)}
          aria-label={`View full details of ${title}`}
        >
          Read Details
        </button>

        <div className="card-actions-right">
          <button
            className="btn-action-ghost"
            onClick={() => onOpenRelated(article)}
            title="Find semantically similar stories"
          >
            🔗 Related
          </button>

          <a
            href={canonical_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-action-ghost"
            title="Open original story on publisher site"
          >
            Source ↗
          </a>
        </div>
      </div>
    </article>
  );
}

export default NewsCard;
