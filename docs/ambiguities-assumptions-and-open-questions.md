# Ambiguities, Open-Ended Areas, and Required Assumptions

This document lists what the PDF leaves open, what is underspecified, and where you must make defensible assumptions. Each item includes **why** it matters and a **recommended assumption** for implementation planning.

---

## Open-ended by design (explicitly your choice)

These are **intentional** — the exercise tests engineering judgment.

| Area | PDF language | Why it is open | What you must do |
|---|---|---|---|
| **Ground truth construction** | "How you construct that subset, and what you treat as ground truth, is your methodology choice" | No single correct labeled set | Document approach; defend in review |
| **Which models to evaluate** | "Evaluate a range of models" — no list | Model catalog changes over time | Pick diverse candidates on Serverless Inference; log what you tried |
| **Which two to recommend** | "Selection should be output of broader evaluation, not a starting assumption" | Tradeoff space is the point | Show elimination rationale |
| **Corpus stability mechanism** | "How you achieve that is up to you" | Snapshot vs cache vs pinned export | Pick one; version the snapshot |
| **Tech stack** | "Everything else is your call" | Not a framework quiz | Choose boring, explainable tools |
| **UI design** | Lists required views/metrics, not wireframes | UX is secondary to eval rigor | Meet minimum surfaces |
| **Metric equivalents** | "F1 (or your chosen equivalents)" | Room for macro/micro/weighted | Pick one; stay consistent |
| **Concurrency default** | "Pick a sensible default" | Workload-dependent | Default + document tradeoff |
| **Hosting / deployed URL** | README must link to running app | Deployment target unspecified | Deploy somewhere stable |
| **Production rollout plan** | "We are not asking you to build that system" | Thought experiment only | Write clear narrative in README |

---

## Ambiguous or incompletely specified

### 1. What fields constitute model input for classification?

**PDF says:** Classify GitHub issues.  
**PDF does not say:** Title only? Title + body? Labels as input (likely not for fair eval)? Comments?

| Risk | Model may perform differently; cost scales with tokens |
|---|---|
| **Assumption** | Use **title + body** as minimum input; exclude native GitHub labels from the prompt to avoid leakage. Optionally truncate very long bodies with documented limit. |
| **Reason** | Matches real production classification (new issue arrives with title/body); avoids cheating via maintainer labels |

### 2. Ground truth source and size

**PDF says:** Subset will have ground truth; don't hand-label everything.  
**PDF does not say:** Minimum subset size, sampling strategy, or trust level for maintainer labels.

| Risk | Metrics may be noisy or non-representative |
|---|---|
| **Assumption** | Build ground truth in tiers: (A) high-confidence mapped maintainer labels, (B) adjudicated sample for sparse classes, (C) exclude ambiguous multi-label issues from scored set unless resolved. Target **80–150 scored issues** with per-class minimums where possible. |
| **Reason** | Balances PDF guidance with statistically usable per-class metrics |

### 3. Handling maintainer label inconsistency

**PDF says:** Labels applied by different people over years, not entirely consistent.  
**PDF does not say:** How to reconcile disagreements or whether to treat maintainer labels as gold standard.

| Risk | "Ground truth" may itself be wrong |
|---|---|
| **Assumption** | Treat maintainer labels as **noisy silver standard**; report limitations; optionally spot-check N random issues per class; document known failure modes (e.g., `suggestion` labeled issues that are really `enhancement`). |
| **Reason** | Matches PDF intent — methodology matters more than perfect labels |

### 4. Mapping workflow labels (`wontfix`, `duplicate`, `blocked`, etc.)

**PDF says:** `other` covers duplicates and ambiguous.  
**PDF does not say:** Whether to map `duplicate` GitHub label → `other` automatically for ground truth.

| Risk | Inconsistent ground truth for `other` class |
|---|---|
| **Assumption** | `duplicate`, obvious spam, off-topic → `other` in ground truth when that native label exists; workflow labels alone (`blocked`, `waiting-response`) do **not** determine category — infer from title/body. |
| **Reason** | Aligns with PDF's `other` definition |

### 5. GitHub API authentication and rate limits

**PDF says:** Pull from GitHub public API.  
**PDF does not say:** Token required, rate limit handling, or refresh policy for stable corpus.

| Risk | Ingestion fails or corpus drifts if new issues arrive |
|---|---|
| **Assumption** | One-time fetch into a **versioned local snapshot** (JSON/SQLite) shipped in repo; optional `GITHUB_TOKEN` for higher rate limits during initial fetch only. |
| **Reason** | Satisfies corpus stability requirement |

### 6. Which Serverless Inference models count as "open-weight" for this exercise

**PDF says:** Comparison scoped to open-weight models on Serverless Inference; credits don't work on external OpenAI/Anthropic.  
**PDF does not say:** Exact model list (catalog evolves).

| Risk | Accidentally benchmarking out-of-scope or paid external models |
|---|---|
| **Assumption** | Enumerate models via `GET https://inference.do-ai.run/v1/models` at eval time; filter to open-weight / DO-credit-eligible models; document slugs used. Evaluate **≥4 candidates**, recommend **2**. |
| **Reason** | Matches credit constraint and "range of models" requirement |

### 7. Prompt design and output format

**PDF does not specify:** System prompt, few-shot examples, JSON vs free-text classification, temperature, max tokens.

| Risk | Non-reproducible results; hard to parse outputs |
|---|---|
| **Assumption** | Structured output (JSON with single `label` field), fixed system prompt listing six labels, temperature 0 (or minimum), deterministic parsing with retry on malformed output. |
| **Reason** | Enables per-issue retry and clean metrics |

### 8. Cost calculation when official pricing is incomplete

**PDF says:** Cost must be traceable from token counts × rates in code.  
**PDF does not say:** Where to get per-token rates for each model.

| Risk | Reviewers challenge dollar figures |
|---|---|
| **Assumption** | Store per-model input/output price per 1M tokens in config sourced from DO model catalog/docs at eval time; compute from `usage` fields in API responses; show formula in UI/README. |
| **Reason** | Satisfies "traceable in your code" requirement |

### 9. What "link to your running application" means operationally

**PDF requires:** URL in README.  
**PDF does not say:** Uptime SLA, auth, whether reviewers run locally vs visit your deploy.

| Risk | Deploy down during review |
|---|---|
| **Assumption** | Deploy to DO App Platform or similar; include Dockerfile for local fallback; README states both URLs. |
| **Reason** | Reduces review friction |

### 10. Persisted eval results — format and granularity

**PDF requires:** Labeled dataset + persisted eval results in zip.  
**PDF does not say:** Schema, one file vs many, whether to persist every raw completion.

| Risk | Incomplete reproducibility |
|---|---|
| **Assumption** | Persist: corpus snapshot, ground-truth file, per-run JSON with predictions, token usage, latency per issue, aggregate metrics, concurrency setting, model slugs, prompt hash/version. |
| **Reason** | Enables reviewer audit without re-spend |

### 11. "Cost per correct classification"

**PDF lists:** "cost per correct classification" as a headline number (Requested scope §4).  
**PDF UI section lists:** "cost per call" — slightly different wording.

| Risk | Metric definition mismatch |
|---|---|
| **Assumption** | Report **both**: cost per inference call (required in UI) **and** cost per correct classification = total cost / true positives + true negatives on scored set (headline in README/metrics panel). |
| **Reason** | Covers both PDF phrasings; cost per correct is more customer-relevant |

### 12. Retry and failure handling semantics

**PDF says:** Individually-retryable failures.  
**PDF does not say:** Max retries, backoff, whether failed issues count in error rate only or also in accuracy denominator.

| Risk | Metrics inconsistency |
|---|---|
| **Assumption** | Up to 3 retries with exponential backoff for rate limits/timeouts; failed issues excluded from accuracy denominator but counted in error rate; visible in UI. |
| **Reason** | Matches production patterns and PDF error breakdown |

### 13. Context window limits for long issue bodies

**PDF does not say:** Maximum body length or handling when an issue exceeds model context.

| Risk | Requests fail or truncate unpredictably |
|---|---|
| **Assumption** | Token-budget truncator on dynamic suffix only; env-configurable caps; retry with halved body on context-length API errors. See [inference-engine.md](./inference-engine.md). |
| **Reason** | Preserves prefix cache; auditable via truncation fields in predictions |

### 14. Prompt prefix caching on Serverless Inference

**PDF does not mention:** DO automatic prefix caching for open-source models.

| Risk | Cost estimates ignore potential input-token savings at scale |
|---|---|
| **Assumption** | Static prefix + dynamic suffix; report `cache_hit_rate` and `cache_savings_usd` **per model**; do not claim cross-model cache sharing. |
| **Reason** | Valid cost lever; distinct from prohibited multi-issue batching |

---

## Assumption map (quick reference)

| # | Topic | Assumption |
|---|---|---|
| A1 | Issue text input | Title + body; no native label leakage |
| A2 | Ground truth size | ~80–150 high-confidence issues, stratified where possible |
| A3 | Maintainer labels | Noisy silver standard with documented mapping |
| A4 | Native label mapping | docs→documentation; security*→security; duplicate→other |
| A5 | Corpus stability | Versioned local snapshot, not live API on each run |
| A6 | Model candidates | ≥4 open-weight SI models via `/v1/models` |
| A7 | Prompting | Structured JSON output, temperature 0 |
| A8 | Cost | Config-driven token rates from DO catalog |
| A9 | Deployment | Public URL + Docker local path |
| A10 | Persistence | JSON artifacts per run with full trace |
| A11 | Retries | 3x with backoff; failures out of accuracy denominator |
| A12 | Cost metrics | Per-call + per-correct-classification |
| A13 | Context overflow | Shared truncator; `BODY_TRUNCATE_CHARS` + token budget; halve-on-error retry |
| A14 | Prefix caching | Static system prompt only; per-model cache; track `cache_hit_rate` separately per model |
| A15 | Checkpoint/resume | `{model}:{issue_id}` keys; flush every 50 issues; no duplicate inference on resume |
| A16 | Adjudicator vs eval models | Fixed `ADJUDICATOR_MODEL` must differ from Model A / Model B comparison slugs |

---

## Questions worth asking DigitalOcean (if blocked)

The PDF invites questions. High-value clarifications:

1. Minimum acceptable ground-truth subset size for per-class metrics?
2. Should the deployed app allow reviewers to enter their own SI API key, or use yours with spend cap?
3. Is prompt caching on Serverless Inference fair game to mention in cost analysis (not batching issues)?
4. Preferred format for persisted eval artifacts?

---

## What is NOT ambiguous (do not treat as optional)

| Requirement | Status |
|---|---|
| DigitalOcean Serverless Inference for generation | **Mandatory** |
| One issue per inference request | **Mandatory** |
| No multi-issue prompt batching | **Mandatory** |
| Configurable concurrency without rebuild | **Mandatory** |
| Two-model side-by-side UI comparison | **Mandatory** |
| Scored + unscored views with listed metrics | **Mandatory** |
| Zip: code + Dockerfile + README + dataset/results | **Mandatory** |
| Six-label schema exactly one label per issue | **Mandatory** |
| Recommend two models from broader eval | **Mandatory** |
