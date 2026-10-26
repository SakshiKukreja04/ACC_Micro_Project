import React from 'react';

/** Small, reusable signal components shared by cards, the modal and list views. */

const SENTIMENT_LABEL = { positive: 'Positive tone', neutral: 'Neutral tone', negative: 'Negative tone' };

export function SentimentMark({ sentiment, score, compact = false }) {
  if (!sentiment) return null;
  const title = score !== undefined && score !== null ? `${SENTIMENT_LABEL[sentiment]} (${score > 0 ? '+' : ''}${Number(score).toFixed(2)})` : SENTIMENT_LABEL[sentiment];
  return (
    <span className={`sentiment-mark sentiment-${sentiment}`} title={title}>
      <span className="sentiment-dot" aria-hidden="true" />
      {!compact && <span>{sentiment}</span>}
      {compact && <span className="sr-only">{title}</span>}
    </span>
  );
}

/** Fact-Grounding score: how much of the AI summary is traceable to the source text. */
export function GroundingBadge({ score }) {
  if (score === null || score === undefined) return null;
  const pct = Math.round(score * 100);
  const level = score >= 0.8 ? 'high' : score >= 0.6 ? 'medium' : 'low';
  return (
    <span
      className={`grounding-badge grounding-${level}`}
      title={`Fact-Grounding: ${pct}% of the summary's key words appear in the source article. Lower scores can signal content the source does not support.`}
    >
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeOpacity="0.3" strokeWidth="2" />
        <circle
          cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="2"
          strokeDasharray={`${(pct / 100) * 31.4} 31.4`} transform="rotate(-90 6 6)" strokeLinecap="round"
        />
      </svg>
      {pct}% grounded
    </span>
  );
}

export function ReadingTime({ minutes }) {
  if (!minutes) return null;
  return <span className="reading-time">{minutes} min read</span>;
}

export function BookmarkButton({ saved, onToggle, size = 'md' }) {
  return (
    <button
      type="button"
      className={`bookmark-btn bookmark-${size} ${saved ? 'is-saved' : ''}`}
      onClick={(e) => {
        e.stopPropagation();
        onToggle?.();
      }}
      aria-pressed={saved}
      aria-label={saved ? 'Remove from saved stories' : 'Save story'}
      title={saved ? 'Saved — click to remove' : 'Save for later'}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"
          fill={saved ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round"
        />
      </svg>
      {size !== 'sm' && <span>{saved ? 'Saved' : 'Save'}</span>}
    </button>
  );
}

export function formatAge(dateStr) {
  if (!dateStr) return 'Recently';
  const d = new Date(dateStr);
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function formatSeconds(s) {
  if (s === null || s === undefined) return '—';
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
}
