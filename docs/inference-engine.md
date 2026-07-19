# Inference Engine (Phase 3)

Per-issue classification via DigitalOcean Serverless Inference. One GitHub issue = one API request (PDF mandatory). Parallel execution is handled by an async runner with a thread pool.

**Modules:** `src/inference/`

---

## Prompt design

### Static prefix + dynamic suffix

Classification uses a **fixed system prompt** loaded from `config/prompt_classification_v1.txt`. The user message carries only per-issue content:

```
[System — identical every request]
  Six label definitions, JSON output schema, rubric

[User — per issue]
  Title: {title}

  Body:
  {body_truncated}
```

- Temperature: `0`
- Native GitHub labels are **not** included (avoids leakage)
- `prompt_version` = first 16 chars of SHA256 hash of the system prompt; stored in run manifest and every prediction row

---

## Context window overflow handling

Long issue bodies can exceed a model's context window once the system prompt and title overhead are included.

**Module:** `src/inference/context.py` (shared by classifier and ground-truth adjudicator)

| Step | Behavior |
|---|---|
| 1. Budget | `available = MODEL_CONTEXT_TOKENS − system_prompt_tokens − COMPLETION_BUDGET − title_overhead` |
| 2. Truncate | Body capped at `min(BODY_TRUNCATE_CHARS, token_budget × 4)` (4 chars/token estimate) |
| 3. API error | On context-length errors → retry with body halved (up to `MAX_RETRIES`) |
| 4. Audit | Persist `truncated`, `original_body_chars`, `sent_body_chars` in each prediction row |

**Guardrail:** Truncation applies to the **dynamic suffix only** — the static system prefix is never modified (preserves prefix cache).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `BODY_TRUNCATE_CHARS` | `8000` | Hard character cap on issue body |
| `MODEL_CONTEXT_TOKENS` | `32768` | Model context budget |
| `COMPLETION_BUDGET` | `256` | Tokens reserved for completion |
| `MAX_RETRIES` | `3` | Retries for rate limits, timeouts, context errors |
| `CONCURRENCY` | `8` | Parallel inference workers |
| `CHECKPOINT_EVERY_N` | `50` | Flush checkpoint every N completed issues |
| `REQUEST_TIMEOUT_SEC` | `60` | Per-request timeout |
| `DO_API` | — | Serverless Inference API key (required for live runs) |
| `PROMPT_VERSION` | auto | Override prompt version hash (optional) |

---

## Prefix prompt caching (DO Serverless Inference)

**Caching ≠ batching.** Each issue still gets its own request. Caching means DO reuses the **static system prompt** across requests **per model**.

### Per-model cache namespaces

- Model A and Model B each maintain a **separate** cache
- A comparison run on 534 issues → ~533 cache hits per model after the first request (for supported models)
- Changing the selected model starts a cold cache for that slug — expected behavior

### Prompt rules for cache efficiency

- Never put `run_id`, timestamps, or `issue_id` in the system prompt
- Do not vary whitespace in the static block between requests
- Keep the same `prompt_version` for an entire run

### DO capability (July 2026)

Prompt caching for **open-source models** on Serverless Inference is in **public preview** — automatic for supported models (no `cache_control` parameter). Examples: DeepSeek V3.2/V4, Kimi K2.5/K2.6, GLM-5/5.1/5.2, Qwen 3.5, Qwen3 Coder Flash, and others per DO docs.

### Telemetry

From API `usage`:

- `prompt_tokens`, `completion_tokens`
- `cache_read_input_tokens` or `prompt_tokens_details.cached_tokens`

Computed per request:

- `cache_hit_rate ≈ cached_tokens / prompt_tokens`
- `cache_savings_usd` = counterfactual full-rate cost minus actual cost

If a model does not report cache fields, bill at full input rate and treat `cache_supported` as false — do not assume savings.

---

## Inference runner

**Module:** `src/inference/runner.py`

- Async worker pool with `ThreadPoolExecutor` (OpenAI SDK is synchronous)
- Append-only `predictions.jsonl` per run
- Checkpoint/resume via `checkpoint.json` with keys `{model}:{issue_id}`
- Idempotent resume: completed issues are skipped on restart

### Per-request record (`predictions.jsonl`)

| Field | Description |
|---|---|
| `run_id`, `issue_id`, `model`, `prompt_version` | Identity / dedupe |
| `predicted_label`, `raw_output` | Classification result |
| `status`, `error_type`, `retry_count` | `ok` or `error` |
| `latency_ms`, `prompt_tokens`, `completion_tokens`, `cached_tokens` | Ops |
| `cost_usd`, `cache_savings_usd` | Cost traceability |
| `truncated`, `original_body_chars`, `sent_body_chars` | Context audit |

---

## Cost calculation

**Module:** `src/inference/cost.py`  
**Rates:** `config/models_pricing.json`

```python
billable_input = prompt_tokens - cached_tokens
cost_usd = (
    billable_input * input_rate
    + cached_tokens * cached_input_rate
    + completion_tokens * output_rate
) / 1_000_000
cache_savings_usd = cost_without_cache - cost_usd
```

Rates are per-million tokens. Default fallback rates exist for unknown model slugs.

---

## Mock classifier (tests / CI)

**Module:** `src/inference/classifier.py` — `MockClassifier`

Deterministic heuristic labels for tests and `make run-eval` without API spend. Live runs use `OpenAIClassifier` against `https://inference.do-ai.run/v1`.

---

## Planned enhancements (not yet implemented)

These appear in the phased plan but are deferred to later phases:

| Feature | Status |
|---|---|
| Adaptive concurrency (decay on 429, increment on streak) | Planned |
| Token-bucket `MAX_RPS` rate limiter | Planned |
| Rolling `metrics_timeseries.jsonl` during run | Planned (Phase 6 UI) |
| Model catalog fetch + `cache_supported` tagging | **Implemented** — see `src/eval/model_catalog.py` |
| Stratified model selection funnel | **Implemented** — see [docs/model-selection.md](./model-selection.md) |
| Parse-failure repair prompt | Partial (retry loop exists; dedicated repair prompt TBD) |

---

## Scale behavior

| Tier | Calls per full comparison | Strategy |
|---|---|---|
| T0 (~534 issues) | ~1,068 (534 × 2 models) | Single process + checkpoint — **implemented** |
| T1 (10–100×) | ~10k–100k | Same code path; checkpoint essential — **architecture ready** |

Prefix caching is the primary T1 cost lever: static prefix × thousands of requests. T0 runs prove `cache_hit_rate`; README extrapolates savings at scale.
