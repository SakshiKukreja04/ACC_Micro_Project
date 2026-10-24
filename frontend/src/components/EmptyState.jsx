import React from 'react';

export function EmptyState({ message, onReset }) {
  return (
    <div className="empty-state-box">
      <div className="empty-icon">📰</div>
      <h3 className="empty-title">No Articles Found</h3>
      <p className="empty-desc">
        {message || 'We could not find any news articles matching your search query or selected category.'}
      </p>
      {onReset && (
        <button className="btn-primary" onClick={onReset} style={{ marginTop: '16px' }}>
          Reset Filters & Show All
        </button>
      )}
    </div>
  );
}

export default EmptyState;
