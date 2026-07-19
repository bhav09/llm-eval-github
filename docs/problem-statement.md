# Problem Statement (Plain Language)

## What this exercise is really about

**The build is not the deliverable. The review conversation is.**

DigitalOcean is evaluating whether you can think like a production ML/inference engineer — not whether you can vibe-code an app. You must be able to explain every meaningful design choice under questioning.

You are playing the role of a consultant to a **hypothetical customer** who:

- Classifies GitHub issues at **high volume**
- Currently uses a **frontier (expensive) model**
- Operates across **many repositories and product lines**
- Suspects they are **overpaying**

Your job: run a rigorous evaluation and **recommend which model(s) they should actually run in production**, backed by methodology, numbers, and reasoning you can defend in a customer-facing review session.

## The concrete task

Build a **runnable evaluation application** (eval harness) that:

1. Classifies GitHub issues from the **`digitalocean/doctl`** repository into a fixed 6-label schema.
2. Uses **`doctl` as a proving ground** — the approach must generalize to the customer's broader multi-repo workload, not be a one-off hack.
3. Evaluates **multiple candidate models** on DigitalOcean **Serverless Inference** (open-weight models only for the comparison; see constraints).
4. **Recommends two models for production** that represent a **meaningful tradeoff** (e.g., 8B vs 70B, reasoning vs non-reasoning).
5. Lets a user **compare those two models side-by-side** in the UI — but the choice of *which two* must come from your broader evaluation, not be a pre-assumed starting point.

## The classification problem

| Field | Value |
|---|---|
| **Data source** | GitHub public API — `digitalocean/doctl` issues (open **and** closed) |
| **Corpus size** | ~500 issues (PDF); GitHub currently reports **534 total issues** |
| **Label schema (customer's)** | Exactly **one** label per issue: `bug`, `enhancement`, `question`, `documentation`, `security`, `other` |
| **`other` meaning** | Issues that genuinely do not fit the first five: spam, duplicates, off-topic, ambiguous |
| **Ground truth quality** | Maintainer labels exist on some issues but were applied by different people over years and are **not entirely consistent** — handling this is **part of the exercise** |

## Hard architectural constraints

| Constraint | Detail |
|---|---|
| **Required external service** | DigitalOcean **Serverless Inference** only (OpenAI-compatible API) |
| **Model scope for comparison** | Open-weight models available on Serverless Inference; **no expectation** to benchmark a frontier model directly |
| **Credits** | Create a DO team, email them the address; they apply **$200** credits (DO-hosted models only — not OpenAI/Anthropic external APIs) |
| **Ingestion scope** | Thin task — **a few hundred lines at most**, then move on |
| **Corpus stability** | Same corpus across runs; **how** you achieve stability is up to you |
| **Per-issue inference** | **One issue = one inference request**. Do **not** batch multiple issues into a single prompt |
| **Concurrency** | Parallel requests; concurrency **configurable without rebuilding the container** |
| **Everything else** | Your choice — tools, libraries, hosting — as long as you can explain why |

## What "good" looks like in the review

They will push on:

- **Model selection reasoning** — what you evaluated, what you rejected, why these two
- **Evaluation methodology** — ground truth construction, metrics, limitations
- **Cost and production thinking** — per-call cost, latency, throughput, failure modes
- **Customer communication** — tradeoffs explained clearly, conclusions matched to evidence strength
- **Production rollout path** — how you'd go from one repo to the full customer workload (thought exercise; **not** a system to build)

## Five requested scope areas (from PDF)

1. **Ground truth dataset** — construct labeled evaluation set; explain reasoning (hand-labeling every issue **not** expected)
2. **Model selection** — evaluate a range; recommend two with meaningful tradeoff
3. **Evaluation methodology** — accuracy, per-class metrics, confusion matrices, honest failure analysis
4. **Cost, latency, throughput, scaling** — headline numbers visible in the app
5. **Production handling** — rollout plan, fallback for model failures, preconditions at each step (discussion only)

## What they explicitly do NOT expect

- Perfect classification accuracy
- Deep DigitalOcean platform knowledge trivia
- Building the full production multi-repo system
- A frontier-model benchmark in the comparison harness
- A heavy data-ingestion pipeline
