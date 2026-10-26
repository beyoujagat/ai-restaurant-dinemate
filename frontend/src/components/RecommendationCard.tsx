import React from 'react';
import type { RecommendationItem } from '../api/client';

interface RecommendationCardProps {
  item: RecommendationItem;
  rank: number;
}

export const RecommendationCard: React.FC<RecommendationCardProps> = ({
  item,
  rank,
}) => {
  const formattedRating = item.rating !== null ? item.rating.toFixed(1) : 'New';
  const formattedCost = item.estimated_cost
    ? `₹${item.estimated_cost.toLocaleString()} for two`
    : 'Cost not listed';

  return (
    <article
      className="rec-card-container"
      id={`restaurant-card-${item.id}`}
      aria-labelledby={`card-title-${item.id}`}
    >
      {/* Top Banner Row: Rank, Speciality/Vibe & Rating */}
      <div className="card-top-row">
        <div className="card-rank-tag">
          <span className="rank-number">#{rank}</span>
          <span className="rank-text">Top Pick</span>
        </div>

        {item.vibe_tag && (
          <div
            className={`card-vibe-tag ${
              item.vibe_tag.length > 24
                ? 'vibe-extra-long'
                : item.vibe_tag.length > 17
                ? 'vibe-long'
                : ''
            }`}
            title="AI Vibe Profile"
            aria-label={`Vibe: ${item.vibe_tag}`}
          >
            <span className="vibe-sparkle">✨</span>
            <span className="vibe-text">{item.vibe_tag}</span>
          </div>
        )}

        <div className="card-location-chip">
          <span className="chip-pin">📍</span>
          <span className="chip-neighborhood">{item.neighborhood}</span>
          {item.distance_km !== undefined && item.distance_km !== null && (
            <span className="chip-distance"> (~{item.distance_km.toFixed(1)} km)</span>
          )}
        </div>

        <div className="card-rating-badge">
          <span className="star-icon">★</span>
          <span className="rating-value">{formattedRating}</span>
          {item.votes > 0 && <span className="votes-count">({item.votes.toLocaleString()})</span>}
        </div>
      </div>

      {/* Restaurant Title */}
      <div className="card-title-row">
        <h3 id={`card-title-${item.id}`} className="restaurant-title">
          {item.name}
        </h3>
        <span className="cost-tag">{formattedCost}</span>
      </div>

      {/* Cuisine Tag Chips */}
      <div className="card-cuisines-row" aria-label="Cuisines">
        {item.cuisines.map((cuisine, idx) => (
          <span key={idx} className="cuisine-badge">
            {cuisine}
          </span>
        ))}
      </div>

      {/* AI Reasoning Box */}
      <div className="card-ai-rationale">
        <div className="ai-rationale-header">
          <div className="ai-header-left">
            <span className="ai-sparkle">✨</span>
            <span className="ai-header-title">Dine❤️Mate AI Rationale</span>
          </div>
        </div>
        <p className="ai-rationale-text">{item.explanation}</p>
      </div>

      {/* Action Footer */}
      <div className="card-footer-action">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-zomato-link"
            id={`zomato-link-${item.id}`}
          >
            <span>View on Zomato</span>
            <span className="arrow-icon">↗</span>
          </a>
        ) : (
          <span className="no-url-note">Verified Zomato Catalog Listing</span>
        )}
      </div>
    </article>
  );
};
