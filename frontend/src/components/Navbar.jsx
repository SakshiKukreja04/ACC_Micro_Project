import React from 'react';

export function Navbar({ activeTab, onSelectTab, isHealthy, theme, onToggleTheme }) {
  return (
    <header className="navbar" role="banner">
      <div className="brand-wrapper">
        <div className="brand-logo" aria-hidden="true">
          <span className="logo-letter">N</span>
        </div>
        <div>
          <div className="brand-title">Nexus Newsroom</div>
          <div className="brand-subtitle">Curated Feeds • Groq AI Summaries • FAISS Vectors</div>
        </div>
      </div>

      <nav className="nav-tabs" role="navigation" aria-label="Main Sections">
        <button
          className={`nav-tab-btn ${activeTab === 'feed' ? 'active' : ''}`}
          onClick={() => onSelectTab('feed')}
          id="tab-feed"
        >
          Top Stories
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'trending' ? 'active' : ''}`}
          onClick={() => onSelectTab('trending')}
          id="tab-trending"
        >
          Trending
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'semantic' ? 'active' : ''}`}
          onClick={() => onSelectTab('semantic')}
          id="tab-semantic"
        >
          Semantic Discovery
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
          onClick={() => onSelectTab('chat')}
          id="tab-chat"
        >
          Ask News AI
        </button>
        <button
          className={`nav-tab-btn ${activeTab === 'cloud' ? 'active' : ''}`}
          onClick={() => onSelectTab('cloud')}
          id="tab-cloud"
        >
          Architecture
        </button>
      </nav>

      <div className="nav-actions">
        {/* Theme Toggle Button */}
        <button
          className="theme-toggle-btn"
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
          aria-label={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} mode`}
        >
          {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
        </button>

        {/* Status Pill */}
        <div className={`pulse-indicator ${isHealthy ? 'status-online' : 'status-offline'}`}>
          <span className="pulse-dot"></span>
          <span>{isHealthy ? 'Supabase Live' : 'API Connecting'}</span>
        </div>
      </div>
    </header>
  );
}

export default Navbar;
