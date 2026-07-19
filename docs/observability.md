# Observability Schema

Structured logging and metrics are first-class deliverables — they support review discussion on production inference and make long runs debuggable at scale.

**Implementation:** `src/observability/` (structlog JSON to stdout)

---

## Log format

Structured JSON via structlog. Standard fields:

| Field | Type | Description |
|---|---|---|
| `timestamp` | ISO8601 | Event time |
| `level` | string | info, warning, error |
| `event` | string | Dot-separated event name |
| `run_id` | string? | Eval run identifier |
| `issue_id` | string? | `{repo}#{number}` |

Additional fields are event-specific (see tables below).

---

## Events by phase

### Phase 1 — Corpus

| Event | Description |
|---|---|
| `corpus.fetch.start` | GitHub fetch started |
| `corpus.fetch.page` | Page fetched |
| `corpus.fetch.complete` | Fetch finished |
| `corpus.validation.pass` | Manifest matches JSONL |
| `corpus.validation.fail` | Validation failed |
| `corpus.load.complete` | Snapshot loaded |

### Phase 2 — Ground truth

| Event | Description |
|---|---|
| `ground_truth.rules.complete` | Rules pass finished |
| `ground_truth.llm.start` | LLM adjudication started |
| `ground_truth.llm.issue` | Single issue adjudicated |
| `ground_truth.pipeline.complete` | Full pipeline finished |

### Phase 3 — Inference

| Event | Description |
|---|---|
| `inference.complete` | Model finished corpus (`model`, `total`, `new`, `duration_sec`) |

**Planned:** `inference.start`, `inference.request.ok`, `inference.request.retry`, `inference.rate_limit`, `inference.checkpoint`

### Phase 4 — Metrics

| Event | Description |
|---|---|
| `metrics.compute.start` | Metrics aggregation started (`rows`) |
| `metrics.compute.complete` | Finished (`rows`, `duration_sec`) |

### Phase 5 — Eval orchestration

| Event | Description |
|---|---|
| `eval.run.complete` | Full comparison run finished (`model_a`, `model_b`, `completed`, `failed`) |

**Planned:** `persistence.checkpoint` with bytes written

---

## Stored signals (not only stdout)

| Signal | Fields | Where stored |
|---|---|---|
| **Run span** | `run_id`, `model_a`, `model_b`, `corpus_version`, `concurrency`, `prompt_version`, timing | `results/runs/<id>/manifest.json` |
| **Request span** | `issue_id`, `latency_ms`, tokens, `cached_tokens`, `cost_usd`, `status`, `error_type`, truncation | `results/runs/<id>/predictions.jsonl` |
| **Aggregates** | accuracy, F1, confusion matrix, ops metrics | `results/runs/<id>/metrics.json` |
| **Ground truth pipeline** | rules counts, LLM queue, scored set size | `data/ground_truth/pipeline_metrics.json` |

**Planned (Phase 6):**

- Rolling ops ticks → `metrics_timeseries.jsonl`
- Event timeline → `results/runs/<id>/events.log`
- Health endpoints: `/health`, `/ready`, `/runs/{id}/status`

---

## Ground truth metrics file

Written to `data/ground_truth/pipeline_metrics.json`:

- `rules_high`, `rules_med`, `rules_low`
- `llm_queue_size`, `llm_resolved`, `llm_unresolved`
- `scored_set_size`, `tier_a_in_scored`, `tier_b_in_scored`
- `per_class_counts`

---

## Prediction row observability fields

Each line in `predictions.jsonl` is a self-contained request trace:

| Field | Ops use |
|---|---|
| `latency_ms` | p50/p95/p99 |
| `prompt_tokens`, `completion_tokens`, `cached_tokens` | Cost + cache hit rate |
| `cost_usd`, `cache_savings_usd` | Cost panel |
| `status`, `error_type`, `retry_count` | Error breakdown |
| `truncated`, `original_body_chars`, `sent_body_chars` | Context overflow audit |

---

## Alert thresholds (review talking points)

Document in README / Ops UI when implemented:

| Condition | Suggested action |
|---|---|
| Error rate > 5% | Reduce concurrency |
| p95 latency > 30s | Check model load or reduce concurrency |
| Cache hit rate < 50% after warmup | Verify static prefix stability |
| Context truncation > 20% of corpus | Review `BODY_TRUNCATE_CHARS` / model choice |

See [inference-engine.md](./inference-engine.md) for context overflow details.
