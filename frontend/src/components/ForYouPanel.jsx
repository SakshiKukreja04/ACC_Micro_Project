import React, { useEffect, useState } from 'react';
import apiService from '../services/api';
import NewsCard from './NewsCard';
import LoadingSkeleton from './LoadingSkeleton';

/** Personalised feed built from the reader's own history — explained story by story. */
export function ForYouPanel({ onOpenDetail, onSummaryGenerated, bookmarkIds, onToggleBookmark, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiService
      .getForYou(12)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [refreshKey]);

  return (
    <div>
      <header className="hero-section">
        <h1 className="hero-title">Picked for you</h1>
        <p className="hero-subtitle">
          Built from the stories you open, listen to and save — on this device only. No account, and you can erase it any time from Saved.
        </p>
      </header>

      {data?.personalized && data.profile?.top_categories?.length > 0 && (
        <div className="interest-strip" aria-label="Your interests">
          <span className="interest-label">You read most about</span>
          {data.profile.top_categories.map((c) => (
            <span key={c.category} className="interest-chip">
              {c.category}
              <span className="interest-share" style={{ width: `${Math.max(8, c.share * 60)}px` }} />
              {Math.round(c.share * 100)}%
            </span>
          ))}
        </div>
      )}

      {data && !data.personalized && (
        <div className="notice-card">
          <strong>Your feed learns as you read.</strong> Open a few stories from Top Stories and this page will start
          recommending similar ones. Until then, here is what’s trending.
        </div>
      )}

      {error && <div className="error-banner" role="alert">{error}</div>}

      {loading ? (
        <LoadingSkeleton count={6} />
      ) : data?.items?.length ? (
        <div className="news-grid">
          {data.items.map((art) => (
            <NewsCard
              key={art.id}
              article={art}
              reason={art.reason}
              onOpenDetail={onOpenDetail}
              onOpenRelated={onOpenDetail}
              onSummaryGenerated={onSummaryGenerated}
              isSaved={bookmarkIds.has(art.id)}
              onToggleBookmark={onToggleBookmark}
            />
          ))}
        </div>
      ) : (
        !error && <div className="notice-card">You’ve read everything similar to your interests. Check Top Stories for new coverage.</div>
      )}
    </div>
  );
}

export default ForYouPanel;
