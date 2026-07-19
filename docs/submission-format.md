# Submission Format

## Packaging

Submit a **single zip file** containing all deliverables below.

There is **no specified filename** for the zip in the PDF. Use a clear name such as `fde-eval-<your-name>.zip`.

## Required contents (exactly four items per PDF)

### 1. Application source code

The runnable eval harness. The PDF states:

> *"The same code that produces the numbers you walk us through is the code we will run."*

Implication: no separate "reporting script" that diverges from what reviewers execute.

### 2. Dockerfile

Must build a **runnable container** of the application.

### 3. README (primary written deliverable)

The README is **not primarily a setup guide**. It is a **written companion** to your work.

**Must include:**

| Requirement | Detail |
|---|---|
| **Link to running application** | A URL where the app is deployed and accessible |
| **Approach and conclusions** | Your methodology and what you learned |
| **Models evaluated** | Full list of candidates you considered |
| **Two recommended models + why** | The production recommendation with tradeoff reasoning |
| **What the evaluation showed** | Numbers and honest interpretation |
| **Reproducibility (secondary weight)** | Enough to build/run the container and required env vars (including **Serverless Inference API key**) so reviewers *could* reproduce your run |

**Tone/weight:** Reasoning and recommendation first; mechanics second.

### 4. Labeled dataset and persisted eval results

Include:

- Your **ground-truth / labeled dataset** used for evaluation
- Any **persisted evaluation run outputs** (predictions, metrics, cost/latency logs — format not specified)

## What is NOT listed as a separate deliverable

The PDF does **not** require:

- A separate slide deck (unless you choose to reference one in README)
- A written PDF report beyond the README
- Video walkthrough
- Git repository link (zip is the submission vehicle)
- CI/CD configuration

You may still use git internally; the formal handoff is the zip.

## Review session (not a file, but part of submission)

Prepare to **walk reviewers through the application live** and defend decisions. The PDF treats this session as co-equal with the build:

> *"The conversation we have when you walk us through it is [the deliverable]."*

## Practical notes from PDF

- Reach out with questions rather than guessing intent — they explicitly invite this
- Methodology should port to any classification problem on any inference provider
- AI coding tools (Cursor, Claude Code, Gemini, etc.) are expected and encouraged — but you must **understand what you built**

## Environment / credentials reviewers need

From the PDF and Dockerfile/README expectations:

| Variable / credential | Purpose |
|---|---|
| **DigitalOcean Serverless Inference API key** | Required for all model inference |
| **GitHub API access** | Implied for pulling issues (token may be needed for rate limits — PDF does not specify; see ambiguities doc) |
| **Concurrency setting** | Must be configurable at runtime (env var or similar — not specified exactly) |

Credits apply only to **DigitalOcean-hosted models** on Serverless Inference.
