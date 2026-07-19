# Colosseum

**Live app:** [https://fde-issue-eval-d4dzv.ondigitalocean.app/](https://fde-issue-eval-d4dzv.ondigitalocean.app/)

Eval harness for classifying `digitalocean/doctl` GitHub issues into six customer labels, comparing DO Serverless Inference models, with defensible hybrid ground truth — plus a data-driven **4-stage model-selection funnel** that picks the best production models from the live DO catalog.

> Named **Colosseum** because the model-selection funnel pits open-weight models against each other in a staged arena, narrowing the field to a ranked podium (1st / 2nd / 3rd).


## Two ways to use the app

### 1. Model Selection (the funnel)

The **Selection** tab runs a 4-stage funnel on demand to recommend production models from the DO Serverless Inference catalog:

| Stage | What happens | API cost |
|---|---|---|
| **S1 — Stratified select** | Fetch the live `/v1/models` list, filter to **open-weight chat models only**, pick 6 representative slugs (one per `size_class × reasoning` tier) | 0 calls |
| **S2 — Pilot** | Run all 6 models on **5 stratified scored issues**; evaluate composite readiness score (accuracy, cost, latency, throughput, reliability) and cut underperformers | 6 × 5 = 30 calls |
| **S3 — Full eval** | Run survivors on **10 issues** (5 pilot reused + 5 new); compute accuracy, macro F1, confusion matrix, cost, latency | survivors × 10 calls |
| **S4 — Recommend** | Rank survivors; emit a **podium** (1st/2nd/3rd by accuracy) + a **field summary** + a production pick | 0 calls |

The funnel runs in the background; the page polls progress every 2s and shows a **funnel-shaped progress widget** (4 colored layers narrowing from all live slugs down to 2 finalists). When complete it shows:

- **Winners** — a podium with 1st (center, tallest, brand blue), 2nd (left), 3rd (right), each with accuracy (using animated count-up transitions), cost/call, and p95 latency.
- **Insights** — a production pick (with reason), field context ("N finalists survived; winner beat the field average by Xpp at Y× cost"), and a trade-off tag per podium model (best accuracy / cheapest / fastest).
- **Eliminated Models** — a progressive-disclosure collapsable metrics drawer listing metrics (accuracy, cost, p95 latency, throughput, reliability) and composite score for pilot rejected models.
- **Selection basis** — an inline expandable panel (collapsed by default) explaining how the 6 candidates were chosen (one per size-class × reasoning tier, open-weight only).
- **The Evaluation Pipeline widget** — a vertical timeline on the idle dashboard explaining the 4 selection stages, which is **collapsed by default** with a click-to-expand toggle.

Each run has an **idempotent run ID** that appears in the URL (`/selection?funnel=<id>`), so runs are shareable and survive reload. The page layout is widened (`max-w-7xl`) across all tabs for standard presentation. A dedicated **About** tab provides complete architectural documentation.

Details: [`docs/model-selection.md`](docs/model-selection.md)

### 2. Eval (head-to-head comparison)

The **Eval** tab runs two specific models head-to-head on a sample of issues (5 / 10 / 20) and shows scored metrics, per-class precision/recall/F1, confusion matrices, disagreements, and an Ops tab with a benchmark-winner table. You can also classify a custom issue (outside the corpus) from the input panel.

The Eval page defaults its Model A / Model B dropdowns to the funnel's recommended pair when a recommendation exists, but you can override either.


## Recommendation

Rather than a static hand-picked recommendation, Colosseum writes its recommendation to `config/recommendations.json` after each successful (non-mock) funnel run. The two finalists represent a meaningful production trade-off:

- **Finalist A — best value** (accuracy per dollar)
- **Finalist B — highest accuracy** (quality ceiling)

The podium (1st/2nd/3rd) and field summary are stored in `results/funnels/<funnel_id>/stage4_recommendation.json` for full auditability.


## What we built

| Phase | Deliverable |
|---|---|
| 0–2 | Corpus snapshot (534 issues), hybrid ground truth, scored set (150) |
| 3–5 | Per-issue SI inference, metrics engine, run orchestration + SQLite |
| 6 | React UI (Selection / Eval / History tabs) |
| 7 | Model catalog + 4-stage selection funnel + stratified sampling |
| 8 | Dockerfile + DO App Platform spec |
| 9 | This README + persisted `results/` artifacts |

**Architecture hooks for 10–100×:** partitioned corpus, checkpoint/resume, streaming metrics, prefix caching, paginated UI — same design handles ~5k–50k issues without rewrite.


## Quick start (local)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# env: DO_API, optional GITHUB_TOKEN
cp .env.example .env  # if present, else create .env

# Terminal 1 — backend (port 8080 to match the Vite proxy)
uvicorn src.api.main:app --host 127.0.0.1 --port 8080

# Terminal 2 — frontend (Vite dev server, proxies /api → :8080)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

> Run the backend on **port 8080** so the Vite dev proxy (`/api/*` → `127.0.0.1:8080`) works. If you change the backend port, update `frontend/vite.config.ts`.

**Docker:**

```bash
docker build -t colosseum .
docker run -p 8080:8080 --env-file .env colosseum
```


## Deploy to DigitalOcean App Platform

1. Push repo to GitHub.
2. Update `.do/app.yaml` with your repo slug (or create app via Control Panel).
3. Set **secrets** in App Platform: `DO_API` (required for live runs).
4. Deploy — App Platform builds the Dockerfile (multi-stage: React + Python).
5. Paste the public URL into this README.

```bash
doctl apps create --spec .do/app.yaml
# or: DO Control Panel → Apps → Create from GitHub
```

**Persistence:** SQLite + JSONL under `results/` inside the container. For production durability, mount a DO Volume at `/app/results` or ship a canonical preloaded run in the image (included).


## Ground truth methodology

1. **Rules engine** → Tier A (~68% HIGH/MED confidence). Enforces **security overrides** for CVEs, **score-based density tie-breakers** to resolve multi-heuristic matches (difference $\ge 2$), and **native-heuristic cross-validation** to demote mapped label conflicts to LOW confidence for LLM review.
2. **LLM adjudicator** → ambiguous queue only (ADJUDICATOR_MODEL, default **`deepseek-v4-pro`**).
3. **Comment-Aware Context** → Dynamically retrieves the last 3 comments from the author or maintainers via `GITHUB_TOKEN` to inform the adjudicator of post-report updates (e.g. user config errors).
4. **Adjudication Caching** → Hashes input details (title, body, comments, prompt) and caches results to guarantee 100% decision reproducibility and zero duplicate API calls.
5. **Smart middle context truncation** → preserves user descriptions at the top and stack trace/log endings at the bottom.
6. **Human calibration** → stratified spot-check template in `human_calibration.json`.
7. **Scored set** → 125 issues (57 Tier A + 68 Tier B) stratified across classes (25 bugs, 25 enhancements, 25 questions, 25 security, 12 docs, 13 other).

```bash
make build-ground-truth          # mock LLM (CI)
python -m ground_truth.pipeline  # live adjudicator (dynamic comments & caching)
```

Details: [`docs/ground-truth-methodology.md`](docs/ground-truth-methodology.md)


## Running evaluations

**UI:**

- **Selection** tab → Run (kicks off the 4-stage funnel; ~survivors×15 + 30 API calls for a live run).
- **Eval** tab → pick Model A/B + sample size (5/10/20) → Run comparison. Use **Mock inference** for a free pilot.

**CLI:**

```bash
python -m eval.run --mock --limit 20
python -m eval.run --model-a alibaba-qwen3-32b --model-b gpt-oss-120b --confirm  # live
```

Artifacts: `results/runs/<run_id>/` — `predictions.jsonl`, `metrics.json`, `manifest.json`. Funnel artifacts: `results/funnels/<funnel_id>/` — `stage1_candidates.json`, `stage2_pilot.json`, `stage3_full.json`, `stage4_recommendation.json`.


## Run history

The **History** tab shows both run types in one unified, time-sorted list:

- **Selection** rows — candidate count, stage reached, recommended pair; expand to see pilot candidates + full-eval survivors.
- **Eval** rows — models, progress, failed count; expand to see the sampled issue IDs (links to GitHub).

Each row has a View link that deep-links into the relevant page with the run ID in the URL.


## Key design choices

| Choice | Rationale |
|---|---|
| One issue = one API call | PDF hard constraint |
| Static prefix + dynamic suffix | DO prefix cache per model |
| Shared context truncator | Long bodies; preserves cache prefix |
| Checkpoint every 50 issues | Resume after crash; T1 scale hook |
| SQLite + JSONL | Simple, auditable, reviewer-friendly |
| Mock classifier | CI + demo without credit burn |
| Stratified sampling (funnel + eval) | 5/15 issues cover the label spectrum without burning the full corpus |
| Open-weight-only filter for the funnel | Closed-source frontier, embeddings, image/video, TTS, routers excluded by slug prefix |
| Idempotent funnel ID in URL | Runs are shareable and survive reload |


## Prefix caching

Identical system prompt across all requests → ~533/534 cache hits per model after warmup (supported models). Tracked per model: `cache_hit_rate`, `cache_savings_usd`. **Not** shared across Model A and B.

Details: [`docs/inference-engine.md`](docs/inference-engine.md)


## Production rollout (discussion)

1. Snapshot each repo's issues (same ingestion harness)
2. Route easy issues to the value pick; low-confidence to the accuracy pick
3. Human queue for Tier C / model disagreement
4. Monitor cost/call, p95, cache hit rate per repo partition

We did **not** build the multi-repo router — methodology ports; harness proves the numbers.


## Tests

```bash
make test   # unit + funnel + stratified-selection + run-single tests
```


## Documentation

Full requirements and architecture: [`docs/README.md`](docs/README.md)

| Doc | Covers |
|---|---|
| [docs/model-selection.md](docs/model-selection.md) | 4-stage funnel, stratified select, pilot, full eval, podium, insights |
| [docs/inference-engine.md](docs/inference-engine.md) | Per-issue SI classification, context overflow, prefix caching |
| [docs/metrics-and-persistence.md](docs/metrics-and-persistence.md) | Metrics, run + funnel artifacts, SQLite schema |
| [docs/ground-truth-methodology.md](docs/ground-truth-methodology.md) | Hybrid rules + LLM adjudication pipeline |


## Zip deliverables checklist

- [x] Application source code
- [x] Dockerfile
- [x] README (this file — add live URL after deploy)
- [x] `data/corpus/` + `data/ground_truth/` + `results/`
