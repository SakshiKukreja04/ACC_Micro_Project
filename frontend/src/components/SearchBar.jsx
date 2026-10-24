import React from 'react';

export function SearchBar({ value, onChange, onSubmit, onClear }) {
  return (
    <form className="search-box-wrapper" onSubmit={onSubmit} role="search">
      <span className="search-icon" aria-hidden="true">🔍</span>
      <input
        type="text"
        className="search-input"
        placeholder="Search keywords across headlines & content..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Search articles"
      />
      {value && (
        <button
          type="button"
          className="search-clear-btn"
          onClick={onClear}
          aria-label="Clear search query"
        >
          ✕
        </button>
      )}
    </form>
  );
}

export default SearchBar;
