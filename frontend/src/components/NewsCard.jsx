import React, { useState } from 'react';
import { BookmarkButton, GroundingBadge, ReadingTime, SentimentMark } from './ui';

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

export function NewsCard({ article, onOpenDetail, onOpenRelated, onSummaryGenerated, isSaved, onToggleBookmark, reason }) {
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
    sentiment,
    sentiment_score,
    grounding_score,
    reading_time_minutes,
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
          <div className="card-meta-right">
            <SentimentMark sentiment={sentiment} score={sentiment_score} compact />
            <time className="publish-time" dateTime={published_at}>
              {formatPublishedDate(published_at)}
            </time>
          </div>
        </div>
        {reason && <p className="card-reason">{reason}</p>}

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
              <span className="ai-badge-label">AI briefing</span>
              <GroundingBadge score={grounding_score} />
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
              title="Summarize this story"
            >
              {isSummarizing ? (
                <>
                  <span className="spinner-dot"></span>
                  <span>Summarizing…</span>
                </>
              ) : (
                <>
                  <span className="sparkle-icon">✨</span>
                  <span>Summarize this story</span>
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
          Read
        </button>
        <ReadingTime minutes={reading_time_minutes} />

        <div className="card-actions-right">
          {onToggleBookmark && <BookmarkButton saved={isSaved} onToggle={() => onToggleBookmark(article)} size="sm" />}
          <button
            className="btn-action-ghost"
            onClick={() => onOpenRelated(article)}
            title="See how other outlets covered this story"
          >
            Compare
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
