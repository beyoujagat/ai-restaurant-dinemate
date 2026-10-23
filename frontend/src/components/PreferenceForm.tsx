import React from 'react';
import type { MetaOptions, RecommendationRequest } from '../api/client';

interface PreferenceFormProps {
  metaOptions: MetaOptions | null;
  metaLoading: boolean;
  preferences: RecommendationRequest;
  onChange: (updated: RecommendationRequest) => void;
  onSubmit: () => void;
  isLoading: boolean;
  validationMessage?: string | null;
}

export const PreferenceForm: React.FC<PreferenceFormProps> = ({
  metaOptions,
  metaLoading,
  preferences,
  onChange,
  onSubmit,
  isLoading,
  validationMessage,
}) => {
  const budgetOptions: Array<{ id: 'low' | 'medium' | 'high'; label: string; hint: string }> = [
    {
      id: 'low',
      label: 'Budget Friendly',
      hint: metaOptions?.budget_labels.low || '≤ ₹400 for two',
    },
    {
      id: 'medium',
      label: 'Casual Dining',
      hint: metaOptions?.budget_labels.medium || '₹401–₹800 for two',
    },
    {
      id: 'high',
      label: 'Fine Dining / Premium',
      hint: metaOptions?.budget_labels.high || '≥ ₹801 for two',
    },
  ];

  const ratingOptions = [
    { value: null, label: 'Any Rating' },
    { value: 3.5, label: '3.5+ ★' },
    { value: 4.0, label: '4.0+ ★ (Recommended)' },
    { value: 4.5, label: '4.5+ ★ (Exceptional)' },
  ];

  const handleLocationChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...preferences, location: e.target.value });
  };

  const handleBudgetChange = (b: 'low' | 'medium' | 'high') => {
    onChange({ ...preferences, budget: b });
  };

  const handleCuisineChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange({ ...preferences, cuisine: e.target.value });
  };

  const handleRatingChange = (r: number | null) => {
    onChange({ ...preferences, min_rating: r });
  };

  const handleExtrasChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...preferences, extras: e.target.value });
  };

  return (
    <div className="preference-form-card" id="preference-form">
      <div className="form-title-bar">
        <div className="form-title-group">
          <span className="form-step-pill">Curate Your Table</span>
          <h2 className="form-main-heading">Dining Preferences</h2>
        </div>
        <span className="form-catalog-pill">
          {metaLoading ? 'Loading facets...' : `📍 ${metaOptions?.locations.length || 0} Neighborhoods`}
        </span>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="preference-form-fields"
      >
        {/* Neighborhood Selection */}
        <div className="form-field-group">
          <label htmlFor="pref-location" className="form-field-label">
            <span className="label-icon">📍</span>
            <span>Bangalore Neighborhood</span>
          </label>
          <div className="select-wrapper">
            <select
              id="pref-location"
              className="form-select-control"
              value={preferences.location}
              onChange={handleLocationChange}
              disabled={metaLoading || isLoading}
            >
              <option value="" disabled>
                -- Select a Bangalore Neighborhood --
              </option>
              {metaOptions?.locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
          <p className="field-hint">Filtered from verified Zomato Bangalore neighborhood records</p>
        </div>

        {/* Budget Band Radio Pills */}
        <div className="form-field-group">
          <label className="form-field-label">
            <span className="label-icon">💰</span>
            <span>Cost for Two (INR)</span>
          </label>
          <div className="budget-pill-group">
            {budgetOptions.map((b) => {
              const isSelected = Boolean(preferences.budget && preferences.budget === b.id);
              return (
                <button
                  key={b.id}
                  type="button"
                  className={`budget-pill-btn ${isSelected ? 'budget-selected' : ''}`}
                  onClick={() => handleBudgetChange(b.id)}
                  disabled={isLoading}
                  id={`btn-budget-${b.id}`}
                >
                  <span className="budget-pill-title">{b.label}</span>
                  <span className="budget-pill-hint">{b.hint}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Cuisine and Rating Grid */}
        <div className="form-two-col-grid">
          {/* Cuisine Dropdown */}
          <div className="form-field-group">
            <label htmlFor="pref-cuisine" className="form-field-label">
              <span className="label-icon">🍲</span>
              <span>Cuisine / Food Style</span>
            </label>
            <div className="select-wrapper">
              <select
                id="pref-cuisine"
                className="form-select-control"
                value={preferences.cuisine}
                onChange={handleCuisineChange}
                disabled={metaLoading || isLoading}
              >
                <option value="">All Cuisines (Any)</option>
                {preferences.cuisine &&
                  metaOptions?.cuisines &&
                  !metaOptions.cuisines.includes(preferences.cuisine) && (
                    <option value={preferences.cuisine}>{preferences.cuisine}</option>
                  )}
                {metaOptions?.cuisines.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Min Rating Selection */}
          <div className="form-field-group">
            <label className="form-field-label">
              <span className="label-icon">⭐</span>
              <span>Minimum Rating</span>
            </label>
            <div className="rating-pill-group">
              {ratingOptions.map((r, idx) => {
                const isSelected = preferences.min_rating !== undefined && preferences.min_rating === r.value;
                return (
                  <button
                    key={idx}
                    type="button"
                    className={`rating-pill-btn ${isSelected ? 'rating-selected' : ''}`}
                    onClick={() => handleRatingChange(r.value)}
                    disabled={isLoading}
                    id={`btn-rating-${idx}`}
                  >
                    {r.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Cravings & Ambiance Free Text */}
        <div className="form-field-group">
          <label htmlFor="pref-extras" className="form-field-label">
            <span className="label-icon">✨</span>
            <span>Special Cravings or Ambiance (Optional)</span>
          </label>
          <div className="input-text-wrapper">
            <input
              id="pref-extras"
              type="text"
              className="form-input-control"
              placeholder="e.g. outdoor seating, craft beer, rooftop, family dinner, quiet corner..."
              value={preferences.extras || ''}
              onChange={handleExtrasChange}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Validation message if required preferences are missing */}
        {validationMessage && (
          <div className="form-validation-alert" role="alert" id="form-validation-error">
            <span className="validation-alert-icon">⚠️</span>
            <span className="validation-alert-text">{validationMessage}</span>
          </div>
        )}

        {/* Action Button */}
        <div className="form-submit-row">
          <button
            type="submit"
            className="btn-submit-search"
            disabled={isLoading}
            id="btn-find-restaurants"
          >
            {isLoading ? (
              <>
                <span className="btn-spinner" />
                <span>Consulting AI Food Concierge...</span>
              </>
            ) : (
              <>
                <span className="btn-sparkle">✨</span>
                <span>Find My Perfect Spots</span>
                <span className="btn-arrow">→</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
