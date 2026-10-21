# DineMate Evaluation

How to judge whether DineMate works, using the phase exit criteria and definition of done in [`implementation-plan.md`](./implementation-plan.md).

Eval follows the same rule as the build: **filters are scored in code; the LLM is scored on ranking and explanations of an already-legal shortlist.** Do not treat a pretty explanation as a pass if the restaurant violates location, budget, cuisine, or minimum rating.

Related docs: [`architecture.md`](./architecture.md), [`edge-case.md`](./edge-case.md), [`problemStatement.md`](./problemStatement.md).

---

## 1. What “good” means

From implementation-plan Phase 8 and the project definition of done:

| # | Criterion | Pass if |
| --- | --- | --- |
| 1 | Real dataset | Names on screen exist in the ingested Hugging Face catalog (e.g. Jalsa), not a mocked list |
| 2 | Preferences narrow candidates | Changing location / budget / cuisine changes the list; every returned row satisfies hard filters (unless `relaxed_filters` is non-empty and shown) |
| 3 | Ranked justifications | Ordered list of ≤5 items, each with a 1–2 sentence reason; `source` is `"llm"` when a key works, or `"heuristic"` with a visible label when it does not |
| 4 | Scannable UI | Each card shows name, cuisine, rating, estimated cost, explanation |

**Assignment bar (brief):** at least one successful run with `source: "llm"` on the gold happy-path query. Heuristic-only is a resilience pass, not a full engine pass (implementation Phase 4 exit criteria).

---

## 2. Eval layers

| Layer | When | Method | Data |
| --- | --- | --- | --- |
| Unit | Phases 1–4 | pytest | Fixture catalog (20–30 rows) |
| Service | Phases 3–4 | pytest + optional live LLM | Fixture + one live gold query |
| API | Phase 5 | HTTP tests or curl | Fixture or full SQLite |
| UI | Phases 6–8 | Manual checklist | Full catalog |
| Quality | Phase 8 | Gold queries + explanation rubric | Full catalog |

Automated tests never need all ~51k rows. Live quality eval does.

---

## 3. Gold queries

Use the same defaults as the plan: K = 12, N = 5, budget ≤400 / 401–800 / ≥801, geography = catalog neighborhoods.

### 3.1 Required queries

| ID | Location | Budget | Cuisine | Min rating | Extras | Intent |
| --- | --- | --- | --- | --- | --- | --- |
| GQ-1 | Banashankari | medium | North Indian | 4.0 | (none) | Happy path (README sample) |
| GQ-2 | Banashankari | medium | Italian | 4.0 | (none) | Phase 2 exit query |
| GQ-3 | Indiranagar (or another facet city/neighborhood) | medium | North Indian | 4.0 | (none) | Preference sensitivity vs GQ-1 |
| GQ-4 | Banashankari | low | North Indian | 4.0 | (none) | Budget sensitivity vs GQ-1 |
| GQ-5 | Banashankari | medium | Chinese | 4.0 | (none) | Cuisine sensitivity vs GQ-1 |
| GQ-6 | Banashankari | medium | North Indian | 4.5 | family-friendly | Tighter rating + extras |
| GQ-7 | Banashankari | high | Martian | 4.0 | (none) | Empty / no invented venues |
| GQ-8 | Banashankari | low | Italian | 4.8 | quick service | Over-constrained → empty or honest relaxation |

If a listed neighborhood is missing from `/api/meta/options`, substitute another real facet value and note it in the eval log.

### 3.2 Constraint oracle

After each recommend call, for every item in `recommendations` (when `relaxed_filters` is empty):

1. `neighborhood == location` OR `listed_city == location`
2. `cost_for_two` in the requested band (null cost must not appear)
3. Requested cuisine is in the restaurant’s cuisine list (case-insensitive)
4. `rating >= min_rating` (null rating must not appear)
5. `id` / name exists in SQLite
6. List length ≤ 5
7. Display fields present: name, cuisines, rating, estimated_cost, explanation

If `relaxed_filters` is set, skip the relaxed dimension(s) and fail the case if the UI/API does not advertise the change.

**Hard-filter pass rate** = share of gold queries (GQ-1–GQ-6) where 100% of returned rows satisfy 1–7.

Target: **100%** on GQ-1–GQ-6 when results are non-empty.

---

## 4. Phase gates

Each implementation-plan phase is an eval gate. Do not score later phases if an earlier gate fails.

### Phase 0 — Foundation

| Check | Pass |
| --- | --- |
| `GET /health` | `{ "status": "ok" }` |
| Vite app starts | Placeholder renders |
| Secrets | `.env` gitignored; `.env.example` has no real keys |

### Phase 1 — Ingest

| Check | Pass |
| --- | --- |
| Source | `ManikaSaini/zomato-restaurant-recommendation` |
| Sample name | Catalog contains a real venue (e.g. Jalsa) |
| Types | Ratings numeric or null; costs int or null |
| Locations | Distinct values are Bangalore neighborhoods / listing areas, not a hardcoded Delhi list |
| PII | Phone not in served tables |
| Dedup | Duplicate name+address collapsed (spot-check) |
| Parsers | Unit tests: `"4.1/5"`, `"NEW"`, `"1,200"` |

**Metric:** ingest summary printed (rows in, rows out, distinct locations, distinct cuisines).

### Phase 2 — Filters

Run on the fixture DB, then spot-check GQ-2 on the full DB.

| Check | Pass |
| --- | --- |
| Isolation | Each of location, budget, cuisine, min rating removes the intended rows |
| Boundaries | 400 low, 401 medium, 800 medium, 801 high |
| Cap | ≤ 12 candidates even when many match |
| Empty | Zero-match fixture query returns `[]` |
| Facets | Options come from the catalog |

**Metric:** `candidate_count ≤ 12`; constraint oracle on the shortlist (not only the top 5).

### Phase 3 — Heuristic engine

| Check | Pass |
| --- | --- |
| Shape | query, candidate_count, relaxed_filters, summary, recommendations, `source: "heuristic"` |
| Fields | name, cuisine, rating, cost, explanation on each item |
| Order | Descending pre-rank score `rating_or_0 * log(1 + votes)` |
| Empty | Empty preferences/filters → empty list, no crash |
| Validation | Unknown budget / negative rating → error |

### Phase 4 — LLM ranker

| Check | Pass |
| --- | --- |
| GQ-1 with key | `source: "llm"`, ≤5 items, 1–2 sentence explanations |
| No key | Heuristic, no crash |
| Hallucinated id | Dropped (unit test with fake JSON) |
| Fake price/rating in JSON | Catalog values win |
| Invalid JSON | Heuristic |
| Prompt | Only allowlisted candidate fields; not full `reviews_list` |
| Cost | One recommend ≈ one LLM call on ≤12 candidates |

**Metric:** hallucination rate = invalid ids / ids returned by the model. Target **0** after the mapper.

### Phase 5 — API

| Check | Pass |
| --- | --- |
| `GET /api/meta/options` | Locations and cuisines from catalog |
| `POST /api/recommend` GQ-1 | 200, ≤5 items, required fields |
| Bad budget | 422 |
| GQ-7 | 200 and `[]` (or relaxation payload, not 500) |
| `/health` | Does not need `LLM_API_KEY` |
| Missing DB | Clear “run ingest first” |

### Phase 6 — UI

Manual (implementation-plan demo checkpoint: browser, not curl).

| Check | Pass |
| --- | --- |
| Form | Location/cuisine from options; budget hints; min rating; extras; Bangalore note |
| GQ-1 | Cards show five required fields |
| Loading | Spinner while waiting |
| Empty | Copy suggests widening budget or dropping cuisine |
| Keys | Network tab: no LLM provider calls from the browser |

### Phase 7 — Resilience

| Check | Pass |
| --- | --- |
| Over-constrained (GQ-8) | Empty + suggestions **or** results with `relaxed_filters` set and a banner |
| LLM off | 200 heuristic + UI notice |
| API down | Toast; not a blank page |
| No silent change | `query` still echoes the original preferences |

### Phase 8 — Assignment done

All four success-criterion proofs in implementation-plan Phase 8:

1. Ingest log + SQLite + names on screen  
2. Two locations (GQ-1 vs GQ-3) → different lists; logs show filter counts  
3. Justifications present (LLM or labeled heuristic)  
4. Five fields visible on each card  

Plus README: ingest, `.env`, run API, run UI, sample GQ-1.

---

## 5. LLM explanation rubric (human, GQ-1 and GQ-6)

Score each of the N cards. Use only when `source: "llm"`.

| Score | Grounding | Fit | Tone |
| --- | --- | --- | --- |
| 2 | Uses catalog facts (cuisine, area, price band, rating, dishes) without new numbers | Clearly tied to this user’s constraints | 1–2 sentences, no “open now” |
| 1 | Mostly relevant but generic (“great food”) | Partial fit (ignores budget or extras) | Too long or fluffy |
| 0 | Invented price/rating/amenity, or wrong cuisine/area | Could apply to any restaurant | Live availability claims |

**Pass:** mean grounding ≥ 1.5 and **zero** score-0 grounding on GQ-1.

Heuristic templates are not scored on this rubric; they only need to be labeled `heuristic` and factually consistent with catalog fields.

**Summary (optional in the brief):** if present, it should mention location + cuisine or budget; if absent, Phase 6 still passes.

---

## 6. Ranking eval (lightweight)

This project is not a retrieval benchmark. Use these only as sanity checks.

| Check | Method | Pass |
| --- | --- | --- |
| Shortlist legality | Constraint oracle on K candidates **before** the LLM | 100% |
| LLM set ⊂ shortlist | All returned ids in the K set | 100% |
| Preference sensitivity | GQ-1 vs GQ-3, GQ-4, GQ-5 | At least two of three pairs have different name sets |
| Heuristic order | Fixture with known scores | Exact order match |
| LLM order | Not required to match heuristic | Allowed to differ; still legal |

Do not fail the assignment because the model ranked #2 over #1 versus the vote formula.

---

## 7. Performance and cost (Phase 4 / 8)

| Metric | Target |
| --- | --- |
| LLM calls per recommend | 1 (0 on heuristic fallback) |
| Candidates in prompt | ≤ 12 |
| Filter latency | Logged; should be << LLM latency |
| LLM timeout | ~20s, one retry on 5xx |
| End-to-end UI (GQ-1) | Completes without a client timeout; spinner visible |

No SLA number is in the implementation plan; treat timeout/retry compliance as the gate.

---

## 8. Eval log template

Copy per gold query (Phase 8).

```text
Query ID:
Preferences:
candidate_count:
source: llm | heuristic
relaxed_filters:
N returned:
Constraint oracle: PASS / FAIL (notes)
Hallucinated ids dropped: n
UI five fields: PASS / FAIL
Explanation rubric (if llm): mean grounding / any 0s
Latency filter_ms / llm_ms
```

Store filled logs under a local notes folder if you want a paper trail; they are not required in git.

---

## 9. Recommended eval sequence

Matches implementation-plan cadence:

1. **After Phase 1:** ingest summary + Jalsa (or equivalent) in SQLite  
2. **After Phase 2:** fixture filter tests + GQ-2 shortlist on full DB  
3. **After Phase 3:** GQ-1 heuristic JSON shape  
4. **After Phase 4:** GQ-1 live LLM + mapper unit tests  
5. **After Phase 5:** curl options + recommend + 422  
6. **After Phase 6:** browser GQ-1 / empty  
7. **After Phase 7:** GQ-8 + LLM-off  
8. **Phase 8:** GQ-1–GQ-8 table + four success proofs  

---

## 10. Fail conditions (automatic no-go)

Any one of these fails the project eval, even if the UI looks fine:

- Results are hardcoded / mocked names not in the catalog  
- A card violates hard filters while `relaxed_filters` is empty  
- LLM output is shown with an invented id, price, or rating  
- Full catalog or full `reviews_list` sent to the model  
- Browser holds the LLM API key  
- Empty or error paths crash or render a blank page  
- No ingest path documented  

---

## 11. Out of scope for scoring

Do not score (implementation-plan v1 non-goals):

- Booking, payments, maps, accounts  
- Delhi or other cities absent from the snapshot  
- Fine-tuned model quality  
- Being a better ranker than Zomato’s production system
