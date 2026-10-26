/**
 * API client for DineMate backend.
 */

export interface MetaOptions {
  locations: string[];
  cuisines: string[];
  budget_labels: {
    low: string;
    medium: string;
    high: string;
  };
  rating_choices?: number[];
}

export interface RecommendationRequest {
  location: string;
  budget: 'low' | 'medium' | 'high' | '';
  cuisine: string;
  min_rating?: number | null;
  extras?: string;
  include_nearby?: boolean;
}

export interface RecommendationItem {
  id: string;
  rank: number;
  name: string;
  cuisines: string[];
  rating: number | null;
  votes: number;
  estimated_cost: number | null;
  neighborhood: string;
  distance_km?: number | null;
  explanation: string;
  vibe_tag?: string | null;
  url?: string | null;
}

export interface RecommendationResponse {
  query: RecommendationRequest;
  candidate_count: number;
  relaxed_filters: string[];
  summary: string;
  source: 'llm' | 'heuristic';
  recommendations: RecommendationItem[];
}

export interface HealthResponse {
  status: string;
}

// In dev with Vite proxy, empty string works seamlessly, or fallback to 8000
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : '';


export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchMetaOptions(): Promise<MetaOptions> {
  const response = await fetch(`${API_BASE_URL}/api/meta/options`);
  if (!response.ok) {
    throw new Error(`Failed to load options: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchRecommendations(
  payload: RecommendationRequest
): Promise<RecommendationResponse> {
  const response = await fetch(`${API_BASE_URL}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch recommendations: ${response.statusText}`);
  }
  return response.json();
}

export interface NearbyNeighbourhoodItem {
  name: string;
  distance_km: number;
}

export interface NearbyResponse {
  location: string;
  nearby_5km: NearbyNeighbourhoodItem[];
  nearby_10km: NearbyNeighbourhoodItem[];
}

export async function fetchNearbyNeighbourhoods(
  location: string
): Promise<NearbyResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/meta/nearby?location=${encodeURIComponent(location)}`
  );
  if (!response.ok) {
    throw new Error(`Failed to load nearby neighbourhoods: ${response.statusText}`);
  }
  return response.json();
}
