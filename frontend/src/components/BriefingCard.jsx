import React, { useEffect, useState } from 'react';
import apiService from '../services/api';

/** AI Daily Briefing: a one-minute digest of the top stories, with numbered links into each story. */
export function BriefingCard({ category, onOpenArticleById }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(true);

  const load = (refresh = false) => {
    setLoading(true);
    apiService
      .getBriefing({ category: category || undefined, refresh })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(false);
  }, [category]);

  if (!loading && (!data || !data.available)) return null;

  const storyByRef = Object.fromEntries((data?.stories || []).map((s) => [s.ref, s]));

  // Turn "[2]" citations in the overview into buttons that open the story
  const renderWithRefs = (text) =>
    (text || '').split(/(\[\d+\])/g).map((part, i) => {
      const m = part.match(/^\[(\d+)\]$/);
      if (m && storyByRef[Number(m[1])]) {
        const s = storyByRef[Number(m[1])];
        return (
          <button key={i} type="button" className="cite-btn" title={s.title} onClick={() => onOpenArticleById?.(s.id)}>
            {m[1]}
          </button>
        );
      }
      return <React.Fragment key={i}>{part}</React.Fragment>;
    });

  return (
    <section className="briefing" aria-label="AI daily briefing">
      <div className="briefing-head">
        <div>
          <span className="briefing-kicker">Your briefing{category ? ` on ${category}` : ''}</span>
          <h2 className="briefing-headline">{loading && !data ? 'Preparing today’s briefing…' : data.headline}</h2>
        </div>
        <div className="briefing-actions">
          <button type="button" className="btn-action-ghost" onClick={() => load(true)} disabled={loading}>
            {loading ? 'Updating…' : 'Refresh'}
          </button>
          <button type="button" className="btn-action-ghost" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            {open ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>
      {open && data && (
        <div className="briefing-body">
          <p className="briefing-overview">{renderWithRefs(data.overview)}</p>
          {data.highlights?.length > 0 && (
            <ul className="briefing-highlights">
              {data.highlights.map((h, i) => (
                <li key={i}>
                  {h.ref && storyByRef[h.ref] ? (
                    <button type="button" className="briefing-link" onClick={() => onOpenArticleById?.(storyByRef[h.ref].id)}>
                      {h.text}
                    </button>
                  ) : (
                    h.text
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="briefing-meta">
            {data.generated_by === 'groq-llm' ? 'Written by the Groq LLM from the top-ranked stories' : 'Assembled from the top-ranked stories'}
            {' '}— updated {new Date(data.generated_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
          </p>
        </div>
      )}
    </section>
  );
}

export default BriefingCard;
