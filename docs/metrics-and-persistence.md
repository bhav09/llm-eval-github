# Metrics and Persistence (Phases 4–5)

How eval results are aggregated, stored, and reloaded without re-running inference.

**Modules:** `src/metrics/`, `src/eval/`

---

## Metrics engine (Phase 4)

**Goal:** Compute all PDF-required analytics from stored predictions. Metrics must be **reproducible from `predictions.jsonl` alone** (audit trail).

### Scored view (ground-truth subset)

Issues where `in_scored_set: true` in `data/ground_truth/labels.json`:

| Metric | Implementation |
|---|---|
| Accuracy | Correct / total on scored set |
| Macro F1 | Mean of per-class F1 (documented choice) |
| Per-class precision, recall, F1 | `src/metrics/scoring.py` |
| Confusion matrix (6×6) | Per model |
| Model A vs B vs ground truth disagreements | `comparison.disagreements` in metrics output |

**Failed predictions** (`status: error`) are excluded from the accuracy denominator but counted in error rate.

### Unscored view (full corpus)

| Metric | Implementation |
|---|---|
| Per-issue predicted labels + raw output | `predictions.jsonl` |
| Model agreement rate | `comparison.agreement_rate` |
| Per-class label distribution | `model_a.label_distribution`, `model_b.label_distribution` |
| Disagreement filter (A ≠ B) | `comparison.disagreements` list |

### Operational metrics (per run, per model)

| Metric | Source |
|---|---|
| Cost per call, total cost | Sum of `cost_usd` in predictions |
| Cache hit rate, savings USD | `cached_tokens` / `prompt_tokens`; `cache_savings_usd` |
| p50 / p95 / p99 latency | Percentiles over `latency_ms` |
| Error breakdown | Count by `error_type` |
| Concurrency | From run `manifest.json` |

### Streaming computation

**Module:** `src/metrics/accumulator.py` — `MetricsAccumulator`

Each prediction row is processed with `update()` without loading the full corpus into memory at once. Same code path works at T0 (~1k rows) and T1 (~100k rows).

Events: `metrics.compute.start`, `metrics.compute.complete`

---

## Run orchestration (Phase 5)

**Module:** `src/eval/orchestrator.py`

1. Load corpus snapshot and ground truth
2. Run Model A inference (full corpus, checkpoint/resume)
3. Run Model B inference (same run directory, separate checkpoint keys)
4. Compute metrics → `metrics.json`
5. Write errors → `errors.jsonl`
6. Register run in SQLite

### Run manifest (`manifest.json`)

| Field | Description |
|---|---|
| `run_id` | Unique run identifier |
| `timestamp`, `started_at`, `finished_at` | Timing |
| `corpus_version` | Corpus snapshot version |
| `ground_truth_version` | Default `labels.json` |
| `model_a`, `model_b` | Comparison model slugs |
| `concurrency`, `prompt_version` | Config snapshot |
| `status` | `running` → `complete` |
| `completed`, `total`, `failed` | Progress |

---

## Artifact layout

```
results/
  eval.db                          # SQLite run registry (runs + funnel_runs + run_issues)
  runs/
    <run_id>/
      manifest.json                # Run metadata + config snapshot
      checkpoint.json              # Resume state ({model}:{issue_id} keys)
      predictions.jsonl            # One row per issue per model (append-only)
      metrics.json                 # Final aggregates (scored + unscored + ops)
      errors.jsonl                 # Failed predictions only
  funnels/
    <funnel_id>/
      stage1_candidates.json        # total_live_slugs, open_weight_slugs, selected[]
      stage2_pilot.json             # per-model pilot metrics
      stage3_full.json              # per-model full-eval metrics
      stage4_recommendation.json    # model_a, model_b, podium, field_summary, finalists, rationale
```

Funnel predictions reuse the same `predictions.jsonl` format as eval runs (the pilot and full-eval stages run via the orchestrator's `run_single` primitive), so a funnel's survivors can be inspected with the same Issue drill-down.

**Planned (Phase 6):** `metrics_timeseries.jsonl`, `events.log` for live UI progress.

### SQLite schema (`results/eval.db`)

| Table | Purpose |
|---|---|
| `runs` | Manifest summary for eval run history / UI list |
| `run_issues` | Index for paginated drill-down (`run_id`, `issue_id`, `model`, label, cost) |
| `funnel_runs` | Funnel run summary (funnel_id, status, stage_reached, pilot/full model slugs, recommended pair, elimination_summary, artifacts JSON) |

The History page merges `runs` and `funnel_runs` into one time-sorted list with a `Type` column (Eval / Selection).

Reload a past run without re-inference:

```python
from eval.orchestrator import reload_run
reload_run("<run_id>")
```

Reload a past funnel:

```python
from eval.persistence import RunStore
store = RunStore()
funnel = store.get_funnel("<funnel_id>")
```

---

## CLI

```bash
# Mock pilot (no API credits, optional issue limit)
python -m eval.run --mock --limit 20

# Live comparison
python -m eval.run --model-a <slug-a> --model-b <slug-b>

# Makefile shortcut
make run-eval   # mock, 20 issues
```

Requires corpus at `data/corpus/doctl/v1/issues.jsonl` and ground truth at `data/ground_truth/labels.json`.

---

## `metrics.json` structure (summary)

```json
{
  "model_a": {
    "scored": { "accuracy", "macro_f1", "per_class", "confusion_matrix" },
    "cost_usd": { "total", "per_call", "cache_savings_total" },
    "latency_ms": { "p50", "p95", "p99" },
    "cache": { "hit_rate", "cached_tokens", "prompt_tokens" },
    "label_distribution": { ... }
  },
  "model_b": { ... },
  "comparison": {
    "agreement_rate",
    "disagreement_count",
    "disagreements": [ { "issue_id", "model_a_label", "model_b_label" } ]
  }
}
```

---

## Canonical preloaded run (submission)

The phased plan calls for shipping **one complete T0 run** in the repo so reviewers can inspect results without spending inference credits. Generate with:

```bash
python -m eval.run --model-a <slug-a> --model-b <slug-b>
# Commit results/runs/<run_id>/ as the canonical artifact
```

---

## Scale notes

| Tier | Predictions per run | Storage | Compute |
|---|---|---|---|
| T0 | ~1,068 | ~1–5 MB | < 1 sec metrics |
| T1 (10–100×) | ~10k–100k | ~10–500 MB | ~5–30 sec streaming |

Do not build shard-merge CLIs or object-storage adapters for the exercise — JSONL + optional SQLite index is sufficient.
