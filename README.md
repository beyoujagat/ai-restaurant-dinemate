# Dine❤️Mate

> **AI-Powered Restaurant Recommendation Service**  
> Built with real Zomato Bangalore catalog data, deterministic candidate filtering, and LLM-powered natural-language reasoning.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646cff.svg)](https://vitejs.dev/)
[![Tests](https://img.shields.io/badge/Tests-84%20passed-brightgreen.svg)]()

---

## Overview

DineMate solves restaurant discovery by adhering to the core architectural principle: **filter first in code, then reason with an LLM**. 

Instead of blowing token budgets and hallucinating venues by sending tens of thousands of catalog records into an LLM prompt, DineMate applies deterministic hard constraints (neighborhood location, budget tier in INR, cuisine containment, and minimum ratings) across a 51,000+ restaurant dataset in SQLite. Only a compact candidate shortlist ($K \le 12$) is sent to the LLM (Groq / Llama 3.3 or GPT) to rank and generate personalized, natural-language justifications.

If the LLM is unconfigured, times out, or errors, DineMate gracefully falls back to a deterministic heuristic engine ($rating \times \log(1 + votes)$) with honest status indicators—ensuring zero downtime.

---

## System Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                       React + Vite UI                       │
│  - Playful 3D Food Aesthetic & Warm Food Mood Board Palette │
│  - Dynamic Facets from Catalog (93 Bangalore Neighborhoods) │
│  - 5 Visible Fields: Name, Cuisine, Rating, Cost, Rationale │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                      FastAPI Application                    │
│  - GET  /health              (Liveness Check)               │
│  - GET  /api/meta/options    (Catalog-Driven Facets)        │
│  - POST /api/recommend       (Filter + Rank Orchestrator)   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼─────────────┐ ┌──────────────▼───────────────┐
│     SQLite Catalog DB      │ │       LLM Ranker Layer       │
│  - Deduplicated Zomato Data│ │  - Structured JSON Output    │
│  - Indexed on neighborhood,│ │  - ID-Allowlist Enforcement  │
│    rating, cost, city      │ │  - Heuristic Fallback Engine │
└────────────────────────────┘ └──────────────────────────────┘
```

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

## Canonical Sample Query

To demonstrate the full end-to-end pipeline, run the canonical query specified in the problem statement:

- **Location**: `Banashankari` (Bangalore)
- **Budget**: `medium` (₹401–₹800 for two)
- **Cuisine**: `North Indian`
- **Minimum Rating**: `4.0`

### Via Web UI
1. Open [http://localhost:5173](http://localhost:5173).
2. Select **Banashankari** from the location dropdown.
3. Choose **Medium (₹401–₹800)** budget.
4. Select **North Indian** from cuisines (or click the North Indian quick chip).
5. Set minimum rating to **4.0+**.
6. Click **Find My Perfect Spots**.

### Via HTTP API (`curl`)
```bash
curl -X POST "http://127.0.0.1:8000/api/recommend" \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Banashankari",
    "budget": "medium",
    "cuisine": "North Indian",
    "min_rating": 4.0
  }'
```

### Result Shape
```json
{
  "query": {
    "location": "Banashankari",
    "budget": "medium",
    "cuisine": "North Indian",
    "min_rating": 4.0,
    "extras": null
  },
  "candidate_count": 12,
  "relaxed_filters": [],
  "summary": "Best North Indian dining options in Banashankari matching your criteria.",
  "source": "llm",
  "recommendations": [
    {
      "id": "e445aa42d8f780e9",
      "rank": 1,
      "name": "Jalsa",
      "cuisines": ["North Indian", "Mughlai", "Chinese"],
      "rating": 4.1,
      "votes": 780,
      "estimated_cost": 800,
      "neighborhood": "Banashankari",
      "explanation": "Jalsa offers a standout North Indian and Mughlai feast with an authentic royal dining experience priced right at ₹800 for two.",
      "url": "https://www.zomato.com/bangalore/jalsa-banashankari"
    }
  ]
}
```

Each recommendation card displays all **5 required fields**:
1. **Restaurant Name** (`Jalsa`)
2. **Cuisines** (`North Indian, Mughlai, Chinese`)
3. **Rating & Review Votes** (`★ 4.1 (780 votes)`)
4. **Estimated Cost for Two** (`₹800 for two`)
5. **AI Rationale / Justification** (Natural-language 1–2 sentence explanation)

---

## Testing & Quality Assurance

### Run Backend Unit & Integration Tests (84 tests)
```powershell
cd backend
.\.venv\Scripts\pytest -v
```

The test suite covers:
- **Phase 1 Ingest**: Parsers for rate/cost/cuisines/votes, deduplication, SQLite persistence.
- **Phase 2 Filters**: Location, budget boundaries (400, 401, 800, 801), cuisine containment, rating thresholds, candidate limit capping.
- **Phase 3 Heuristic Engine**: Fallback scoring ($rating \times \log(1+votes)$), deterministic ordering, template explanations.
- **Phase 4 LLM Ranker**: Prompt packing (allowlisted fields only), ID hallucination rejection, catalog value preservation.
- **Phase 5 HTTP API**: Endpoint validation, 422 error codes, facet options, query echo.
- **Phase 7 Resilience**: Filter relaxation (drops extras first, widens budget by one band), in-memory demo cache, graceful error handling.
- **Phase 8 Verification**: End-to-end tests for all 4 primary success criteria, canonical query, and schema validation.

### Run Frontend Lint & Production Build
```powershell
cd frontend
npm run lint
npm run build
```

---

## Success Criteria Verification

| # | Criterion | How DineMate Proves It | Status |
|---|---|---|:---:|
| 1 | **Real Dataset Records** | Queried from `restaurants.sqlite` derived from Hugging Face; real Bangalore venues (e.g., Jalsa, Onesta, Truffles); no mocked arrays. | ✅ Verified |
| 2 | **Preferences Narrow Candidates** | Code filters in `filters.py` reduce 51k+ rows to $\le 12$ candidates before ranking; different inputs yield distinct candidate shortlists. | ✅ Verified |
| 3 | **Ranked Recs with Justifications** | Every result includes an ordered rank and specific natural-language justification (LLM or labeled heuristic). | ✅ Verified |
| 4 | **Scannable UI** | Cards render the 5 required fields (Name, Cuisines, Rating/Votes, Cost for two, Explanation) + Zomato link. | ✅ Verified |

---

## Explicit Non-Goals (Out of Scope for v1)

As specified in the architecture document, the following capabilities are explicitly out of scope:
- **Live Table Bookings**: No real-time reservation integration with third-party restaurant reservation systems.
- **Payment Processing**: No checkout, billing, or transaction processing.
- **Maps & Live GPS Navigation**: No embedded interactive mapping or routing APIs.
- **User Accounts & Auth**: No registration, passwords, session cookies, or saved bookmarks.
- **Multi-City Catalogs**: Dataset coverage is strictly Bangalore-centric based on the Hugging Face snapshot.

---

## Repository Structure

```text
ai-restaurant-dinemate/
├── docs/
│   ├── problemStatement.md      # Original project specifications
│   ├── architecture.md          # Complete system architecture design
│   └── implementation-plan.md   # Phased step-by-step implementation guide
├── data/
│   ├── raw/                     # Raw Hugging Face dataset cache
│   └── processed/               # Cleaned restaurants.sqlite & restaurants.parquet
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app and CORS configuration
│   │   ├── api/                 # Endpoints (/health, /api/meta/options, /api/recommend)
│   │   ├── domain/              # Pydantic schemas (Preference, Restaurant, Budget)
│   │   ├── catalog/             # Ingest pipeline, SQLite store, candidate filters
│   │   ├── llm/                 # LLM client, prompt builder, schema validators
│   │   └── services/            # Recommendation orchestration & relaxation policy
│   ├── tests/                   # 84 unit, integration, and E2E pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # PreferenceForm, RecommendationCard, WelcomeModal, etc.
│   │   ├── pages/               # RecommendPage (main interactive workspace)
│   │   ├── api/                 # Typed API client for FastAPI backend
│   │   ├── App.css              # Rich styling, animations, warm food mood board palette
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── .env.example                 # Example configuration template
└── README.md                    # Project documentation
```
