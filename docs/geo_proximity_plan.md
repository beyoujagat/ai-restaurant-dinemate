# DineMate — Geo-Proximity Plan
## Adding 5 km → 10 km Neighbourhood Expansion

> **Architectural plan approved. Plan document update only — no application code or runtime files modified.**

---

## 1. What the Dataset Already Has

| Field | Table / File | Example Value |
|---|---|---|
| `neighborhood` | `restaurants.sqlite → restaurants`, `locations` | `"Indiranagar"` |
| `listed_city` | `restaurants.sqlite → restaurants` | `"MG Road"` |
| `address` | `restaurants.sqlite → restaurants` | `"942, 21st Main Road, 2nd Stage, Banashankari, …"` |

**Confirmed absent:** `latitude`, `longitude` — in every layer (raw dataset, SQLite, Parquet, domain model, filters, tests).

**Distinct neighborhood values (93 total from `locations` table):**

```
BTM, Banashankari, Banaswadi, Bannerghatta Road, Basavanagudi,
Basaveshwara Nagar, Bellandur, Bommanahalli, Brigade Road,
Brookefield, CV Raman Nagar, Central Bangalore, Church Street,
City Market, Commercial Street, Cunningham Road, Domlur,
East Bangalore, Ejipura, Electronic City, Frazer Town,
HBR Layout, HSR, Hebbal, Hennur, Hosur Road,
ITPL Main Road Whitefield, Indiranagar, Infantry Road, JP Nagar,
Jakkur, Jalahalli, Jayanagar, Jeevan Bhima Nagar, KR Puram,
Kaggadasapura, Kalyan Nagar, Kammanahalli, Kanakapura Road,
Kengeri, Koramangala, Koramangala 1st–8th Block,
Kumaraswamy Layout, Langford Town, Lavelle Road, MG Road,
Magadi Road, Majestic, Malleshwaram, Marathahalli, Mysore Road,
Nagarbhavi, Nagawara, New BEL Road, North Bangalore,
Old Airport Road, Old Madras Road, Peenya, RT Nagar,
Race Course Road, Rajajinagar, Rajarajeshwari Nagar,
Rammurthy Nagar, Residency Road, Richmond Road, Sadashiv Nagar,
Sahakara Nagar, Sanjay Nagar, Sankey Road, Sarjapur Road,
Seshadripuram, Shanti Nagar, Shivajinagar, South Bangalore,
St. Marks Road, Thippasandra, Ulsoor, Uttarahalli,
Varthur Main Road Whitefield, Vasanth Nagar, Vijay Nagar,
West Bangalore, Whitefield, Wilson Garden, Yelahanka, Yeshwantpur
```

**Scope Boundary:** Only `neighborhood` values are used for geo-proximity calculations. `listed_city` is an editorial grouping in the raw data and is deliberately excluded from proximity calculations to prevent cross-field ambiguity.

---

## 2. Architectural Decisions

1. **OpenStreetMap Nominatim for Geocoding:** Used for a one-time lookup script respecting OSM usage policies (1 request/second strict rate limit, dedicated descriptive `User-Agent` header).
2. **Strict Verification Gating:** Unverified coordinates (`verified: false`) or coordinates outside the valid Bangalore bounding box (`12.7–13.2°N`, `77.4–77.9°E`) are **never** used for automatic proximity matching. If selected, the engine falls back to exact matching only.
3. **Transparent UI Communication:** When results are returned via 5 km or 10 km geographic expansion, the frontend and API summaries display clear, human-friendly messaging rather than internal flag strings.
4. **Broad Area Label Exclusion:** Non-specific regional zones (`"Central Bangalore"`, `"East Bangalore"`, `"West Bangalore"`, `"North Bangalore"`, `"South Bangalore"`) are tagged with `"broad_area": true` and excluded from automatic radius matching until a defensible reference point is established. Exact matching applies.
5. **Single Source of Truth (`neighborhood` only):** Proximity calculations exclusively operate on the selected `neighborhood` field; `listed_city` is not conflated with neighbourhood coordinates.
6. **Committed Coordinate Lookup:** Verified coordinates are stored in a small static file (`data/processed/neighbourhood_coords.json`) committed to Git, eliminating runtime geocoding and external API dependencies during deployment.

---

## 3. One-Time Geocoding Method

### Endpoint & Protocol

**Endpoint:** `https://nominatim.openstreetmap.org/search`

**Request Example:**
```http
GET /search?q=Indiranagar,+Bengaluru,+Karnataka,+India&format=json&limit=1&countrycodes=in HTTP/1.1
Host: nominatim.openstreetmap.org
User-Agent: DineMate-Bangalore-Geocoder/1.0 (dinemate-app@local)
```

### Policy Compliance & Safeguards
- **Rate Limit:** Strictly enforced `time.sleep(1.0)` between requests.
- **Bounding Box Validation:** Each returned coordinate must satisfy `12.7 <= lat <= 13.2` and `77.4 <= lon <= 77.9`. Coordinates outside this box are discarded.
- **One-time Execution:** Run offline via `backend/scripts/geocode_neighbourhoods.py`. Generated coordinates are committed to version control; the production app never makes external network calls for geocoding.

---

## 4. Supplementary Coordinates File Schema

### File: `data/processed/neighbourhood_coords.json`

```json
{
  "__version__": "1.0",
  "Banashankari": {
    "lat": 12.9256,
    "lng": 77.5462,
    "verified": true,
    "broad_area": false
  },
  "Indiranagar": {
    "lat": 12.9784,
    "lng": 77.6408,
    "verified": true,
    "broad_area": false
  },
  "Central Bangalore": {
    "lat": 12.9716,
    "lng": 77.5946,
    "verified": false,
    "broad_area": true
  },
  "East Bangalore": {
    "lat": 12.9716,
    "lng": 77.6946,
    "verified": false,
    "broad_area": true
  }
}
```

### Entry Fields:
- `lat` / `lng`: Decimal coordinates (WGS84).
- `verified`: Boolean (`true` only if verified against map centroid).
- `broad_area`: Boolean (`true` for regional zones; inhibits radius matching).

---

## 5. Distance Calculation & Proximity Engine

### Haversine Formula (Pure Python `math`)

```python
import math

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0  # Earth radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

### Proximity Querying Rules:
- If `query_location` is not in lookup, has `verified == false`, or has `broad_area == true`:
  - `find_nearby_neighbourhoods(query_location, radius_km)` returns `[]`.
- Candidates in nearby neighbourhoods are retrieved via SQL:
  `SELECT * FROM restaurants WHERE LOWER(neighborhood) IN (?, ?, ...)`
  (utilizing the existing SQLite index on `neighborhood`).

---

## 6. Refined Relaxation Ladder (Interaction with Budget & Extras)

To avoid returning restaurants that match none of the diner's preferences (e.g. 10 km away, wrong budget, and missing tags), relaxation follows a deterministic precedence ladder:

```
User Query: [Location: "Indiranagar", Budget: "low", Cuisine: "Italian", Extras: "book_table"]
  │
  ├─ Tier 0: Strict Query (Strict Location + Strict Budget + Strict Extras)
  │    → If candidates found: return results, relaxed_filters = []
  │
  ├─ Tier 1: Local Extras Relax (Strict Location + Strict Budget + Drop Extras)
  │    → If candidates found: return results, relaxed_filters = ["extras"]
  │    (Diners prefer staying in their neighbourhood over keeping an extra tag)
  │
  ├─ Tier 2: Geo 5 km + Strict Budget (Nearby <= 5 km + Strict Budget + Strict Extras)
  │    → If candidates found: return results, relaxed_filters = ["location_expanded_5km"]
  │    (Preserves budget by looking in adjacent neighbourhoods)
  │
  ├─ Tier 3: Geo 5 km Relax (Nearby <= 5 km + Strict Budget + Drop Extras)
  │    → If candidates found: return results, relaxed_filters = ["location_expanded_5km", "extras"]
  │
  ├─ Tier 4: Geo 10 km + Strict Budget (Nearby <= 10 km + Strict Budget + Strict Extras)
  │    → If candidates found: return results, relaxed_filters = ["location_expanded_10km"]
  │
  ├─ Tier 5: Geo 10 km Relax (Nearby <= 10 km + Strict Budget + Drop Extras)
  │    → If candidates found: return results, relaxed_filters = ["location_expanded_10km", "extras"]
  │
  ├─ Tier 6: Local Budget Widening (Strict Location + Widen Budget [low→med] + Strict/Dropped Extras)
  │    → If candidates found: return results, relaxed_filters = ["budget"] or ["budget", "extras"]
  │    (Note: "high" budget is never relaxed down, protecting premium dining intent)
  │
  └─ Tier 7: Empty Result Fallback
       → Return candidate_count = 0 with constructive suggestions in summary.
       (Avoids compounding 10 km expansion AND budget widening simultaneously).
```

---

## 7. UI Communication & Response Alignment

### Frontend Display (`frontend/src/pages/RecommendPage.tsx`)
Replace raw token rendering with user-facing explanations:

```tsx
// Helper to format friendly notification
const formatRelaxationNotice = (relaxed: string[], queryLoc?: string) => {
  const parts: string[] = [];
  if (relaxed.includes('location_expanded_10km')) {
    parts.push(`expanded your search within 10 km of ${queryLoc || 'your area'}`);
  } else if (relaxed.includes('location_expanded_5km')) {
    parts.push(`expanded your search within 5 km of ${queryLoc || 'your area'}`);
  }
  if (relaxed.includes('budget')) {
    parts.push('widened your budget criteria');
  }
  if (relaxed.includes('extras')) {
    parts.push('relaxed optional amenity filters');
  }
  return `Note: To find great matches, we ${parts.join(' and ')}.`;
};
```

### Backend Summary Generator (`build_summary` in `recommend.py`)
- If `location_expanded_5km` in `relaxed_filters`:
  `"Top 5 Italian recommendations within 5 km of Indiranagar."`
- If `location_expanded_10km` in `relaxed_filters`:
  `"Top 5 Italian recommendations within 10 km of Indiranagar."`

### Groq LLM Ranker Integration (`app/llm/prompts.py`)
- The prompt builder appends relaxation context to the user prompt:
  *"Note: Candidate list was expanded to nearby neighbourhoods within 5 km of Indiranagar. Acknowledge the restaurant's actual locality accurately."*
  This prevents the model from hallucinating that a Domlur venue is in Indiranagar.

---

## 8. Exact Files That Will Change

### New Files

| File | Purpose |
|---|---|
| `data/processed/neighbourhood_coords.json` | Static coordinate lookup with `verified` and `broad_area` flags. Committed to Git. |
| `backend/app/catalog/geo.py` | Core geo module: `load_coords()`, `haversine_km()`, `find_nearby_neighbourhoods(query_location, radius_km)`. |
| `backend/scripts/geocode_neighbourhoods.py` | One-time offline Nominatim script with rate limiting and bbox checks. |
| `backend/tests/test_geo.py` | Unit tests for geocoding data, Haversine accuracy, gating, and bounding box checks. |

### Existing Files That Will Change

| File | Change |
|---|---|
| [`backend/app/catalog/filters.py`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/backend/app/catalog/filters.py) | Add `filter_by_nearby_locations` helper function. Existing `filter_by_location` is untouched. |
| [`backend/app/catalog/store.py`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/backend/app/catalog/store.py) | Extend candidate query to support neighbourhood sets (`neighborhood IN (...)`). |
| [`backend/app/services/recommend.py`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/backend/app/services/recommend.py) | Implement the 7-tier relaxation ladder in `get_candidates_with_relaxation`; update `build_summary` for radius messaging. |
| [`backend/app/llm/prompts.py`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/backend/app/llm/prompts.py) | Include relaxation context in the prompt to ensure explanations reflect actual restaurant localities. |
| [`frontend/src/pages/RecommendPage.tsx`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/frontend/src/pages/RecommendPage.tsx) | Replace raw `relaxed_filters.join(', ')` with human-readable banner text. |
| [`backend/tests/test_resilience.py`](file:///c:/Users/jagat/AI-Projects/ai-restaurant-dinemate/backend/tests/test_resilience.py) | Add test cases verifying relaxation ladder tiers and `relaxed_filters` flags. |

### Files That Do NOT Change

| File | Reason |
|---|---|
| `data/processed/restaurants.sqlite` | Schema unchanged. |
| `data/processed/restaurants.parquet` | Schema unchanged. |
| `backend/app/catalog/ingest.py` | Pipeline unchanged; coordinates live separately. |
| `backend/app/domain/models.py` | `Restaurant` model unchanged; `RecommendationResponse.relaxed_filters` already supports string list. |
| `backend/requirements.txt` | No new packages needed (pure `math`, `httpx` already installed). |

---

## 9. Test Matrix

| Test Suite / Test Name | Verification Target |
|---|---|
| `test_haversine_known_pair` | Indiranagar ↔ Koramangala 5th Block ≈ 4.8 km (within ±0.5 km). |
| `test_haversine_symmetry_and_zero` | `dist(A, B) == dist(B, A)` and `dist(A, A) == 0.0`. |
| `test_load_coords_bbox` | All entries in `neighbourhood_coords.json` satisfy `12.7 <= lat <= 13.2` and `77.4 <= lng <= 77.9`. |
| `test_unverified_coords_excluded` | Neighbourhood with `verified: false` returns `[]` from `find_nearby_neighbourhoods`. |
| `test_broad_area_coords_excluded` | Broad area labels (`Central Bangalore`, etc.) return `[]` from `find_nearby_neighbourhoods`. |
| `test_find_nearby_5km_vs_10km` | Domlur is within 5 km of Indiranagar; Whitefield is > 15 km away and not returned. |
| `test_relaxation_ladder_extras_before_geo` | Missing extra tag in strict location drops tag before expanding radius. |
| `test_relaxation_ladder_geo_before_budget` | Zero candidates in strict location triggers 5 km expansion while preserving strict budget. |
| `test_relaxed_filters_flag_values` | Returns `["location_expanded_5km"]` and `["location_expanded_10km"]` respectively. |
| `test_ui_banner_formatting` | Frontend renders user-friendly expansion copy for 5 km and 10 km expansions. |
| `test_existing_regression_suite` | All existing catalog, ranking, and API tests continue to pass without regression. |

---

## 10. Step-by-Step Implementation Roadmap

### Step 1: Offline Geocoding & Coordinate Dataset Creation
1. **Create the Geocoder Script (`backend/scripts/geocode_neighbourhoods.py`)**:
   - Query all distinct neighbourhoods from `locations` in `data/processed/restaurants.sqlite`.
   - Implement OpenStreetMap Nominatim queries with:
     - Polite custom `User-Agent: DineMate-Bangalore-Geocoder/1.0`.
     - Strict `time.sleep(1.0)` between requests.
     - Bangalore bounding box filter (`12.7 <= lat <= 13.2` and `77.4 <= lng <= 77.9`).
   - Mark the 5 broad regional areas (`"Central Bangalore"`, `"East Bangalore"`, `"West Bangalore"`, `"North Bangalore"`, `"South Bangalore"`) with `"broad_area": true`.
2. **Execute and Verify Coordinates**:
   - Run the script once locally to generate `data/processed/neighbourhood_coords.json`.
   - Inspect and verify centroids for key ambiguous localities (e.g. BTM, HSR, Koramangala blocks) and set `"verified": true`.
   - Commit `data/processed/neighbourhood_coords.json` to Git.

### Step 2: Core Geo Engine Module (`backend/app/catalog/geo.py`)
1. **Coordinate Loader & Validation**:
   - Implement `load_coords()` with in-memory caching (`lru_cache` or module singleton).
   - Filter out entries where `verified != true` or `broad_area == true`.
2. **Distance & Proximity Functions**:
   - Implement pure-Python `haversine_km(lat1, lng1, lat2, lng2)` using Python's `math` module.
   - Implement `find_nearby_neighbourhoods(query_location: str, radius_km: float) -> list[str]`:
     - Returns neighbouring locations within `radius_km` (excluding the query location itself).
     - Returns `[]` if the query location is unverified, missing, or a broad area.
3. **Write Unit Tests (`backend/tests/test_geo.py`)**:
   - Test Haversine precision against known pairs (e.g. Indiranagar ↔ Koramangala ≈ 4.8 km).
   - Test exclusion of unverified/broad-area entries and bounding box checks.
   - Run `pytest backend/tests/test_geo.py` to confirm.

### Step 3: Catalog Query & Filter Layer Updates
1. **Filters Layer (`backend/app/catalog/filters.py`)**:
   - Add `filter_by_nearby_locations(restaurants, query_location, radius_km)` without modifying the existing `filter_by_location` function.
2. **Store Layer (`backend/app/catalog/store.py`)**:
   - Extend `query_candidates()` (or add a helper) to support candidate querying across a list of neighbourhoods using SQL `WHERE LOWER(neighborhood) IN (...)`.

### Step 4: Recommendation Engine & Relaxation Ladder
1. **Update `backend/app/services/recommend.py`**:
   - Refactor `get_candidates_with_relaxation()` to follow the 7-tier relaxation ladder:
     - **Tier 0:** Strict query.
     - **Tier 1:** Strict location + drop extras → `relaxed_filters = ["extras"]`.
     - **Tier 2:** 5 km neighbours + strict budget → `relaxed_filters = ["location_expanded_5km"]`.
     - **Tier 3:** 5 km neighbours + drop extras → `relaxed_filters = ["location_expanded_5km", "extras"]`.
     - **Tier 4:** 10 km neighbours + strict budget → `relaxed_filters = ["location_expanded_10km"]`.
     - **Tier 5:** 10 km neighbours + drop extras → `relaxed_filters = ["location_expanded_10km", "extras"]`.
     - **Tier 6:** Strict location + widen budget (maintaining the "high" budget protection guardrail).
     - **Tier 7:** 0 candidates fallback.
   - Update `build_summary()` to check `relaxed_filters` and state the scope clearly (e.g., *"Top 5 recommendations within 5 km of Indiranagar"*).
2. **Update LLM Prompt Context (`backend/app/llm/prompts.py`)**:
   - When location expansion occurred, append a note to the user prompt so explanations accurately cite the restaurant's actual locality.
3. **Resilience & Regression Tests (`backend/tests/test_resilience.py`)**:
   - Add tests verifying the expansion tiers and `relaxed_filters` flags.

### Step 5: Frontend UI Communication
1. **Update `frontend/src/pages/RecommendPage.tsx`**:
   - Replace `recResponse.relaxed_filters.join(', ')` with a friendly formatter:
     - `"Note: To find great matches, we expanded your search within 5 km of [Location]."`
     - `"Note: To find great matches, we expanded your search within 10 km of [Location] and relaxed optional amenity filters."`
2. **Visual Check**:
   - Verify the alert banner renders cleanly and highlights the expanded radius.

### Step 6: End-to-End Verification
1. Run backend test suite:
   ```powershell
   pytest backend/tests
   ```
2. Test queries through the API and frontend:
   - Strict match query (e.g., popular cuisine in Koramangala) → confirm `relaxed_filters: []`.
   - Sparse query needing expansion (e.g., specific cuisine with 0 results in selected neighborhood) → confirm 5 km expansion and banner display.
   - Broad area query (e.g., `"Central Bangalore"`) → confirm radius expansion is skipped and exact matching applies.

