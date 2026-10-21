import React from 'react';

interface EmptyStateProps {
  location: string;
  cuisine: string;
  budget: string;
  onResetFilters: () => void;
  onWidenBudget: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  location,
  cuisine,
  budget,
  onResetFilters,
  onWidenBudget,
}) => {
  return (
    <div className="empty-state-card" id="empty-state-container">
      <div className="empty-graphic">
        <span className="empty-icon">🍽️</span>
        <span className="empty-badge">0 Matches</span>
      </div>

      <h3 className="empty-headline">No Tables Matched All Strict Filters</h3>
      <p className="empty-desc">
        We searched the Bangalore catalog for{' '}
        <strong>{cuisine || 'any cuisine'}</strong> in <strong>{location}</strong> with a{' '}
        <strong>{budget} budget</strong>, but couldn't find a spot that satisfies all criteria simultaneously.
      </p>

      <div className="empty-tips-box">
        <h4 className="tips-title">💡 Quick Ways to Discover Great Food:</h4>
        <ul className="tips-list">
          <li>Widen your budget to medium or high for more diverse dining formats.</li>
          <li>Select "All Cuisines" to explore top-rated local cafes and eateries in {location}.</li>
          <li>Try nearby foodie hubs like <strong>Koramangala</strong>, <strong>Indiranagar</strong>, or <strong>Jayanagar</strong>.</li>
        </ul>
      </div>

      <div className="empty-actions">
        <button
          type="button"
          className="btn-empty-action btn-empty-primary"
          onClick={onWidenBudget}
        >
          <span>Widen Budget to Medium/High</span>
        </button>
        <button
          type="button"
          className="btn-empty-action btn-empty-secondary"
          onClick={onResetFilters}
        >
          <span>Reset Filters &amp; Explore All</span>
        </button>
      </div>
    </div>
  );
};
