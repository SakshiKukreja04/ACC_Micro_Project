import React from 'react';

/** Real-time notification pushed over Server-Sent Events when the collector stores new stories. */
export function LiveToast({ event, onRefresh, onDismiss }) {
  if (!event) return null;
  const first = event.latest?.[0];
  return (
    <div className="live-toast" role="status" aria-live="polite">
      <span className="live-toast-dot" aria-hidden="true" />
      <div className="live-toast-body">
        <strong>{event.new_count} new {event.new_count === 1 ? 'story' : 'stories'}</strong>
        {first && <span className="live-toast-title">{first.source_name}: {first.title}</span>}
      </div>
      <button type="button" className="btn-primary" onClick={onRefresh}>Show</button>
      <button type="button" className="live-toast-close" onClick={onDismiss} aria-label="Dismiss">✕</button>
    </div>
  );
}

export default LiveToast;
