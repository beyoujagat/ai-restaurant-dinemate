# Dine❤️Mate

> **AI-Powered Restaurant Recommendation Service**  
> Built with real Zomato Bangalore catalog data, deterministic candidate filtering, verified geo-proximity expansion, and LLM-powered natural-language reasoning.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646cff.svg)](https://vitejs.dev/)
[![Tests](https://img.shields.io/badge/Tests-135%20passed-brightgreen.svg)]()
[![Lint](https://img.shields.io/badge/Oxlint-0%20warnings-brightgreen.svg)]()
[![Build](https://img.shields.io/badge/Build-passing-brightgreen.svg)]()

---

## Overview

DineMate solves restaurant discovery by adhering to the core architectural principle: **filter first in code, then reason with an LLM**.

Instead of blowing token budgets and hallucinating venues by sending tens of thousands of catalog records into an LLM prompt, DineMate applies deterministic hard constraints (neighborhood location, budget tier in INR, cuisine containment, and minimum ratings) across a 51,000+ restaurant dataset in SQLite. Only a compact candidate shortlist ($K \le 12$) is sent to the LLM (Groq / Llama 3.3 or GPT) to rank and generate personalized, natural-language justifications.

If the LLM is unconfigured, times out, or errors, DineMate gracefully falls back to a deterministic heuristic engine ($rating \times \log(1 + votes)$) with honest status indicators—ensuring zero downtime.

When a strict local search yields zero matches, DineMate does not hallucinate or silently substitute venues from other areas. Instead, it provides an **honest empty-results interface** with verified nearby neighbourhood suggestions and an **explicit nearby search action** that searches adjacent neighbourhoods within 10 km while strictly preserving the diner's selected cuisine, budget, and minimum rating.

---

## System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       React + Vite UI                       │
│  - Playful 3D Food Aesthetic & Warm Food Mood Board Palette │
│  - Dynamic Facets from Catalog (93 Bangalore Neighborhoods) │
│  - Informational Nearby Badges & Approximate Distances      │
│  - Honest Empty State with Explicit "Search Nearby" Button  │
│  - 5 Visible Fields: Name, Cuisine, Rating, Cost, Rationale │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                      FastAPI Application                    │
│  - GET  /health              (Liveness Check)               │
│  - GET  /api/meta/options    (Catalog-Driven Facets)        │
│  - GET  /api/meta/nearby     (Verified Proximity Lookups)   │
│  - POST /api/recommend       (Filter + Rank Orchestrator)   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼─────────────┐ ┌──────────────▼───────────────┐
│     SQLite Catalog DB      │ │       LLM Ranker Layer       │
│  - Deduplicated Zomato Data│ │  - Structured JSON Output    │
│  - 51k+ Records, 93 Areas  │ │  - ID-Allowlist Enforcement  │
│  - Indexed on neighborhood,│ │  - Contextual Locality Notes │
│    rating, cost, city      │ │  - Heuristic Fallback Engine │
└──────────────┬─────────────┘ └──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────┐
│                    Geo Proximity Engine                     │
│  - Committed static lookup: neighbourhood_coords.json       │
│  - Pure-Python Haversine Distance: R = 6371.0 km            │
│  - Bangalore Bounding Box Validation: 12.7–13.2°N, 77.4–77.9│
│  - 88 Verified Localities; 5 Gated Regional Zones           │
└─────────────────────────────────────────────────────────────┘
```

---

## Verified Geo-Proximity & Nearby Search

DineMate includes a complete, self-contained geographic proximity engine designed specifically for the Bangalore metropolitan area:

### 1. Strict Search First & Honest Empty States
- **No Silent Expansion:** When a diner searches for a specific cuisine and budget in a locality (e.g. low-budget Assamese in Indiranagar), DineMate **never** silently returns restaurants from distant neighbourhoods without user consent.
- **Informational Nearby Badges:** The empty-results view displays verified neighbouring localities within 5 km and 10 km as non-interactive informational labels displaying straight-line distances (e.g. `Domlur (1.2 km)`, `Ulsoor (1.8 km)`). Misleading clickable chips that would silently switch the location without preserving context have been removed.
- **Explicit User Action:** Diners can click **`📍 Search Nearby Locations (within 10 km)`** to actively broaden their search.

### 2. Strict Filter Preservation
When an explicit nearby search is triggered (`include_nearby: true`):
- **Cuisine Containment:** Strictly preserved (case-insensitive substring containment).
- **Budget Invariance:** Low budget ($\le ₹400$), medium budget ($₹401–₹800$), and high budget ($\ge ₹801$) constraints are strictly maintained. Premium dining intent ("high" budget) is never downgraded.
- **Rating Guardrails:** Minimum rating thresholds (e.g. $4.0+$ or $4.5+$) continue to be strictly enforced; null-rated venues are excluded.
- **Distance Attribution:** Every recommendation returned via geo-expansion displays its locality and approximate distance (e.g. `Domlur (~1.2 km away)`), both on the venue card badge and in the natural-language explanation.

### 3. Coordinate Validation & Bounding Box Checks
- All coordinates are validated against the strict Bangalore metropolitan bounding box:
  $$12.7^\circ\text{N} \le \text{Latitude} \le 13.2^\circ\text{N}, \quad 77.4^\circ\text{E} \le \text{Longitude} \le 77.9^\circ\text{E}$$
- Great-circle distance is calculated using the pure-Python Haversine formula ($R = 6371.0\text{ km}$):
  $$\Delta\sigma = 2 \arcsin\sqrt{\sin^2\left(\frac{\Delta\phi}{2}\right) + \cos\phi_1 \cos\phi_2 \sin^2\left(\frac{\Delta\lambda}{2}\right)}$$
- **88 Verified Localities:** All major dining hubs, including BTM Layout (`12.9140, 77.6103`), HSR Layout (`12.9116, 77.6389`), Koramangala (`12.9357, 77.6241`), Vijay Nagar (`12.9710, 77.5374`), Sanjay Nagar (`13.0295, 77.5785`), Thippasandra (`12.9739, 77.6510`), Sadashiv Nagar (`13.0110, 77.5809`), Rammurthy Nagar (`13.0120, 77.6778`), and ITPL Main Road Whitefield (`12.9870, 77.7364`) are validated against authoritative OpenStreetMap Nominatim suburb/landmark centroids.
- **5 Gated Regional Zones:** Non-specific macro-regions (`Central Bangalore`, `East Bangalore`, `North Bangalore`, `South Bangalore`, `West Bangalore`) are marked with `broad_area: true, verified: false`. They are excluded from radius matching to prevent arbitrary quadrant anchoring; exact matching applies.

---

## Prerequisites

- **Python**: 3.10 or newer (tested on Python 3.15)
- **Node.js**: 18 or newer & **npm**

---

## Quickstart Guide

### 1. Catalog Ingestion (**REQUIRED FIRST STEP**)

Before starting the web application or running integration tests, you **must ingest and build the local catalog** from Hugging Face (`ManikaSaini/zomato-restaurant-recommendation`).

1. Navigate to the `backend/` directory and activate your virtual environment:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   *(On macOS / Linux: `source .venv/bin/activate`)*

2. Run the catalog ingestion pipeline:
   ```powershell
   python -m app.catalog.ingest
   ```

   **What this does:**
   - Downloads/streams the raw 51,717-row dataset from Hugging Face.
   - Cleans numeric ratings (`"4.1/5"` $\rightarrow$ `4.1`, `"NEW"`/`"-"` $\rightarrow$ `null`).
   - Normalizes INR costs for two (`"800"`, `"1,200"` $\rightarrow$ `800`, `1200`).
   - Normalizes and splits comma-separated cuisines.
   - Deduplicates identical restaurants across multiple Zomato listing types by `(normalized name, address)`.
   - Strips PII (phone numbers and uncurated reviews are discarded).
   - Generates indexed `data/processed/restaurants.sqlite` and `restaurants.parquet`.

---

### 2. Configure Environment (`.env`)

Copy the example environment configuration in the project root:

```powershell
Copy-Item .env.example .env
```
*(On macOS / Linux: `cp .env.example .env`)*

Configure your `.env` settings:
```ini
CATALOG_DB_PATH=data/processed/restaurants.sqlite
HF_DATASET=ManikaSaini/zomato-restaurant-recommendation

# LLM Provider — Groq (https://console.groq.com/keys) or OpenAI-compatible
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_your_api_key_here
LLM_MODEL=llama-3.3-70b-versatile

CANDIDATE_LIMIT=12
RESULT_LIMIT=5
BUDGET_LOW_MAX=400
BUDGET_MEDIUM_MAX=800
```

> [!NOTE]
> If `LLM_API_KEY` is omitted or invalid, DineMate will operate in **Heuristic Fallback Mode**. All recommendations will be computed deterministically with full explanations and labeled accordingly in the UI.

---

### 3. Run the Backend API

From `backend/` with the virtual environment active:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify backend health:
- Liveness check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) returns `{"status":"ok"}`
- Catalog facets: [http://127.0.0.1:8000/api/meta/options](http://127.0.0.1:8000/api/meta/options)
- Verified nearby lookups: [http://127.0.0.1:8000/api/meta/nearby?location=Indiranagar&radius_km=5.0](http://127.0.0.1:8000/api/meta/nearby?location=Indiranagar&radius_km=5.0)

---

### 4. Run the Frontend Web UI

In a separate terminal, navigate to `frontend/`:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your web browser.

---

## Canonical Sample Queries

### 1. Strict Local Match
- **Location**: `Banashankari`
- **Budget**: `medium` (₹401–₹800 for two)
- **Cuisine**: `North Indian`
- **Minimum Rating**: `4.0`

**Result:** Returns top-rated venues strictly in Banashankari (e.g. *Jalsa*). `relaxed_filters: []`.

### 2. Explicit Nearby Search Expansion
- **Location**: `Indiranagar`
- **Budget**: `low` ($\le ₹400$ for two)
- **Cuisine**: `Assamese`
- **Action**: Initial search yields 0 candidates in Indiranagar. Clicking **`Search Nearby Locations (within 10 km)`** executes `include_nearby: true`.

**Result:** Returns *Taste of Assam* in Koramangala 4th Block (~4.7 km away) at ₹400 for two with rating 3.3★. Notice banner: `"Note: To find great matches, we expanded your search within 5 km of Indiranagar."` and card displays `(~4.7 km away)`.

---

## Testing & Quality Assurance

### Run Backend Test Suite (135 tests)
```powershell
cd backend
.\.venv\Scripts\pytest -v
```

The test suite covers:
- **Phase 1 Ingest (`test_ingest.py`)**: Parsers for rate/cost/cuisines/votes, deduplication, SQLite persistence.
- **Phase 2 Filters (`test_filters.py`)**: Location, budget boundaries (400, 401, 800, 801), cuisine containment, rating thresholds, candidate limit capping.
- **Phase 3 Heuristic Engine (`test_recommend_service.py`)**: Fallback scoring ($rating \times \log(1+votes)$), deterministic ordering, template explanations.
- **Phase 4 LLM Ranker (`test_llm_ranker.py`)**: Prompt packing (allowlisted fields only), ID hallucination rejection, catalog value preservation.
- **Phase 5 HTTP API (`test_api.py`)**: Endpoint validation, 422 error codes, facet options, query echo, and `/api/meta/nearby` radius parameter handling (respects custom radius, negative/zero safety, subset property).
- **Core Geo Engine (`test_geo.py`)**: Pure-Python Haversine distance accuracy, symmetry, bounding box checks, gating rules, coordinate verification for BTM, HSR, Koramangala, Vijay Nagar, Sanjay Nagar, Thippasandra, ITPL Main Road, Rammurthy Nagar, and Sadashiv Nagar.
- **Resilience & Ladder (`test_resilience.py`)**: Extras relaxation, budget widening, and error tolerance.
- **Step 6 & E2E Verification (`test_step6_verification.py`, `test_phase8_e2e.py`)**: End-to-end multi-tier expansion on real catalog data, high-budget guardrails, UI contracts, and filter preservation on explicit nearby search.

### Run Frontend Lint & Production Build
```powershell
cd frontend
npm run lint
npm run build
```
- **Lint Check (`oxlint`)**: Passed with **0 warnings and 0 errors** across all source files.
- **Production Build (`tsc -b && vite build`)**: Clean build output generated in `< 200 ms`.

---

## Success Criteria Verification

| # | Criterion | How DineMate Proves It | Status |
|---|---|---|:---:|
| 1 | **Real Dataset Records** | Queried from `restaurants.sqlite` derived from Hugging Face; real Bangalore venues (e.g., Jalsa, Onesta, Truffles); no mocked arrays. | ✅ Verified |
| 2 | **Preferences Narrow Candidates** | Code filters in `filters.py` reduce 51k+ rows to $\le 12$ candidates before ranking; different inputs yield distinct candidate shortlists. | ✅ Verified |
| 3 | **Ranked Recs with Justifications** | Every result includes an ordered rank and specific natural-language justification (LLM or labeled heuristic). | ✅ Verified |
| 4 | **Scannable UI** | Cards render the 5 required fields (Name, Cuisines, Rating/Votes, Cost for two, Explanation) + Zomato link. | ✅ Verified |
| 5 | **Verified Nearby Expansion** | Proximity engine discovers adjacent dining spots within 10 km while preserving cuisine, budget, and minimum rating. | ✅ Verified |

---

## Current Scope & Limitations (Honest Documentation)

- **Local Verification Status:** All 135 tests, frontend linting, and production builds are verified in the local development environment. Documentation does not represent or claim that any third-party remote cloud deployment (e.g., Railway/Vercel) has been redeployed.
- **Straight-Line vs Road Routing:** Distances are calculated using the great-circle Haversine formula (straight-line distance). Actual driving times and road travel distances in Bangalore traffic will vary.
- **Broad Regional Zones:** Non-specific areas (`Central Bangalore`, `East Bangalore`, `North Bangalore`, `South Bangalore`, `West Bangalore`) are intentionally gated from automatic radius expansion to avoid arbitrary centroid anchoring.
- **Explicit Non-Goals:** Live reservation booking systems, payment checkout, GPS turn-by-turn navigation, and multi-city catalogs outside Bangalore remain out of scope.

---

## Repository Structure

```text
ai-restaurant-dinemate/
├── docs/
│   ├── problemStatement.md              # Original project specifications
│   ├── architecture.md                  # Complete system architecture design
│   ├── implementation-plan.md           # Phased step-by-step implementation guide
│   └── geo_proximity_plan.md            # Geo-proximity specifications & relaxation ladder
├── data/
│   ├── raw/                             # Raw Hugging Face dataset cache
│   └── processed/
│       ├── restaurants.sqlite           # Cleaned and indexed SQLite catalog
│       ├── restaurants.parquet          # Compressed Parquet catalog
│       └── neighbourhood_coords.json    # Static verified coordinates lookup (88 verified)
├── backend/
│   ├── app/
│   │   ├── main.py                      # FastAPI app and CORS configuration
│   │   ├── api/routes.py                # Endpoints (/health, /api/meta/options, /api/meta/nearby, /api/recommend)
│   │   ├── domain/                      # Pydantic schemas (Preference, Restaurant, Budget)
│   │   ├── catalog/
│   │   │   ├── geo.py                   # Pure-Python Haversine distance & coordinate gating
│   │   │   ├── store.py                 # SQLite store & multi-location querying
│   │   │   ├── filters.py               # Candidate filters & scoring pipeline
│   │   │   └── ingest.py                # Pipeline for Hugging Face catalog
│   │   ├── llm/                         # LLM client, prompt builder, schema validators
│   │   └── services/                    # Recommendation orchestration & relaxation ladder
│   ├── scripts/
│   │   └── geocode_neighbourhoods.py    # Offline OSM Nominatim geocoding script
│   ├── tests/                           # 135 unit, integration, geo, and E2E pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── EmptyState.tsx           # Honest empty state, informational badges & search action
│   │   │   ├── RecommendationCard.tsx   # Venue card with approximate distance badge
│   │   │   ├── PreferenceForm.tsx       # Interactive query filters
│   │   │   └── WelcomeModal.tsx
│   │   ├── pages/                       # RecommendPage (main interactive workspace)
│   │   ├── api/client.ts                # Typed API client for FastAPI backend
│   │   ├── App.css                      # Styling, animations, non-interactive badges
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── .env.example                         # Example configuration template
└── README.md                            # Project documentation
```
