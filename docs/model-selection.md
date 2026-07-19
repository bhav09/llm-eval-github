# Model Selection Funnel

How Colosseum picks the best production models from the live DO Serverless Inference catalog without burning the full corpus budget on every slug.

**Module:** `src/eval/funnel.py` — `FunnelOrchestrator`
**Selection logic:** `src/eval/model_catalog.py` — `stratified_select`, `tag_model`, `_is_open_weight_chat`
**Persistence:** `src/eval/persistence.py` — `FunnelRun` model + `funnel_runs` table
**API:** `src/api/main.py` — `/api/funnel*` endpoints
**UI:** `frontend/src/pages/ModelSelectionPage.tsx`

---

## Why a funnel

Testing every live slug on the full scored set is expensive and mostly redundant — many slugs are near-duplicates (same family, adjacent sizes). The funnel narrows the field in cheap stages so the expensive full-eval stage only runs on a handful of survivors.

| Stage | Input | Output | API calls |
|---|---|---|---|
| **S1 — Stratified select** | live `/v1/models` slugs | 6 representative open-weight candidates | 0 |
| **S2 — Pilot** | 6 candidates × 5 stratified scored issues | survivors (multi-criteria composite readiness score filter) | 30 |
| **S3 — Full eval** | survivors × 10 issues (5 pilot reused + 5 new) | per-model accuracy, F1, confusion matrix, cost, latency, throughput | survivors × 10 |
| **S4 — Recommend** | survivor metrics | podium (1st/2nd/3rd) + field summary + production pick | 0 |

**Total cost** for a live run where K survivors reach S3: `30 + K×10` calls. For K=3 that's 60 calls — vs 6×150 = 900 for a naive full-catalog eval.

---

## Stage 1 — Stratified select

`fetch_live_models()` pulls the live `/v1/models` list (falls back to the static catalog if `DO_API` is unset or the call fails). `stratified_select(live_slugs, k=6)` then:

1. **Filters to open-weight chat models** via `_is_open_weight_chat`:
   - Allows `openai-gpt-oss-*` (open-weight).
   - Excludes by slug prefix: `anthropic-`, `openai-gpt-`, `openai-o1`, `openai-o3`, `openai-gpt-image-`, `stable-diffusion-`, `wan2-`, `qwen3-tts-`, `qwen3-embedding-`, `all-mini-lm-`, `bge-`, `e5-`, `gte-`, `multi-qa-`, `router:`.
2. **Tags each slug** with `tag_model` — prefers the static catalog (`config/models_catalog.json`) and infers the rest from the slug: `family`, `parameter_b` (regex `\d+b`), `size_class` (small ≤8B, medium ≤20B, large ≤70B, very_large >70B), `reasoning` (slug hints: `thinking`, `r1`, `reasoning`), `instruct` (hints: `instruct`, `-it`, `-chat`, `maverick`, `flash`, `omni`).
3. **Groups by `(size_class, reasoning)`** and picks one representative per group, preferring instruct variants and the smallest parameter count within the group (cost coverage). Groups are ordered so the most distinct capability tiers come first (small, very_large, then reasoning tiers, then medium/large).

The stage 1 artifact records both counts so the UI doesn't hardcode "20":

```json
{
  "total_live_slugs": 23,
  "open_weight_slugs": 17,
  "selected": [ { "slug": "...", "family": "...", "size_class": "...", "reasoning": false, "selection_reason": "Covers the small tier" }, ... ]
}
```

---

## Stage 2 — Pilot

Runs all 6 candidates on **5 stratified scored issues** (sampled from the 150-issue scored set, covering all present labels). For each model we measure:

- `accuracy`, `macro_f1`
- `error_rate` (failed calls / total)
- `invalid_rate` (parse failures / total)
- `cost_per_call`, `p95_latency_ms`
- `throughput_rps`

**Multi-Criteria Elimination:** Instead of simple error thresholds, a weighted **composite readiness score** is calculated:
* **Accuracy** (30%)
* **Latency** (20%) — based on normalized relative P95 latency
* **Cost** (20%) — based on normalized relative cost per call
* **Throughput** (15%) — based on normalized relative throughput in rps
* **Reliability** (15%) — computed as $1 - error\_rate - invalid\_rate$

Models with operational failure rates $> 40\%$ are disqualified. All remaining models are sorted by composite score, and the top $50\%$ (minimum 2) survive. Rejected models are tagged with specific weakness fields and rationales (stored in `elimination_summary`). Pilot predictions are persisted to `predictions.jsonl` so Stage 3 can **reuse** them — no duplicate API spend.

---

## Stage 3 — Full eval

Runs the survivors on **10 issues** = the 5 pilot issues (predictions reused) **+ 5 new stratified issues**. This reuses pilot predictions via the orchestrator's checkpoint keys, so only the 5 new issues incur fresh API calls per survivor.

Computes the full metric set per model: `accuracy`, `macro_f1`, `per_class` precision/recall/F1, `confusion_matrix`, `cost_per_call`, `cost_total`, `p95_latency_ms`, `throughput_rps`, `error_rate`, `invalid_rate`, `ok_count`, `failed_count`, `scored_count`.

The confusion matrix only includes labels actually present in the ground truth or predicted by the model (not all 6) — matches the Eval page behavior.

---

## Stage 4 — Recommend

`_recommend(full_results)` produces:

- **`model_a`** — best value (accuracy per dollar; tiebreak macro F1)
- **`model_b`** — highest accuracy (tiebreak macro F1); if the same model wins both, the second-highest accuracy is picked; if the two are near-identical (within 2pp accuracy AND within 1.5× cost) and a 3rd exists, the 3rd is promoted to model_b so the pair represents a real trade-off.
- **`podium`** — top 3 by `(accuracy, macro_f1, -cost)`, each with `rank`, `slug`, `accuracy`, `macro_f1`, `cost_per_call`, `p95_latency_ms`.
- **`field_summary`** — `{ survivors, avg_accuracy, avg_cost_per_call, avg_p95_latency_ms }` so the UI can say "winner beat the field average by Xpp at Y× cost" without re-listing per-model numbers.
- **`finalists`** — the two recommended models with a `story` ("Best value" / "Highest accuracy") for the Eval page dropdown defaults.
- **`rationale`** — human-readable summary.

On non-mock runs, the recommendation is also written to `config/recommendations.json` so the Eval page can default its Model A/B dropdowns. Mock runs skip this write to avoid contaminating the real config with dummy slugs.

---

## Artifacts

```
results/
  funnels/
    <funnel_id>/
      stage1_candidates.json     # total_live_slugs, open_weight_slugs, selected[]
      stage2_pilot.json           # per-model pilot metrics
      stage3_full.json            # per-model full-eval metrics
      stage4_recommendation.json  # model_a, model_b, podium, field_summary, finalists, rationale
```

The `funnel_id` is timestamp-based (`YYYYMMDDTHHMMSSZ-<8 hex>`) and idempotent — it appears in the app URL (`/selection?funnel=<id>`) so a run can be reloaded or shared.

---

## SQLite

The `funnel_runs` table mirrors the `FunnelRun` model so the History page can list selection runs alongside eval runs:

| Column | Purpose |
|---|---|
| `funnel_id` | Primary key |
| `timestamp`, `started_at`, `finished_at` | Timing |
| `status` | `running` → `complete` / `aborted` / `failed` |
| `stage_reached` | 1–4 |
| `pilot_model_slugs`, `full_model_slugs` | Candidate / survivor lists |
| `recommended_a`, `recommended_b`, `rationale` | Final pick |
| `elimination_summary` | JSON: cut reasons, stage labels |
| `artifacts` | JSON: stage1–4 payloads |

---

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/funnel/start` | Start a funnel run (body: `{ use_mock?, confirm_spend? }`) |
| `GET /api/funnel` | List funnel runs (query: `limit`) |
| `GET /api/funnel/{id}` | Get a funnel run (with artifacts) |
| `GET /api/funnel/{id}/status` | Get live progress (`{ stage, model_index, model_count, current_slug }`) |
| `POST /api/funnel/{id}/cancel` | Cancel a running funnel (drains in-flight calls, writes partial metrics) |

---

## Cancellation

A per-funnel `asyncio.Event` is registered before the run starts. Each stage checks the event between models and between issues; when set, the orchestrator drains in-flight calls, writes partial metrics, and marks the funnel `aborted`. Partial results are still persisted, so a cancelled run can be inspected in History.

---

## UI behavior

- **Before run (Idle state):** A spacious widescreen two-column Hero dashboard. Left column hosts descriptions, the "Start Benchmark" action card, and a list of the 3 most recent selection runs (allowing users to view results instantly). The right column shows a vertical timeline pipeline ("The Evaluation Pipeline"), which is **collapsed by default** with a clickable expand/collapse toggle to save vertical space. The "Selection basis" candidate models section is also collapsed by default.
- **During run:** Stepper showing 4 narrowing trapezoid layers pulsing active states, alongside a model execution checklist with checkboxes, status tags, and elapsed duration.
- **After run:** A 3D winners podium (1st center/gold, 2nd silver, 3rd bronze) featuring count-up accuracy metrics, an Insights section recommending picks, and a progressive-disclosure collapsable metrics drawer showing the cost, latency, throughput, reliability, and composite score of all eliminated models.
- **URL:** `?funnel=<id>` is set on start and restored on reload.
- **Widescreen alignment:** Layout utilizes standard container limits (`max-w-7xl` on Selection, Eval, History, and About pages) for consistent presentation.
- **About Page:** A dedicated About page lives next to History in the navigation header, detailing the complete Roman Colosseum metaphor, labeling taxonomy, 4-stage selection funnel steps, and design choices.

---

## Tests

| File | Covers |
|---|---|
| `tests/test_stratified_selection.py` | `tag_model` + `stratified_select` grouping, ordering, open-weight filter |
| `tests/test_funnel.py` | End-to-end funnel with mocked inference; podium, field_summary, elimination |
| `tests/test_run_single.py` | `run_single` primitive (one model, persist manifest + metrics, cancellation) |

Funnel tests use isolated `db_path` and `funnels_dir` (tmp dirs) and skip the `config/recommendations.json` write (mock runs) so they don't contaminate the real config.
