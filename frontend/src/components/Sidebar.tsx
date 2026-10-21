import React from 'react';

interface SidebarProps {
  activeNav: string;
  onNavClick: (navId: string) => void;
  apiOnline: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeNav,
  onNavClick,
  apiOnline,
}) => {
  const navItems = [
    { id: 'recommend', icon: '🍽️', label: 'AI Concierge', badge: 'Live' },
    { id: 'neighborhoods', icon: '📍', label: 'Neighborhoods', badge: null },
    { id: 'top_rated', icon: '⭐', label: 'Top Rated', badge: '4.5+' },
    { id: 'trending', icon: '🔥', label: 'Trending Cuisines', badge: null },
  ];

  return (
    <aside className="app-sidebar" aria-label="Main Navigation">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <div className="brand-logo-mark">
          <span className="brand-fork-knife">🍽️</span>
        </div>
        <div className="brand-text-block">
          <h1 className="brand-title-main">
            Dine<span className="logo-heart">❤️</span>Mate
          </h1>
          <p className="brand-tagline">AI Restaurant Concierge</p>
        </div>
      </div>

      {/* Nav Menu */}
      <nav className="sidebar-nav">
        <span className="nav-section-title">DISCOVER BANGALORE</span>
        <ul className="nav-list">
          {navItems.map((item) => {
            const isActive = activeNav === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className={`nav-link-btn ${isActive ? 'active' : ''}`}
                  onClick={() => onNavClick(item.id)}
                >
                  <span className="nav-link-icon">{item.icon}</span>
                  <span className="nav-link-label">{item.label}</span>
                  {item.badge && (
                    <span className={`nav-link-badge ${isActive ? 'badge-active' : ''}`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* AI Concierge Info Box */}
      <div className="sidebar-ai-card">
        <div className="ai-card-header">
          <span className="ai-sparkle-pulse">✨</span>
          <span className="ai-card-title">Intelligent Curation</span>
        </div>
        <p className="ai-card-desc">
          Strict code filters on 51k+ rows, followed by deep Groq LLM taste reasoning.
        </p>
        <div className="ai-card-status">
          <span className={`status-indicator-dot ${apiOnline ? 'dot-online' : 'dot-offline'}`} />
          <span className="status-indicator-text">
            {apiOnline ? 'FastAPI & LLM Connected' : 'Backend Connecting...'}
          </span>
        </div>
      </div>

      {/* Bangalore Catalog Badge */}
      <div className="sidebar-footer-city">
        <div className="city-pin">📍</div>
        <div className="city-info">
          <div className="city-name">Bengaluru, KA</div>
          <div className="city-stats">Zomato Catalog • 51k+ Rows</div>
        </div>
      </div>
    </aside>
  );
};
