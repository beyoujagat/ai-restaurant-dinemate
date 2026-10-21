import React from 'react';
import type { HealthResponse } from '../api/client';

interface TopBarProps {
  apiHealth: HealthResponse | null;
  healthLoading: boolean;
  selectedLocation: string;
  onOpenTour: () => void;
  searchTerm: string;
  onSearchChange: (val: string) => void;
  onSearchSubmit: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  apiHealth,
  healthLoading,
  selectedLocation,
  onOpenTour,
  searchTerm,
  onSearchChange,
  onSearchSubmit,
}) => {
  const isHealthy = apiHealth?.status === 'ok';

  return (
    <header className="app-topbar">
      {/* City Location indicator */}
      <div className="topbar-location-pill">
        <span className="location-icon">📍</span>
        <div className="location-text">
          <span className="location-label">Exploring Bangalore</span>
          <span className="location-zone">
            {selectedLocation ? selectedLocation : 'All Neighborhoods'}
          </span>
        </div>
      </div>

      {/* Global Craving Search Bar */}
      <form
        className="topbar-search-form"
        onSubmit={(e) => {
          e.preventDefault();
          onSearchSubmit();
        }}
      >
        <span className="search-icon">🔍</span>
        <input
          type="text"
          className="topbar-search-input"
          placeholder="What are you craving? (e.g. rooftop, biryani, craft beer, cozy cafe)..."
          value={searchTerm}
          onChange={(e) => onSearchChange(e.target.value)}
          id="topbar-cravings-input"
        />
        {searchTerm && (
          <button
            type="button"
            className="search-clear-btn"
            onClick={() => onSearchChange('')}
            title="Clear search"
          >
            ✕
          </button>
        )}
        <button
          type="submit"
          className="search-submit-btn"
          id="btn-topbar-search"
          title="Search cravings"
        >
          Search
        </button>
      </form>

      {/* Right controls: Health Pill & Tour */}
      <div className="topbar-actions">
        <div
          className={`backend-status-chip ${
            isHealthy ? 'status-online' : healthLoading ? 'status-checking' : 'status-offline'
          }`}
          title={isHealthy ? 'FastAPI & SQLite Catalog connected' : 'Connecting to backend...'}
        >
          <span className="status-dot" />
          <span className="status-label">
            {healthLoading ? 'Connecting...' : isHealthy ? 'API Online' : 'API Offline'}
          </span>
        </div>

        <button
          type="button"
          className="btn-tour-pill"
          onClick={onOpenTour}
          title="Open welcome card"
          id="btn-open-welcome-tour"
        >
          <span>✨ Welcome</span>
        </button>

        <div className="user-avatar-pill">
          <span className="avatar-icon">🧑‍🍳</span>
          <span className="avatar-name">Bangalore Foodie</span>
        </div>
      </div>
    </header>
  );
};
