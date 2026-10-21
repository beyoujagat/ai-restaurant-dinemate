import React from 'react';

export interface CategoryOption {
  id: string;
  name: string;
  icon: string;
  cuisineKeyword: string;
}

const POPULAR_CATEGORIES: CategoryOption[] = [
  { id: 'all', name: 'All Cuisines', icon: '🍽️', cuisineKeyword: '' },
  { id: 'biryani', name: 'Dum Biryani', icon: '🍛', cuisineKeyword: 'Biryani' },
  { id: 'north_indian', name: 'North Indian', icon: '🍲', cuisineKeyword: 'North Indian' },
  { id: 'south_indian', name: 'South Indian', icon: '🍱', cuisineKeyword: 'South Indian' },
  { id: 'cafe', name: 'Cozy Cafes', icon: '☕', cuisineKeyword: 'Cafe' },
  { id: 'pizza', name: 'Pizza & Italian', icon: '🍕', cuisineKeyword: 'Pizza' },
  { id: 'chinese', name: 'Asian / Chinese', icon: '🥢', cuisineKeyword: 'Chinese' },
  { id: 'healthy', name: 'Healthy Bowls', icon: '🥗', cuisineKeyword: 'Healthy Food' },
  { id: 'burgers', name: 'Burgers & Fries', icon: '🍔', cuisineKeyword: 'Burger' },
  { id: 'desserts', name: 'Desserts & Bakes', icon: '🍰', cuisineKeyword: 'Desserts' },
];

interface CategoryChipsProps {
  selectedCuisine: string;
  onSelectCategory: (cuisineKeyword: string) => void;
}

export const CategoryChips: React.FC<CategoryChipsProps> = ({
  selectedCuisine,
  onSelectCategory,
}) => {
  return (
    <div className="category-chips-section">
      <div className="section-title-row">
        <div>
          <h3 className="section-title">Popular Bangalore Cravings</h3>
          <p className="section-subtitle">Quickly filter by iconic city favorites</p>
        </div>
        <span className="category-hint-badge">⚡ 1-Click Fast Filter</span>
      </div>

      <div className="category-chips-scroll">
        {POPULAR_CATEGORIES.map((cat) => {
          // Exact match check to ensure one specific chip is active at a time
          const isSelected =
            cat.cuisineKeyword === ''
              ? !selectedCuisine
              : selectedCuisine.trim().toLowerCase() === cat.cuisineKeyword.toLowerCase();

          return (
            <button
              key={cat.id}
              type="button"
              className={`category-chip-card ${isSelected ? 'chip-active' : ''}`}
              onClick={() => onSelectCategory(cat.cuisineKeyword)}
              id={`cat-chip-${cat.id}`}
              aria-pressed={isSelected}
            >
              <div className="chip-icon-circle">
                <span className="chip-icon">{cat.icon}</span>
              </div>
              <span className="chip-label">{cat.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
