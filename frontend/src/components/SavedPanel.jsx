import React, { useEffect, useState } from 'react';
import apiService from '../services/api';
import NewsCard from './NewsCard';
import { formatAge } from './ui';

/** Reading list (bookmarks) + reading history + privacy control. */
export function SavedPanel({ onOpenDetail, onSummaryGenerated, bookmarkIds, onToggleBookmark, onForgotten }) {
  const [saved, setSaved] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState(null);

  const load = () => {
    setLoading(true);
    Promise.all([apiService.getBookmarks().catch(() => []), apiService.getHistory(15).catch(() => [])])
      .then(([b, h]) => {
        setSaved(b);
        setHistory(h);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [bookmarkIds.size]);

  const forget = async () => {
    const res = await apiService.forgetMe();
    setConfirming(false);
    setMessage(`Erased ${res.deleted_bookmarks} saved stories and ${res.deleted_events} history entries.`);
    onForgotten?.();
    load();
  };

  return (
    <div>
      <header className="hero-section">
        <h1 className="hero-title">Saved stories</h1>
        <p className="hero-subtitle">Your reading list and recent history, stored against an anonymous ID on this browser.</p>
      </header>

      {loading ? (
        <div className="explainer-loading">Loading your reading list…</div>
      ) : saved.length === 0 ? (
        <div className="notice-card">
          Nothing saved yet. Use <strong>Save</strong> on any story to keep it here.
        </div>
      ) : (
        <div className="news-grid">
          {saved.map((art) => (
            <NewsCard
              key={art.id}
              article={art}
              onOpenDetail={onOpenDetail}
              onOpenRelated={onOpenDetail}
              onSummaryGenerated={onSummaryGenerated}
              isSaved={bookmarkIds.has(art.id)}
              onToggleBookmark={onToggleBookmark}
            />
          ))}
        </div>
      )}

      <section className="history-section">
        <h2 className="section-heading">Recently read</h2>
        {history.length === 0 ? (
          <p className="empty-subtext">Stories you open will appear here.</p>
        ) : (
          <ol className="history-list">
            {history.map((a) => (
              <li key={a.id}>
                <button type="button" className="title-link-btn" onClick={() => onOpenDetail(a)}>{a.title}</button>
                <span className="history-meta">{a.source_name} — published {formatAge(a.published_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="privacy-box">
        <div>
          <h3>Your data</h3>
          <p>Erase every saved story and history entry linked to this browser. Recommendations reset to trending.</p>
          {message && <p className="privacy-done" role="status">{message}</p>}
        </div>
        {confirming ? (
          <div className="privacy-actions">
            <button type="button" className="btn-danger" onClick={forget}>Erase my data</button>
            <button type="button" className="btn-secondary" onClick={() => setConfirming(false)}>Keep it</button>
          </div>
        ) : (
          <button type="button" className="btn-secondary" onClick={() => setConfirming(true)}>Erase my data…</button>
        )}
      </section>
    </div>
  );
}

export default SavedPanel;
