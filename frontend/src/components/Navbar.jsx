import React from 'react';

export const TABS = [
  { id: 'feed', label: 'Top stories' },
  { id: 'foryou', label: 'For you' },
  { id: 'trending', label: 'Trending' },
  { id: 'semantic', label: 'Discover' },
  { id: 'chat', label: 'Ask AI' },
  { id: 'insights', label: 'Insights' },
  { id: 'saved', label: 'Saved' },
  { id: 'monitor', label: 'System' },
];

export function Navbar({ activeTab, onSelectTab, isHealthy, isLive, savedCount, theme, onToggleTheme }) {
  return (
    <header className="navbar" role="banner">
      <div className="brand-wrapper">
        <div className="brand-logo" aria-hidden="true">
          <span className="logo-letter">N</span>
        </div>
        <div>
          <div className="brand-title">Nexus Newsroom</div>
          <div className="brand-subtitle">Every source, summarised and compared</div>
        </div>
      </div>

      <nav className="nav-tabs" aria-label="Main sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`nav-tab-btn ${activeTab === t.id ? 'active' : ''}`}
            onClick={() => onSelectTab(t.id)}
            aria-current={activeTab === t.id ? 'page' : undefined}
            id={`tab-${t.id}`}
          >
            {t.label}
            {t.id === 'saved' && savedCount > 0 && <span className="nav-count">{savedCount}</span>}
          </button>
        ))}
      </nav>

      <div className="nav-actions">
        <button
          className="theme-toggle-btn"
          onClick={onToggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
        </button>

        <button
          type="button"
          className={`pulse-indicator ${isHealthy ? 'status-online' : 'status-offline'}`}
          onClick={() => onSelectTab('monitor')}
          title="Open the system monitor"
        >
          <span className="pulse-dot"></span>
          <span>{!isHealthy ? 'API offline' : isLive ? 'Live' : 'Connected'}</span>
        </button>
      </div>
    </header>
  );
}

export default Navbar;
