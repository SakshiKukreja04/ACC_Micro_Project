import React, { useEffect, useState } from 'react';
import apiService from '../services/api';
import { SentimentMark, formatAge } from './ui';

/**
 * Perspective Lens — how different publishers cover the same story.
 * Outlets are placed on a single tone scale (negative → positive), then shown side by side
 * with what each one emphasises, followed by the shared facts and a neutral synthesis.
 */
export function PerspectiveLens({ articleId, onOpenArticle }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    apiService
      .getPerspectives(articleId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    apiService.recordEvent(articleId, 'perspective');
    return () => {
      alive = false;
    };
  }, [articleId]);

  if (loading) return <div className="explainer-loading">Finding other outlets that covered this story…</div>;
  if (error) return <div className="lens-note">Couldn't compare coverage: {error}</div>;
  if (!data) return null;

  if (!data.available) {
    return <div className="lens-note">{data.message}</div>;
  }

  const { outlets, analysis } = data;
  const angleFor = (source) => analysis?.differences?.find((d) => d.source === source)?.angle;

  return (
    <div className="lens">
      <div className="lens-scale" role="img" aria-label="Tone of each outlet from negative to positive">
        <div className="lens-scale-track">
          <span className="lens-scale-mid" />
          {outlets.map((o, i) => {
            const left = ((Math.max(-1, Math.min(1, o.sentiment_score)) + 1) / 2) * 100;
            return (
              <span
                key={o.article_id}
                className={`lens-marker sentiment-${o.sentiment}`}
                style={{ left: `${left}%`, '--stack': i % 2 ? 1 : 0 }}
                title={`${o.source_name}: ${o.sentiment_score > 0 ? '+' : ''}${o.sentiment_score}`}
              >
                <span className="lens-marker-label">{o.source_name.replace(/^Demo /, '')}</span>
              </span>
            );
          })}
        </div>
        <div className="lens-scale-ends">
          <span>More critical</span>
          <span>More upbeat</span>
        </div>
      </div>

      <div className="lens-stats">
        <div>
          <strong>{Math.round(data.coverage_agreement_index * 100)}%</strong>
          <span>vocabulary shared across outlets</span>
        </div>
        <div>
          <strong>{data.tone_spread.toFixed(2)}</strong>
          <span>tone gap between outlets (0–2)</span>
        </div>
        <div>
          <strong>{outlets.length}</strong>
          <span>publishers compared</span>
        </div>
      </div>

      <div className="lens-columns" style={{ '--cols': Math.min(outlets.length, 3) }}>
        {outlets.map((o) => (
          <article key={o.article_id} className="lens-outlet">
            <header>
              <span className="lens-outlet-name">{o.source_name}</span>
              <SentimentMark sentiment={o.sentiment} score={o.sentiment_score} />
            </header>
            <button type="button" className="lens-outlet-title" onClick={() => onOpenArticle?.(o.article_id)}>
              {o.title}
            </button>
            <p className="lens-outlet-lead">{o.lead}</p>
            {angleFor(o.source_name) && <p className="lens-outlet-angle">{angleFor(o.source_name)}</p>}
            {o.distinct_focus?.length > 0 && (
              <div className="lens-focus">
                <span>Only here:</span>
                {o.distinct_focus.map((k) => (
                  <span key={k} className="lens-chip">{k}</span>
                ))}
              </div>
            )}
            <footer>{formatAge(o.published_at)}</footer>
          </article>
        ))}
      </div>

      {analysis?.consensus?.length > 0 && (
        <div className="lens-consensus">
          <h5>What the outlets agree on</h5>
          <ul>
            {analysis.consensus.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {analysis?.framing_note && <p className="lens-framing">{analysis.framing_note}</p>}
      {analysis?.neutral_synthesis && (
        <div className="lens-synthesis">
          <h5>Balanced account</h5>
          <p>{analysis.neutral_synthesis}</p>
        </div>
      )}
      <p className="lens-provenance">
        {analysis?.generated_by === 'groq-llm'
          ? 'Comparison written by the Groq LLM from the articles above only.'
          : 'Comparison computed from shared and distinctive keywords. Add a Groq API key for a written analysis.'}
      </p>
    </div>
  );
}

export function StoryTimeline({ articleId, onOpenArticle }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    apiService
      .getTimeline(articleId)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [articleId]);

  if (loading) return <div className="explainer-loading">Ordering related coverage by publication time…</div>;
  if (!data || data.events.length <= 1) {
    return <div className="lens-note">No earlier or later coverage of this story has been collected yet.</div>;
  }

  return (
    <div className="timeline">
      <p className="timeline-summary">
        First reported by <strong>{data.first_reported_by}</strong>
        {data.span_hours ? <> and followed by {data.sources.length - 1} more outlet{data.sources.length > 2 ? 's' : ''} over {data.span_hours} hours.</> : '.'}
      </p>
      <ol className="timeline-list">
        {data.events.map((e) => (
          <li key={e.article_id} className={e.is_current ? 'is-current' : ''}>
            <time dateTime={e.published_at}>
              {e.published_at ? new Date(e.published_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'}
            </time>
            <div>
              <span className="timeline-source">{e.source_name}</span>
              <SentimentMark sentiment={e.sentiment} compact />
              {e.is_current ? (
                <span className="timeline-title">{e.title} <em>(this story)</em></span>
              ) : (
                <button type="button" className="timeline-title" onClick={() => onOpenArticle?.(e.article_id)}>
                  {e.title}
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default PerspectiveLens;
