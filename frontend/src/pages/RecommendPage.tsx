import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  fetchHealth,
  fetchMetaOptions,
  fetchRecommendations,
} from '../api/client';
import type {
  HealthResponse,
  MetaOptions,
  RecommendationRequest,
  RecommendationResponse,
} from '../api/client';
import { WelcomeModal } from '../components/WelcomeModal';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { CategoryChips } from '../components/CategoryChips';
import { PreferenceForm } from '../components/PreferenceForm';
import { RecommendationCard } from '../components/RecommendationCard';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { EmptyState } from '../components/EmptyState';

export const RecommendPage: React.FC = () => {
  // Modal State
  const [showWelcomeModal, setShowWelcomeModal] = useState(true);

  // Health and Metadata State
  const [apiHealth, setApiHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [metaOptions, setMetaOptions] = useState<MetaOptions | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  // Navigation State
  const [activeNav, setActiveNav] = useState('recommend');

  // Query & Preferences State
  const [preferences, setPreferences] = useState<RecommendationRequest>({
    location: 'Banashankari',
    budget: 'medium',
    cuisine: '',
    min_rating: 4.0,
    extras: '',
  });

  // Keep a ref to latest preferences so dismiss handler can access current values safely
  const preferencesRef = useRef(preferences);
  useEffect(() => {
    preferencesRef.current = preferences;
  }, [preferences]);

  // Recommendations State
  const [recResponse, setRecResponse] = useState<RecommendationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  // Top search bar input state
  const [topSearchTerm, setTopSearchTerm] = useState('');

  /**
   * Reference-stable execution function.
   * Takes the exact query payload to execute and does NOT depend on component state.
   */
  const executeRecommendation = useCallback(
    async (queryToRun: RecommendationRequest) => {
      setIsLoading(true);
      setErrorMessage(null);
      setHasSearched(true);

      try {
        const data = await fetchRecommendations(queryToRun);
        setRecResponse(data);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : 'Failed to fetch recommendations';
        setErrorMessage(msg);
      } finally {
        setIsLoading(false);
      }
    },
    [] // Stable reference: never re-created
  );

  /**
   * Initial load: Fetch health and metadata ONLY ONCE on mount.
   * Does NOT trigger automatic recommendation fetching to avoid loops.
   */
  useEffect(() => {
    let isMounted = true;

    // 1. Health check
    fetchHealth()
      .then((data) => {
        if (isMounted) {
          setApiHealth(data);
          setHealthLoading(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setHealthLoading(false);
        }
      });

    // 2. Load catalog options
    fetchMetaOptions()
      .then((data) => {
        if (!isMounted) return;
        setMetaOptions(data);
        setMetaLoading(false);

        // Pre-set default location if available
        const defaultLoc =
          data.locations.includes('Banashankari')
            ? 'Banashankari'
            : data.locations[0] || 'Koramangala 5th Block';

        setPreferences((prev) => ({
          ...prev,
          location: defaultLoc,
        }));
      })
      .catch((err) => {
        if (isMounted) {
          setMetaLoading(false);
          setErrorMessage(`Could not load catalog options: ${err.message}`);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []); // Run strictly once on mount

  // Modal dismiss handler
  const handleModalDismiss = () => {
    setShowWelcomeModal(false);
    // Explicit trigger on first modal dismiss
    if (!hasSearched) {
      executeRecommendation(preferencesRef.current);
    }
  };

  // Explicit User Action: Clicking a category chip
  const handleSelectCategory = (cuisineKeyword: string) => {
    const updated: RecommendationRequest = {
      ...preferences,
      cuisine: cuisineKeyword,
    };
    setPreferences(updated);
    executeRecommendation(updated);
  };

  // Explicit User Action: Form submit
  const handleFormSubmit = () => {
    executeRecommendation(preferences);
  };

  // Explicit User Action: Navigation item click
  const handleNavClick = (navId: string) => {
    setActiveNav(navId);
    if (navId === 'top_rated') {
      const updated: RecommendationRequest = {
        ...preferences,
        min_rating: 4.5,
      };
      setPreferences(updated);
      executeRecommendation(updated);
    } else if (navId === 'recommend') {
      executeRecommendation(preferences);
    } else if (navId === 'neighborhoods') {
      const el = document.getElementById('pref-location');
      el?.focus();
    } else if (navId === 'trending') {
      const el = document.querySelector('.category-chips-section');
      el?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Explicit User Action: Topbar search submit
  const handleTopSearchSubmit = () => {
    const updated: RecommendationRequest = {
      ...preferences,
      extras: topSearchTerm,
    };
    setPreferences(updated);
    executeRecommendation(updated);
  };

  // Empty state recovery handlers
  const handleWidenBudget = () => {
    const updated: RecommendationRequest = {
      ...preferences,
      budget: 'high',
    };
    setPreferences(updated);
    executeRecommendation(updated);
  };

  const handleResetFilters = () => {
    const defaultLoc = metaOptions?.locations[0] || 'Banashankari';
    const updated: RecommendationRequest = {
      location: defaultLoc,
      budget: 'medium',
      cuisine: '',
      min_rating: null,
      extras: '',
    };
    setPreferences(updated);
    setTopSearchTerm('');
    executeRecommendation(updated);
  };

  return (
    <div className="dinemate-app-layout">
      {/* 1. Playful Welcome Modal (Single Action Button) */}
      {showWelcomeModal && <WelcomeModal onDismiss={handleModalDismiss} />}

      {/* 2. Left Sidebar Navigation */}
      <Sidebar
        activeNav={activeNav}
        onNavClick={handleNavClick}
        apiOnline={apiHealth?.status === 'ok'}
      />

      {/* 3. Main Application Workspace */}
      <div className="app-main-content">
        {/* Top Header / Search Bar */}
        <TopBar
          apiHealth={apiHealth}
          healthLoading={healthLoading}
          selectedLocation={preferences.location}
          onOpenTour={() => setShowWelcomeModal(true)}
          searchTerm={topSearchTerm}
          onSearchChange={setTopSearchTerm}
          onSearchSubmit={handleTopSearchSubmit}
        />

        <main className="dashboard-body">
          {/* Hero Welcome Banner */}
          <section className="dashboard-hero-card">
            <div className="hero-text-col">
              <div className="hero-pill-badge">
                <span className="badge-flame">🔥</span>
                <span>Zomato Bangalore Catalog</span>
              </div>
              <h2 className="hero-banner-title">
                Find Your Next Favorite Table with{' '}
                <span className="hero-brand-name">
                  Dine<span className="logo-heart">❤️</span>Mate
                </span>
              </h2>
              <p className="hero-banner-desc">
                Hard constraints are filtered deterministically in code across 51,000+ verified
                restaurants, and the top candidates are thoughtfully reasoned by AI.
              </p>
            </div>

            <div className="hero-img-col">
              <img
                src="/assets/hero_food_3d.jpg"
                alt="3D Gourmet Food Showcase"
                className="hero-3d-graphic animate-float-slow"
              />
            </div>
          </section>

          {/* Popular Cravings Category Bar */}
          <CategoryChips
            selectedCuisine={preferences.cuisine}
            onSelectCategory={handleSelectCategory}
          />

          {/* Form & Results Two-Column Layout */}
          <div className="content-grid-layout">
            {/* Left Column: Form Controls */}
            <section className="form-column" aria-label="Dining Criteria">
              <PreferenceForm
                metaOptions={metaOptions}
                metaLoading={metaLoading}
                preferences={preferences}
                onChange={setPreferences}
                onSubmit={handleFormSubmit}
                isLoading={isLoading}
              />
            </section>

            {/* Right Column: Dynamic Recommendations */}
            <section className="results-column" aria-label="Recommendations">
              {/* Results Top Meta Bar */}
              <div className="results-status-bar">
                <div className="results-meta-title">
                  <h3 className="results-heading">Curated Recommendations</h3>
                  {recResponse && (
                    <span className="results-count-chip">
                      {recResponse.recommendations.length} of {recResponse.candidate_count} candidates
                    </span>
                  )}
                </div>

                {recResponse && (
                  <div className="results-badges-group">
                    <span
                      className={`source-badge ${
                        recResponse.source === 'llm' ? 'source-llm' : 'source-heuristic'
                      }`}
                      title={
                        recResponse.source === 'llm'
                          ? 'Groq LLM generated natural-language explanations'
                          : 'Deterministic catalog heuristic explanation'
                      }
                    >
                      {recResponse.source === 'llm' ? '✨ Groq LLM Reasoned' : '⚡ Heuristic Match'}
                    </span>
                  </div>
                )}
              </div>

              {/* Relaxed Filters Notification Banner */}
              {recResponse?.relaxed_filters && recResponse.relaxed_filters.length > 0 && (
                <div className="relaxed-notice-banner" role="alert">
                  <span className="notice-icon">ℹ️</span>
                  <span>
                    Note: To find great matches, some constraints were broadened:{' '}
                    <strong>{recResponse.relaxed_filters.join(', ')}</strong>.
                  </span>
                </div>
              )}

              {/* Heuristic Fallback Notice Banner */}
              {recResponse?.source === 'heuristic' && recResponse.recommendations.length > 0 && (
                <div className="heuristic-notice-banner" role="status">
                  <span className="notice-icon">⚡</span>
                  <span>
                    <strong>Catalog Heuristic Ranking Active:</strong> Recommendations were ranked using deterministic catalog ratings and review votes while AI reasoning is offline.
                  </span>
                </div>
              )}

              {/* Summary line from engine */}
              {recResponse?.summary && (
                <div className="results-summary-quote">
                  <span className="quote-mark">“</span>
                  <span>{recResponse.summary}</span>
                  <span className="quote-mark">”</span>
                </div>
              )}

              {/* Error Banner */}
              {errorMessage && (
                <div className="results-error-card" role="alert">
                  <div className="error-icon">⚠️</div>
                  <div className="error-content">
                    <h4>Unable to Load Recommendations</h4>
                    <p>{errorMessage}</p>
                    <button
                      type="button"
                      className="btn-retry"
                      onClick={() => executeRecommendation(preferences)}
                    >
                      Retry Search
                    </button>
                  </div>
                </div>
              )}

              {/* Content States: Loading, Empty, Cards, or Ready State */}
              {isLoading ? (
                <LoadingSpinner />
              ) : recResponse && recResponse.recommendations.length > 0 ? (
                <div className="recommendations-grid">
                  {recResponse.recommendations.map((item, index) => (
                    <RecommendationCard
                      key={item.id || index}
                      item={item}
                      rank={index + 1}
                    />
                  ))}
                </div>
              ) : hasSearched && !isLoading ? (
                <EmptyState
                  location={preferences.location}
                  cuisine={preferences.cuisine}
                  budget={preferences.budget}
                  onResetFilters={handleResetFilters}
                  onWidenBudget={handleWidenBudget}
                />
              ) : (
                <div className="ready-prompt-card">
                  <span className="ready-icon">🍽️</span>
                  <h4>Ready to Discover Your Next Feast?</h4>
                  <p>
                    Pick an iconic craving above (Biryani, South Indian, Pizza, etc.) or click{' '}
                    <strong>Find My Perfect Spots</strong> to begin!
                  </p>
                </div>
              )}
            </section>
          </div>
        </main>

        {/* Footer */}
        <footer className="app-footer">
          <div className="footer-left">
            <span className="footer-brand">
              Dine<span className="logo-heart">❤️</span>Mate
            </span>
            <span className="footer-divider">•</span>
            <span>Real Bangalore Zomato Catalog Dataset</span>
          </div>
          <div className="footer-right">
            <span>Deterministic Filter Layer → Groq LLM Ranking</span>
          </div>
        </footer>
      </div>

      {/* Floating API / Network Error Toast */}
      {errorMessage && (
        <div className="api-error-toast" role="alert" id="api-error-toast">
          <div className="toast-content">
            <span className="toast-icon">⚠️</span>
            <span className="toast-message">
              <strong>Connection Issue:</strong> {errorMessage}
            </span>
          </div>
          <button
            type="button"
            className="btn-toast-retry"
            onClick={() => executeRecommendation(preferences)}
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
};
