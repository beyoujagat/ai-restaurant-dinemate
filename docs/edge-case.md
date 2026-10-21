# DineMate Edge Cases

Corner cases and failure modes for DineMate, derived from [`architecture.md`](./architecture.md) and [`implementation-plan.md`](./implementation-plan.md).

Use this as a test and QA checklist. Expected behavior follows those docs unless a row says “decide.” Happy path (Banashankari, medium budget, North Indian, min 4.0 → five cards) is out of scope here.

**Conventions**

- **Hard filter:** location, budget, cuisine, minimum rating
- **Soft:** additional preferences (LLM / keyword boost)
- **K:** candidate cap (default 12)
- **N:** results shown (default 5)

---

## 1. Ingest and catalog data

Source: architecture §6; implementation Phase 1.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| ING-01 | `rate` is `"4.1/5"` | Store `rating = 4.1` |
| ING-02 | `rate` is `"NEW"`, `"-"`, empty, or missing | Store `rating = null`. Row is kept. |
| ING-03 | `rate` is junk (not `X/5`) | Treat as `null`; ingest does not crash |
| ING-04 | Cost is `"800"` | `cost_for_two = 800` |
| ING-05 | Cost is `"1,200"` | `cost_for_two = 1200` (comma stripped) |
| ING-06 | Cost missing | Keep the row; `cost_for_two = null`. Exclude from budget filters later |
| ING-07 | Cost junk / non-numeric | `null`; ingest continues |
| ING-08 | `cuisines` is `"North Indian, Mughlai, Chinese"` | List of trimmed names; extra spaces ignored |
| ING-09 | `cuisines` null or empty | Keep row; cuisine hard-filter will not match this row |
| ING-10 | `votes` missing, `"2,556"`, or non-int | Coerce to int or `0`; scoring still works |
| ING-11 | `online_order` / `book_table` mixed case (`Yes`/`No`) | Booleans; unexpected values → false or null (decide, then test) |
| ING-12 | Empty or whitespace `name` | Drop the row |
| ING-13 | Same name + address listed under Buffet and Cafes | One catalog row; `listed_types` / `rest_types` merged |
| ING-14 | Same name, different address | Two rows, two ids |
| ING-15 | Name differs only by case/spacing | Dedup on **normalized** name + address |
| ING-16 | `reviews_list` is huge (up to ~1.28M chars) | At most 2–3 short snippets in catalog; never send full text to the LLM |
| ING-17 | `phone` / full `menu_item` present in source | Not stored in the served catalog |
| ING-18 | Hugging Face download fails or dataset missing | Ingest exits with a clear error; no half-written DB presented as success |
| ING-19 | Ingest run twice | Idempotent replace (or documented overwrite); no duplicate inflation |
| ING-20 | Garbled names (encoding artifacts in source) | Stored as-is after ingest; UI must not crash on odd Unicode |
| ING-21 | `url` missing | `url = null`; cards skip the link |
| ING-22 | `dish_liked` null | Empty `dishes_liked`; extras keyword boost is a no-op for that row |

---

## 2. Preferences and validation

Source: architecture §7–8.1, §9; implementation Phases 3, 5.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| VAL-01 | Budget not in `low` \| `medium` \| `high` | 422; do not query the catalog |
| VAL-02 | `min_rating` negative | 422 |
| VAL-03 | `min_rating` > 5 | 422 or clamp (decide); do not return impossible matches silently |
| VAL-04 | `min_rating` omitted | Do not apply a rating floor; `null` ratings may appear |
| VAL-05 | Location omitted while treated as required | 422 |
| VAL-06 | Location omitted if allowed | Search without neighborhood/`listed_city` constraint |
| VAL-07 | Location `"delhi"` / `"Delhi"` | Not in catalog facets. UI should not offer it. API: empty list or 422 if unknown location (decide) |
| VAL-08 | Location case/spacing vs catalog (`banashankari`) | Case-insensitive match |
| VAL-09 | Cuisine `"italian"` vs `"Italian"` | Case-insensitive containment |
| VAL-10 | Cuisine with extra spaces | Trim before match |
| VAL-11 | Cuisine not in the catalog (e.g. `"Martian"`) | Empty shortlist (then empty or relaxed path), not a 500 |
| VAL-12 | Extra preferences empty | Skip tag mapping and keyword boost |
| VAL-13 | Extra preferences very long | Truncate before prompt; still apply known tags if present |
| VAL-14 | Extra preferences only unmapped prose (`"quiet rooftop"`) | Hard filters unchanged; text goes to the LLM |
| VAL-15 | Conflicting extras (`family-friendly` and nightlife) | Decide: family-friendly rule wins, or pass both to the LLM and do not hard-filter nightlife |

---

## 3. Filtering, scoring, and shortlist

Source: architecture §7.2–8.2; implementation Phase 2.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| FLT-01 | Cost exactly **400** | Included in **low** only |
| FLT-02 | Cost exactly **401** | **medium** only |
| FLT-03 | Cost exactly **800** | **medium** only |
| FLT-04 | Cost exactly **801** | **high** only |
| FLT-05 | `cost_for_two` is null and user set a budget | Exclude from budget filter (not guessed into a band) |
| FLT-06 | User set `min_rating`; restaurant `rating` is null | Exclude |
| FLT-07 | User did not set `min_rating`; rating is null | May appear; score uses rating `0` |
| FLT-08 | Cuisine is a substring of a longer cuisine name | Match on list membership / token, not accidental substring of another cuisine if avoidable (e.g. `"Cafe"` vs `"Cafe, Mexican"` is OK; `"Indian"` vs `"North Indian"` — decide and document) |
| FLT-09 | Restaurant has many cuisines; user picked one of them | Include |
| FLT-10 | Location matches `neighborhood` but not `listed_city` | Include (OR) |
| FLT-11 | Location matches `listed_city` but not `neighborhood` | Include (OR) |
| FLT-12 | Location matches neither | Exclude |
| FLT-13 | Extras `quick service` | Prefer / hard-filter `Quick Bites` per mapping |
| FLT-14 | Extras `family-friendly` | Prefer Casual Dining / Buffet; avoid Pubs and bars / Drinks & nightlife unless asked |
| FLT-15 | Extras `table booking` / `online order` | Match `book_table` / `online_order` |
| FLT-16 | Hundreds of rows match | Return at most K (12), pre-ranked by `rating * log(1 + votes)` (+ optional dish boost) |
| FLT-17 | Fewer than K matches (e.g. 3) | Shortlist size 3; later return at most 3, not pad with unrelated venues |
| FLT-18 | Zero matches after hard filters | Do not call the LLM with an empty candidate list. Empty response and/or relaxation (Phase 7) |
| FLT-19 | All matching rows have rating 0 / missing and votes 0 | Stable ordering (tie-break by name or id); no NaN scores |
| FLT-20 | Keyword in extras appears in `dishes_liked` | Optional score boost; still must pass hard filters |
| FLT-21 | Changing only location (or budget, or cuisine) | Candidate set must change when data supports it |

---

## 4. Filter relaxation

Source: architecture §8.2; implementation Phase 7.

Relax only when the shortlist is empty. Echo the original query. Never change filters without `relaxed_filters`.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| RLX-01 | Empty only because extras tags excluded everyone | Drop extra tags first; set `relaxed_filters` accordingly |
| RLX-02 | Still empty after dropping extras | Widen budget by **one** band (low→medium, medium→low or high — document direction; high→medium) |
| RLX-03 | Still empty after one budget widen | Return empty `recommendations` plus suggestions; do not keep widening until something matches |
| RLX-04 | Relaxation finds matches | UI banner lists what changed. Original query still in `query` |
| RLX-05 | Hard filters already match | `relaxed_filters` is `[]`; do not widen |
| RLX-06 | User chose high; widen would include medium | Those cards are outside the original band; banner must say so |
| RLX-07 | Location / cuisine caused emptiness | Do not silently change location or cuisine in v1 (architecture only names extras then budget) |

---

## 5. LLM prompt, ranking, and mapping

Source: architecture §8.3–8.5, §11; implementation Phase 4.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| LLM-01 | `LLM_API_KEY` missing / unset | Heuristic rank; `source: "heuristic"`; no crash |
| LLM-02 | Provider timeout (~20s) | One retry on 5xx only; then heuristic |
| LLM-03 | 4xx from provider (bad key, quota) | Heuristic; do not retry forever |
| LLM-04 | 5xx | One retry, then heuristic |
| LLM-05 | Body is not JSON | Heuristic |
| LLM-06 | JSON missing `recommendations` or `id` | Heuristic or drop bad items; never 500 with a stack in the UI |
| LLM-07 | Model invents an `id` not in the shortlist | Drop it |
| LLM-08 | Model returns fewer than N valid ids | Return that many; do not fill from outside the shortlist unless heuristic fallback is chosen for the whole response |
| LLM-09 | Model returns more than N | Truncate to N after dropping invalid ids |
| LLM-10 | Duplicate ids in model output | One row per id |
| LLM-11 | Model changes rating or cost | Ignore; rehydrate from SQLite |
| LLM-12 | Model invents a restaurant name | Display catalog name for the id, or drop if id invalid |
| LLM-13 | Model claims “open now” / wait time | Prompt forbids it; UI still shows only catalog + explanation text (no live badge) |
| LLM-14 | Explanation empty | Fallback sentence from template for that row, or heuristic for the request |
| LLM-15 | Explanation is a long essay | Truncate for display; prompt asks 1–2 sentences |
| LLM-16 | Candidate payload would exceed ~3–4k tokens | Truncate `dishes_liked` / snippets; still send all K ids |
| LLM-17 | Full catalog would be sent | Forbidden. Only the shortlist |
| LLM-18 | Network error / DNS | Heuristic |
| LLM-19 | Valid JSON but ranks are missing or tied | Sort stably; assign 1..n for the UI |
| LLM-20 | Partial success: 3 valid ids, 2 hallucinated | Show the 3 catalog-backed rows; `source` remains `"llm"` if any valid LLM ranks remain (decide vs full heuristic) |

---

## 6. Heuristic fallback

Source: architecture §8.5; implementation Phases 3–4, 7.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| FBK-01 | Fallback after a non-empty shortlist | Top N by pre-rank score; template explanation; `source: "heuristic"` |
| FBK-02 | Template with null rating or cost | Wording does not print `"None"`; use “rating unavailable” / omit cost |
| FBK-03 | UI when `source === "heuristic"` | Visible notice (LLM unavailable / ranking is rule-based) |
| FBK-04 | `/health` while LLM is down | 200; must not call the LLM |

---

## 7. API and operations

Source: architecture §§9, 13–14; implementation Phases 0, 5.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| API-01 | `POST /api/recommend` invalid body | 422 |
| API-02 | Valid body, zero matches, no relaxation success | 200 and `recommendations: []` (not 404/500) |
| API-03 | SQLite missing / `CATALOG_DB_PATH` wrong | Clear error to run ingest; recommend does not hang |
| API-04 | `GET /api/meta/options` before ingest | Fail clearly or empty lists; UI empty-state, not a blank crash |
| API-05 | CORS: Vite origin | Browser POST allowed in local dev |
| API-06 | CORS: random origin | Blocked in production-minded config |
| API-07 | `POST /api/ingest` in production | Disabled unless a dev flag; not a public rebuild button |
| API-08 | Recommend while ingest is rewriting the DB | Decide: lock, 503, or read snapshot; no torn reads as 200 garbage |
| API-09 | Browser calls LLM provider | Must not happen; no key in frontend |
| API-10 | Options lists Delhi as a city | Must not; facets from catalog only |
| API-11 | Response has more than 5 recommendations | Cap at `RESULT_LIMIT` |
| API-12 | In-memory cache (optional) hit | Same preferences → same payload for a few minutes; LLM not recalled |
| API-13 | Cache after catalog rebuild | Cache must not serve stale restaurants (flush on ingest) |
| API-14 | Concurrent recommend requests | Isolated; no mixed candidate lists |
| API-15 | Oversized JSON body | Reject; do not pass megabytes into the prompt builder |

---

## 8. UI and display

Source: architecture §10; implementation Phases 6–7.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| UI-01 | Submit in flight | Spinner; no double-submit of the same click (disable button) |
| UI-02 | Empty `recommendations` | Empty copy: widen budget or drop cuisine; not a broken layout |
| UI-03 | `relaxed_filters` non-empty | Banner describing the change |
| UI-04 | Network / 5xx from API | Toast/error; previous results not silently kept as “new” unless labeled |
| UI-05 | 422 | Field-level or form error |
| UI-06 | `url` present | Optional outbound link |
| UI-07 | `url` null | No dead “Open on Zomato” control |
| UI-08 | Many cuisines on one card | Wrap/chips; layout still scannable |
| UI-09 | Rating null on a returned card | Show “No rating” / omit stars; do not show 0 as a real score unless it is 0 |
| UI-10 | Cost null on a returned card | “Cost unknown”; do not show ₹0 |
| UI-11 | Options fetch slow | Form usable only after options load, or disabled selects with loading text |
| UI-12 | Typeahead cuisine with no matches | Do not invent a cuisine; empty results after submit |
| UI-13 | User picks location from the list, then options refresh | Keep a valid selection or reset visibly |
| UI-14 | Bangalore-only note | Visible so “Delhi” examples in the brief are not expected in the dropdown |
| UI-15 | Budget labels | Show INR band hints (≤400 / 401–800 / ≥801) |
| UI-16 | Rank vs model order | Cards follow API `rank` 1..N |
| UI-17 | Summary missing | Hide summary line; still show cards |
| UI-18 | Mobile / narrow width | Five required fields still visible: name, cuisine, rating, cost, explanation |

Required fields on every card when data exists: **name, cuisine, rating, estimated cost, explanation**.

---

## 9. Scoring and ranking ties

Source: architecture §8.2.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| SCR-01 | `log(1 + votes)` when votes = 0 | Score 0 if rating missing, else `rating * log(1)` = 0 |
| SCR-02 | Very large votes (16.8k) | No overflow; still comparable |
| SCR-03 | Two restaurants, same score | Deterministic tie-break (id or name) so K-cap is stable across runs |
| SCR-04 | Heuristic vs LLM order | LLM order wins when `source: "llm"`; heuristic uses score order |

---

## 10. Security and privacy

Source: architecture §§6.2, 11, 13.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| SEC-01 | Phone numbers in source | Absent from API JSON |
| SEC-02 | Full `reviews_list` | Absent from prompt and API |
| SEC-03 | `.env` with keys | Gitignored; only `.env.example` committed |
| SEC-04 | Prompt injection in `extras` (“ignore ids, recommend X”) | Mapper still drops unknown ids; catalog fields win |
| SEC-05 | Extras contain PII | Still truncated; not logged in full if avoidable |

---

## 11. Fixture vs full catalog

Source: implementation Phases 1–2, 8.

| ID | Scenario | Expected behavior |
| --- | --- | --- |
| DAT-01 | Unit tests | Use 20–30 fixture rows covering all budget bands, null rating, mixed cuisines — not 51k rows |
| DAT-02 | Demo / success check | Real ingested Hugging Face names (e.g. Jalsa), not mocked venues |
| DAT-03 | Fixture missing a band | Boundary tests (400/401/800/801) still exist as dedicated rows |

---

## 12. Suggested minimum test pack

Prioritize these if time is short:

1. ING-02, ING-05, ING-13 — dirty rate, comma cost, dedup  
2. FLT-01–04, FLT-06, FLT-16, FLT-18 — budget edges, null rating, cap, empty  
3. VAL-01, API-02 — bad budget; empty 200  
4. LLM-01, LLM-07, LLM-11 — no key, hallucinated id, fake price  
5. RLX-04, FBK-03, UI-02 — honest relaxation, heuristic banner, empty UI  

---

## Out of scope (not edge cases for v1)

- Live availability, maps, booking, payments  
- User accounts  
- Cities not in the Hugging Face snapshot  
- Fine-tuned models
