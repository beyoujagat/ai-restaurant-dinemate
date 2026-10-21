# DineMate — Production Deployment Plan
**Target Architecture:** FastAPI Backend on **Railway** · React/Vite Frontend on **Vercel**

---

## 1. Executive Summary & Architecture Overview

DineMate is structured as a monorepo containing:
- **`backend/`**: Python 3.10+ / FastAPI service serving `/health`, `/api/meta/options`, and `/api/recommend`.
- **`frontend/`**: React 19 + TypeScript + Vite 8 SPA.
- **`data/`**: Processed catalog database (`restaurants.sqlite` ~18.5 MB, currently gitignored).

```text
┌─────────────────────────────────┐
│     Vercel (React 19 SPA)       │
│  Root Directory: frontend/      │
│  VITE_API_BASE_URL = Railway    │
└────────────────┬────────────────┘
                 │ HTTPS
                 ▼
┌─────────────────────────────────┐
│     Railway (FastAPI / ASGI)    │
│  Port: $PORT (Dynamic)          │
│  CORS: Allowed Vercel Origin    │
│  DB: restaurants.sqlite         │
└────────────────┬────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐   ┌──────────────┐
│ SQLite DB    │   │ Groq API     │
│ (Catalog)    │   │ (Llama 3.3)  │
└──────────────┘   └──────────────┘
```

---

## 2. Pre-Deployment Code & Configuration Requirements

Before deploying, the following non-breaking configuration updates will be needed (planned, not executed yet):

### 2.1 Backend CORS Update (`backend/app/main.py`)
* **Current status:** Hardcoded to `localhost:5173`, `127.0.0.1:5173`, `localhost:3000`.
* **Required change:** Support environment-configured allowed origins and Vercel preview domains:
  ```python
  allowed_origins = [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:3000",
  ]
  env_origins = os.getenv("CORS_ORIGINS", "")
  if env_origins:
      allowed_origins.extend([origin.strip() for origin in env_origins.split(",") if origin.strip()])
  ```
  Additionally, enable regex matching `allow_origin_regex=r"https://.*\.vercel\.app"` so Vercel preview deployments function automatically without manual origin updates.

### 2.2 Backend Host & Port Binding for Railway
* Railway injects a dynamic `$PORT` environment variable (typically integer 8000+).
* Uvicorn must bind to `0.0.0.0` (not `127.0.0.1`) and listen on `$PORT`.
* Add a `Procfile` in `backend/` or repo root:
  ```text
  web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
  ```
* Or a `railway.json` at repo root defining the start command and build root.

### 2.3 SQLite Dataset Deployment Strategy on Railway
Because `data/processed/*.sqlite` is gitignored:
* **Option A (Recommended — Self-Bootstrapping Build):**
  Add a build/start check: If `data/processed/restaurants.sqlite` is not present, run `python -m app.catalog.ingest`.
  * *Ingestion stats:* ~51,700 rows from Hugging Face, completes in ~15–25 seconds.
  * *Start Command:*
    ```bash
    python -c "import os; os.path.exists('data/processed/restaurants.sqlite') or __import__('app.catalog.ingest').catalog.ingest.run_ingest()" && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
    ```
* **Option B (Railway Volume):**
  Mount a persistent Railway volume at `data/processed/` and run ingestion once via Railway CLI (`railway run python -m app.catalog.ingest`).
* **Option C (Commit to Git):**
  Un-ignore `data/processed/restaurants.sqlite` (18.5 MB is well below GitHub's 100 MB limit).

---

## 3. Environment Variables Specification

### 3.1 Backend (Railway Dashboard)

| Variable | Recommended Production Value | Required? | Purpose |
|---|---|:---:|---|
| `GROQ_API_KEY` | `gsk_...` | **Yes** | Groq Llama 3.3 inference key (falls back to heuristic if unset) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Optional | Default model |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Optional | Groq API endpoint |
| `CATALOG_DB_PATH` | `data/processed/restaurants.sqlite` | Optional | Path to SQLite catalog |
| `HF_DATASET` | `ManikaSaini/zomato-restaurant-recommendation` | Optional | Dataset repo |
| `CORS_ORIGINS` | `https://<your-vercel-app>.vercel.app` | **Yes** | Allows frontend to call API |
| `CANDIDATE_LIMIT` | `12` | Optional | Cap on candidate shortlist |
| `RESULT_LIMIT` | `5` | Optional | Final recommendation count |
| `BUDGET_LOW_MAX` | `400` | Optional | Price tier divider in INR |
| `BUDGET_MEDIUM_MAX` | `800` | Optional | Price tier divider in INR |

### 3.2 Frontend (Vercel Project Settings)

| Variable | Recommended Production Value | Required? | Purpose |
|---|---|:---:|---|
| `VITE_API_BASE_URL` | `https://<your-railway-app>.up.railway.app` | **Yes** | Points frontend client to Railway backend (**No trailing slash**) |

---

## 4. GitHub Setup & Push Protocol

### 4.1 Pre-Push Verification Checklist
- [x] Working tree clean (`master` branch).
- [x] `.env` is gitignored and untracked.
- [x] `.env.example` contains only blank template fields.
- [x] Processed database files and tarballs are untracked.

### 4.2 GitHub Push Steps
1. Create a new GitHub repository (e.g., `ai-restaurant-dinemate` or `dinemate`).
2. Add the remote and push:
   ```bash
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git branch -M main
   git push -u origin main
   ```

---

## 5. Deployment Order (Step-by-Step)

```text
Step 1: Push Code to GitHub
           │
           ▼
Step 2: Deploy Backend to Railway FIRST
           │ (Obtain Railway public URL, e.g. https://...up.railway.app)
           ▼
Step 3: Deploy Frontend to Vercel SECOND
           │ (Provide VITE_API_BASE_URL = Railway URL)
           │ (Obtain Vercel public URL, e.g. https://...vercel.app)
           ▼
Step 4: Update Backend CORS on Railway with Vercel Domain
           │
           ▼
Step 5: End-to-End Verification
```

### Phase 1: Deploy Backend to Railway (FIRST)
1. Log in to [Railway](https://railway.com/).
2. Click **New Project** → **Deploy from GitHub repo** → select the DineMate repo.
3. In **Settings**:
   * **Root Directory**: Leave as `/` (root) or set to `backend`.
   * If root: set **Build Command** to `pip install -r backend/requirements.txt`.
   * Set **Start Command** to:
     ```bash
     cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
     ```
4. In **Variables**, add:
   * `GROQ_API_KEY`
   * `CATALOG_DB_PATH` = `data/processed/restaurants.sqlite`
5. In **Networking**, click **Generate Domain** (e.g., `https://dinemate-backend-production.up.railway.app`).
6. Test backend health:
   ```bash
   curl https://<railway-domain>/health
   # Expected: {"status":"ok"}
   ```

### Phase 2: Deploy Frontend to Vercel (SECOND)
1. Log in to [Vercel](https://vercel.com/).
2. Click **Add New Project** → Import the DineMate GitHub repo.
3. In **Project Configuration**:
   * **Framework Preset**: Vite
   * **Root Directory**: `frontend` (Click *Edit* and select the `frontend` folder).
   * **Build Command**: `npm run build` (Default)
   * **Output Directory**: `dist` (Default)
   * **Install Command**: `npm install` (Default)
4. In **Environment Variables**:
   * Key: `VITE_API_BASE_URL`
   * Value: `https://<your-railway-domain>` (without trailing slash)
5. Click **Deploy**.
6. Note the deployed Vercel URL (e.g., `https://dinemate.vercel.app`).

### Phase 3: Finalize CORS on Railway
1. Return to the Railway project dashboard.
2. Under **Variables**, add/update:
   * `CORS_ORIGINS` = `https://<your-vercel-domain>.vercel.app`
3. Railway will automatically redeploy the backend with the new environment variable.

---

## 6. Verification & Acceptance Testing

After both services are live, verify the deployment:

### 1. Health Probe
```bash
curl -I https://<railway-domain>/health
# Expected: HTTP/2 200 OK, {"status":"ok"}
```

### 2. Catalog Facets Endpoint
```bash
curl https://<railway-domain>/api/meta/options
# Expected: JSON with 93 Bangalore neighborhoods, cuisines list, budget labels
```

### 3. Canonical Recommendation API Test
```bash
curl -X POST https://<railway-domain>/api/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Banashankari",
    "budget": "medium",
    "cuisine": "North Indian",
    "min_rating": 4.0
  }'
# Expected: 200 OK with candidate_count, source ("llm" or "heuristic"), recommendations array
```

### 4. Frontend Web UI Verification
1. Open `https://<your-vercel-app>.vercel.app` in your browser.
2. Confirm the **Location** dropdown populates with Bangalore neighborhoods (proves `GET /api/meta/options` is working across domains).
3. Run the canonical query:
   * **Location**: *Banashankari*
   * **Budget**: *Medium*
   * **Cuisine**: *North Indian*
   * **Rating**: *4.0+*
4. Confirm recommendation cards render with:
   - Restaurant Name
   - Cuisines
   - Rating & Votes
   - Estimated Cost for Two
   - Justification / Explanation
   - LLM / Heuristic status badge
5. Open browser DevTools Network tab: Verify all API calls go to `https://<railway-domain>/api/...` and return `200` with proper CORS headers (`Access-Control-Allow-Origin`).
