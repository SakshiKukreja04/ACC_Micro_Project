import React from 'react';

export function CategoryFilter({ categories, selectedCategory, onSelectCategory }) {
  return (
    <div className="categories-pills" role="tablist" aria-label="Filter news by category">
      {categories.map((cat) => {
        const name = typeof cat === 'string' ? cat : cat.category;
        const count = typeof cat === 'object' && cat.article_count !== undefined ? cat.article_count : null;
        const isActive = (selectedCategory === name) || (!selectedCategory && name === 'All');

        return (
          <button
            key={name}
            className={`pill-btn ${isActive ? 'active' : ''}`}
            onClick={() => onSelectCategory(name === 'All' ? '' : name)}
            role="tab"
            aria-selected={isActive}
          >
            {name}
            {count !== null && <span className="category-count">({count})</span>}
          </button>
        );
      })}
    </div>
  );
}

export default CategoryFilter;
