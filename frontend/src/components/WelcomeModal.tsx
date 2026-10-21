import React, { useState } from 'react';

interface WelcomeModalProps {
  onDismiss: () => void;
}

export const WelcomeModal: React.FC<WelcomeModalProps> = ({ onDismiss }) => {
  const [isDismissing, setIsDismissing] = useState(false);

  const handleDismiss = () => {
    if (isDismissing) return;
    setIsDismissing(true);
    // Smooth transition before unmounting
    setTimeout(() => {
      onDismiss();
    }, 320);
  };

  return (
    <div
      className={`modal-backdrop ${isDismissing ? 'modal-fade-out' : 'modal-fade-in'}`}
      role="dialog"
      aria-modal="true"
      id="welcome-modal-overlay"
      onClick={(e) => {
        // Allow clicking outer backdrop to dismiss
        if (e.target === e.currentTarget) {
          handleDismiss();
        }
      }}
    >
      {/* Surrounding Floating 3D-style Food Stickers with lively micro-animations */}
      <div className="floating-food-orbit orbit-tl" aria-hidden="true">
        <div className="floating-badge badge-burger animate-float-slow">
          <span className="food-emoji">🍔</span>
          <span className="badge-caption">Gourmet Burgers</span>
        </div>
      </div>

      <div className="floating-food-orbit orbit-tr" aria-hidden="true">
        <div className="floating-badge badge-pizza animate-float-reverse">
          <span className="food-emoji">🍕</span>
          <span className="badge-caption">Woodfired Pizza</span>
        </div>
      </div>

      <div className="floating-food-orbit orbit-bl" aria-hidden="true">
        <div className="floating-badge badge-biryani animate-float-reverse">
          <span className="food-emoji">🍛</span>
          <span className="badge-caption">Dum Biryani</span>
        </div>
      </div>

      <div className="floating-food-orbit orbit-br" aria-hidden="true">
        <div className="floating-badge badge-basil animate-float-slow">
          <span className="food-emoji">🥗</span>
          <span className="badge-caption">Fresh Bowls &amp; Herbs</span>
        </div>
      </div>

      <div className="floating-food-orbit orbit-ml" aria-hidden="true">
        <div className="floating-badge badge-noodles animate-float-slow">
          <span className="food-emoji">🍜</span>
        </div>
      </div>

      <div className="floating-food-orbit orbit-mr" aria-hidden="true">
        <div className="floating-badge badge-sushi animate-float-reverse">
          <span className="food-emoji">🍣</span>
        </div>
      </div>

      {/* Main Modal Card */}
      <div
        className={`welcome-modal-card ${isDismissing ? 'card-dismissing' : 'card-entering'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header-brand">
          <span className="modal-logo-text">
            Dine<span className="logo-heart">❤️</span>Mate
          </span>
          <span className="modal-city-tag">Bangalore Concierge</span>
        </div>

        <div className="modal-visual-frame">
          <img
            src="/assets/hero_food_3d.jpg"
            alt="Delicious 3D food illustration"
            className="modal-hero-img"
          />
          <div className="modal-visual-overlay-pill">
            <span className="sparkle-icon">✨</span> 51,000+ Verified Tables
          </div>
        </div>

        <div className="modal-content-body">
          <h2 className="modal-headline">Hungry for the Perfect Spot?</h2>
          <p className="modal-subtext">
            Turn your cravings into your next favourite food adventure.
          </p>
        </div>

        {/* Action Button: Single primary button with smooth basil green hover/click */}
        <div className="modal-actions-group">
          <button
            type="button"
            className="btn-modal-single"
            onClick={handleDismiss}
            id="btn-welcome-find-feast"
          >
            <span className="btn-icon">🍽️</span>
            <span>Let's find my feast!</span>
          </button>
        </div>
      </div>
    </div>
  );
};
