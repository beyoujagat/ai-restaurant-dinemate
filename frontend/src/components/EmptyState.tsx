import React, { useEffect, useState } from 'react';
import { fetchNearbyNeighbourhoods } from '../api/client';
import type { NearbyNeighbourhoodItem, NearbyResponse } from '../api/client';

export interface EmptyStateProps {
  location: string;
  cuisine: string;
  budget: 'low' | 'medium' | 'high' | string;
  onResetFilters: () => void;
  onWidenBudget: (targetBudget?: 'medium' | 'high' | '') => void;
  onSelectLocation?: (location: string) => void;
  onSearchNearby?: () => void;
  onClearCuisine?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  location,
  cuisine,
  budget,
  onResetFilters,
  onWidenBudget,
  onSearchNearby,
}) => {
  const [nearbyData, setNearbyData] = useState<NearbyResponse | null>(null);
  const [fetchedLocation, setFetchedLocation] = useState<string | null>(null);
  const [radiusKm, setRadiusKm] = useState<5 | 10>(5);

  const trimmedLoc = location?.trim();
  const loadingNearby = Boolean(trimmedLoc) && fetchedLocation !== trimmedLoc;

  useEffect(() => {
    let isMounted = true;
    if (!trimmedLoc) {
      return;
    }

    fetchNearbyNeighbourhoods(trimmedLoc)
      .then((data) => {
        if (!isMounted) return;
        setNearbyData(data);
        setFetchedLocation(trimmedLoc);
        if (data.nearby_5km && data.nearby_5km.length > 0) {
          setRadiusKm(5);
        } else if (data.nearby_10km && data.nearby_10km.length > 0) {
          setRadiusKm(10);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setNearbyData(null);
        setFetchedLocation(trimmedLoc);
      });

    return () => {
      isMounted = false;
    };
  }, [trimmedLoc]);

  const activeNearbyList: NearbyNeighbourhoodItem[] =
    radiusKm === 5
      ? nearbyData?.nearby_5km || []
      : nearbyData?.nearby_10km || [];

  const has5km = Boolean(nearbyData?.nearby_5km && nearbyData.nearby_5km.length > 0);
  const has10km = Boolean(nearbyData?.nearby_10km && nearbyData.nearby_10km.length > 0);
  const hasEligibleNearby = Boolean(!loadingNearby && nearbyData?.nearby_10km && nearbyData.nearby_10km.length > 0);

  const getBudgetLabel = () => {
    if (budget === 'low') return 'Budget Friendly (≤ ₹400 for two)';
    if (budget === 'medium') return 'Casual Dining (₹401–₹800 for two)';
    if (budget === 'high') return 'Fine Dining / Premium (≥ ₹801 for two)';
    return 'selected budget';
  };

  // Render dynamic primary action button based on budget level
  const renderPrimaryActionButton = () => {
    if (budget === 'low') {
      return (
        <button
          type="button"
          className="btn-empty-action btn-empty-primary"
          id="btn-widen-budget-low"
          onClick={() => onWidenBudget('medium')}
        >
          <span>Widen Budget to Medium/High</span>
        </button>
      );
    }

    if (budget === 'medium') {
      return (
        <button
          type="button"
          className="btn-empty-action btn-empty-primary"
          id="btn-widen-budget-medium"
          onClick={() => onWidenBudget('high')}
        >
          <span>Widen Budget to High</span>
        </button>
      );
    }

    if (budget === 'high') {
      return (
        <button
          type="button"
          className="btn-empty-action btn-empty-primary"
          id="btn-explore-all-budgets"
          onClick={() => onWidenBudget('')}
        >
          <span>Explore All Budgets</span>
        </button>
      );
    }

    // Default when budget is not specified
    return (
      <button
        type="button"
        className="btn-empty-action btn-empty-primary"
        id="btn-widen-budget-default"
        onClick={() => onWidenBudget('medium')}
      >
        <span>Widen Budget to Medium/High</span>
      </button>
    );
  };

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
        <strong>{getBudgetLabel()}</strong>, but couldn&apos;t find a spot that satisfies all criteria simultaneously.
      </p>

      <div className="empty-tips-box">
        <h4 className="tips-title">💡 Quick Ways to Discover Great Food:</h4>
        <ul className="tips-list">
          {/* Budget tip */}
          {budget === 'low' && (
            <li>
              Widen your budget to <strong>Medium/High</strong> for a greater selection of casual dining spots.
            </li>
          )}
          {budget === 'medium' && (
            <li>
              Widen your budget to <strong>High (₹800+)</strong> to unlock fine dining, microbreweries, and rooftop cafes.
            </li>
          )}
          {budget === 'high' && (
            <li>
              Explore all budgets to remove the upper spending tier restriction.
            </li>
          )}
          {!budget && (
            <li>Choose a budget or relax filters to see more restaurants.</li>
          )}

          {/* Cuisine tip */}
          {cuisine ? (
            <li>
              Select &quot;All Cuisines&quot; to explore other top-rated dishes and eateries in {location}.
            </li>
          ) : (
            <li>Search across all cuisines is already enabled in {location}.</li>
          )}

          {/* Nearby neighbourhood suggestions */}
          <li>
            {loadingNearby ? (
              <span>Finding verified nearby neighbourhoods...</span>
            ) : hasEligibleNearby ? (
              <div className="empty-nearby-section">
                <span>
                  Verified nearby neighbourhoods within{' '}
                  <strong>{radiusKm} km</strong> of {location}:
                </span>
                <div
                  className="empty-nearby-chips"
                  role="region"
                  aria-label={`Nearby neighbourhoods within ${radiusKm} km`}
                >
                  {activeNearbyList.slice(0, 6).map((item) => (
                    <span
                      key={item.name}
                      className="btn-nearby-chip"
                    >
                      <span className="nearby-pin">📍</span>
                      <span className="nearby-name">{item.name}</span>
                      <span className="nearby-dist-tag">{item.distance_km} km</span>
                    </span>
                  ))}
                </div>
                {has5km && has10km && (
                  <button
                    type="button"
                    className="radius-toggle-btn"
                    onClick={() => setRadiusKm(radiusKm === 5 ? 10 : 5)}
                  >
                    {radiusKm === 5
                      ? `Show up to 10 km (${nearbyData?.nearby_10km.length} areas)`
                      : `Show within 5 km (${nearbyData?.nearby_5km.length} areas)`}
                  </button>
                )}
              </div>
            ) : (
              <span>
                No verified adjacent neighbourhoods within 10 km for {location}. Try exploring all budgets or resetting filters.
              </span>
            )}
          </li>
        </ul>
      </div>

      <div className="empty-actions">
        {renderPrimaryActionButton()}
        {hasEligibleNearby && onSearchNearby && (
          <button
            type="button"
            className="btn-empty-action btn-empty-nearby"
            id="btn-search-nearby-locations"
            onClick={onSearchNearby}
          >
            <span>📍 Search Nearby Locations (within 10 km)</span>
          </button>
        )}
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
