import React, { useEffect, useState } from 'react';

const LOADING_MESSAGES = [
  'Filtering 51,000+ real Bangalore restaurants...',
  'Checking neighborhood boundaries & verified budget bands...',
  'Consulting Groq LLM AI food critic for taste pairings...',
  'Baking fresh personalized recommendations...',
  'Adding the final garnish to your dining shortlist...',
];

export const LoadingSpinner: React.FC = () => {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setMessageIndex((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 1800);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="loading-state-container" aria-live="polite">
      <div className="loading-pot-graphic">
        <span className="pot-emoji">🍲</span>
        <div className="steam-particle steam-1">♨️</div>
        <div className="steam-particle steam-2">♨️</div>
      </div>

      <h3 className="loading-title">Dine❤️Mate is Curating Tables...</h3>
      <p className="loading-subtext">{LOADING_MESSAGES[messageIndex]}</p>

      {/* Stable skeleton recommendation cards to eliminate layout shifts */}
      <div className="loading-skeleton-grid">
        {[1, 2, 3].map((n) => (
          <div key={n} className="skeleton-card-item">
            <div className="skeleton-top-row">
              <div className="skeleton-pill pill-sm" />
              <div className="skeleton-pill pill-md" />
              <div className="skeleton-pill pill-sm right-align" />
            </div>
            <div className="skeleton-line line-header" />
            <div className="skeleton-chips-row">
              <div className="skeleton-tag" />
              <div className="skeleton-tag" />
              <div className="skeleton-tag" />
            </div>
            <div className="skeleton-rationale-box">
              <div className="skeleton-line line-sub" />
              <div className="skeleton-line line-full" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
