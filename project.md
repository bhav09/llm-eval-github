# Enhanced Task Brief (ETB) — FDE Eval Harness

## Scope

Build a runnable eval harness for classifying `digitalocean/doctl` GitHub issues into six customer labels, comparing DO Serverless Inference models, with defensible ground truth and production-thinking architecture.

**Phases in this ETB:** 0 (foundation), 1 (corpus), 2 (ground truth). Phases 3–5 (inference, metrics, eval orchestration) are implemented; Phases 6–9 follow the plan in `.cursor/plans/fde_eval_phased_plan_c7e77ab4.plan.md`.

## Stack

- Python 3.12, httpx, pydantic-settings, structlog, openai SDK (SI API)
- JSONL corpus + JSON ground truth artifacts
- pytest for tests

## Scale tiers

| Tier | Scope |
|---|---|
| **T0** | Build & ship on ~534 doctl issues |
| **T1** | Architect for 10–100× (~5k–50k); hooks only, README narrative |
| **Out of scope** | 1000× load tests, Kafka/worker fleets |

## Ground truth methodology

1. **Rules engine** — native label mapping + title/body heuristics → Tier A (HIGH)
2. **LLM adjudicator** — ambiguous queue only, fixed model ≠ eval models → Tier B
3. **Human calibration** — stratified sample template for spot-checks
4. **Scored set** — 80–150 issues from Tier A + B; Tier C excluded from scoring

## Observability

Structured JSON logs via structlog; events: `corpus.*`, `ground_truth.*`. See `docs/observability.md`.

## Prefix caching (Phase 3+)

Static system prompt + dynamic issue suffix; per-model cache on DO SI. Not implemented in Phases 0–2.

## Non-goals

- Fine-tuning, multi-tenant SaaS, 1000× infra, multi-issue prompt batching

## Assumptions

See `docs/ambiguities-assumptions-and-open-questions.md` (A1–A12).
