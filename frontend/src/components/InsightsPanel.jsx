import React, { useEffect, useState } from 'react';
import apiService from '../services/api';
import { BarList, ColumnChart, SentimentBar } from './charts';

const WINDOWS = [
  { hours: 24, label: '24 hours' },
  { hours: 48, label: '2 days' },
  { hours: 168, label: '7 days' },
];

export function InsightsPanel({ onPickCategory, onOpenArticleById }) {
  const [hours, setHours] = useState(48);
  const [overview, setOverview] = useState(null);
  const [topics, setTopics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([apiService.getInsights(hours), apiService.getTopics(Math.round(hours / 2))])
      .then(([o, t]) => {
        setOverview(o);
        setTopics(t);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [hours]);

  const totals = overview?.totals;
  const volume = (overview?.volume_by_hour || []).map((v) => ({
    label: new Date(v.hour).toLocaleTimeString([], { hour: 'numeric' }),
    value: v.count,
  }));

  return (
    <div>
      <header className="hero-section insights-hero">
        <div>
          <h1 className="hero-title">What the news is about</h1>
          <p className="hero-subtitle">Topics that are suddenly being covered, how each outlet sounds, and where coverage is concentrated.</p>
        </div>
        <div className="segmented" role="group" aria-label="Time window">
          {WINDOWS.map((w) => (
            <button key={w.hours} type="button" className={hours === w.hours ? 'active' : ''} aria-pressed={hours === w.hours} onClick={() => setHours(w.hours)}>
              {w.label}
            </button>
          ))}
        </div>
      </header>

      {error && <div className="error-banner" role="alert">{error}</div>}
      {loading && !overview ? (
        <div className="explainer-loading">Analysing the collection…</div>
      ) : overview && (
        <>
          <dl className="totals-strip">
            <div><dt>Stories</dt><dd>{totals.articles}</dd></div>
            <div><dt>Summarised</dt><dd>{totals.summarized}</dd></div>
            <div><dt>Publishers</dt><dd>{totals.sources}</dd></div>
            <div><dt>Multi-outlet stories</dt><dd>{totals.story_clusters}</dd></div>
            <div><dt>Avg. grounding</dt><dd>{totals.avg_grounding_score != null ? `${Math.round(totals.avg_grounding_score * 100)}%` : '—'}</dd></div>
          </dl>

          <div className="insights-grid">
            <section className="panel panel-wide">
              <div className="panel-head">
                <h2>Rising topics</h2>
                <p>Keywords appearing far more in the last {Math.round(hours / 2)} hours than in the {Math.round(hours / 2)} hours before.</p>
              </div>
              {topics?.topics?.length ? (
                <ol className="topic-list">
                  {topics.topics.slice(0, 12).map((t) => (
                    <li key={t.topic}>
                      <div className="topic-main">
                        <span className="topic-name">{t.topic}</span>
                        {t.is_new ? <span className="topic-new">new</span> : t.growth !== null && <span className="topic-growth">{t.growth > 0 ? '+' : ''}{Math.round(t.growth * 100)}%</span>}
                      </div>
                      <div className="topic-meta">
                        {t.mentions} stories from {t.source_count} outlet{t.source_count === 1 ? '' : 's'}{t.category ? ` in ${t.category}` : ''}
                      </div>
                      {t.examples?.[0] && (
                        <button type="button" className="topic-example" onClick={() => onOpenArticleById?.(t.examples[0].id)}>
                          {t.examples[0].title}
                        </button>
                      )}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="empty-subtext">Not enough new coverage in this window to detect rising topics.</p>
              )}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Coverage by category</h2>
                <p>Select a category to open its feed.</p>
              </div>
              <BarList
                items={overview.category_distribution.map((c) => ({ label: c.category, value: c.count }))}
                onSelect={(item) => onPickCategory?.(item.label)}
              />
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Tone by publisher</h2>
                <p>Share of positive, neutral and negative stories.</p>
              </div>
              <ul className="tone-list">
                {overview.sentiment_by_source.slice(0, 10).map((s) => (
                  <li key={s.source}>
                    <span className="tone-source">{s.source}</span>
                    <SentimentBar positive={s.positive} neutral={s.neutral} negative={s.negative} />
                    <span className={`tone-score ${s.avg_score >= 0 ? 'pos' : 'neg'}`}>{s.avg_score > 0 ? '+' : ''}{s.avg_score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
              <div className="tone-legend">
                <span><i className="seg-positive" /> Positive</span>
                <span><i className="seg-neutral" /> Neutral</span>
                <span><i className="seg-negative" /> Negative</span>
              </div>
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Stories published per hour</h2>
                <p>Last {overview.window_hours} hours.</p>
              </div>
              <ColumnChart items={volume} labelEvery={Math.max(1, Math.round(volume.length / 8))} />
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Tone by category</h2>
              </div>
              <ul className="tone-list">
                {overview.sentiment_by_category.map((s) => (
                  <li key={s.category}>
                    <span className="tone-source">{s.category}</span>
                    <SentimentBar positive={s.positive} neutral={s.neutral} negative={s.negative} />
                    <span className={`tone-score ${s.avg_score >= 0 ? 'pos' : 'neg'}`}>{s.avg_score > 0 ? '+' : ''}{s.avg_score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </div>
  );
}

export default InsightsPanel;
