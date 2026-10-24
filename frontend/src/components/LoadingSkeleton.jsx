import React from 'react';

export function LoadingSkeleton({ count = 6 }) {
  return (
    <div className="news-grid" aria-label="Loading news articles">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="news-card skeleton-card">
          <div className="skeleton-line skeleton-meta"></div>
          <div className="skeleton-line skeleton-title"></div>
          <div className="skeleton-line skeleton-title" style={{ width: '70%' }}></div>
          <div className="skeleton-line skeleton-text" style={{ marginTop: '14px' }}></div>
          <div className="skeleton-line skeleton-text" style={{ width: '90%' }}></div>
          <div className="skeleton-box" style={{ marginTop: '16px', height: '64px' }}></div>
          <div className="skeleton-actions" style={{ marginTop: '20px' }}>
            <div className="skeleton-btn"></div>
            <div className="skeleton-btn"></div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default LoadingSkeleton;
