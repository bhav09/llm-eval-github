# DigitalOcean FDE Evaluation Exercise — Documentation Index

This folder documents the requirements extracted from `DigitalOcean FDE Evaluation Exercise(1).pdf` in the repository root. All claims are tied to the PDF text unless explicitly marked as external verification or inference.

| Document | Purpose |
|---|---|
| [problem-statement.md](./problem-statement.md) | Plain-language summary of what you are building and why |
| [submission-format.md](./submission-format.md) | Exact deliverables, packaging, and README expectations |
| [application-inputs-and-outputs.md](./application-inputs-and-outputs.md) | What goes into the app and what it must produce |
| [labels-analysis.md](./labels-analysis.md) | Whether the six-label schema is correct; mapping to doctl |
| [ground-truth-methodology.md](./ground-truth-methodology.md) | Hybrid rules + LLM adjudication pipeline; scored set; artifacts |
| [inference-engine.md](./inference-engine.md) | Per-issue SI classification, context overflow, prefix caching, checkpoint |
| [model-selection.md](./model-selection.md) | 4-stage model-selection funnel: stratified select, pilot, full eval, podium, insights |
| [metrics-and-persistence.md](./metrics-and-persistence.md) | Metrics accumulator, run + funnel artifacts, SQLite registry, CLI |
| [deployment.md](./deployment.md) | DO App Platform deploy, Docker, env vars, persistence |
| [observability.md](./observability.md) | Structured logging events, stored signals, prediction trace fields |
| [ambiguities-assumptions-and-open-questions.md](./ambiguities-assumptions-and-open-questions.md) | Open-ended areas, gaps, and recommended assumptions |
| [finetuning-and-scale.md](./finetuning-and-scale.md) | Fine-tuning answer, T0/T1 scale philosophy, throughput vs multi-tenant |

**Source of truth:** `DigitalOcean FDE Evaluation Exercise(1).pdf` (5 pages).

**External verification used for labels:** GitHub API against `digitalocean/doctl` (queried 2026-07-18).
