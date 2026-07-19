# Labels Analysis — Are the Six Labels "Correct"?

## Short answer

**Yes — for the exercise.** The six labels are the **customer's classification schema**, not a claim that they match doctl's native GitHub labels one-to-one.

The PDF is explicit:

> *"Treat this as the customer's schema."*

Your job is to map messy real-world GitHub issues into this fixed taxonomy and handle inconsistency in ground truth — not to adopt doctl's label set as-is.

---

## The required schema (from PDF)

Each issue gets **exactly one** label:

| # | Label | Intended meaning (from PDF) |
|---|---|---|
| 1 | `bug` | Software defect / broken behavior |
| 2 | `enhancement` | Feature request / improvement |
| 3 | `question` | User asking for help or clarification |
| 4 | `documentation` | Docs-related work |
| 5 | `security` | Security-related issues |
| 6 | `other` | Does not fit above: spam, duplicates, off-topic, ambiguous |

---

## How this compares to doctl's actual GitHub labels

Verified against `digitalocean/doctl` via GitHub API on **2026-07-18**.

### doctl native labels (partial list relevant to mapping)

| doctl GitHub label | Count (issues with label) | Maps to customer schema |
|---|---:|---|
| `bug` | 162 | `bug` — direct match |
| `enhancement` | 16 | `enhancement` — direct match |
| `question` | 12 | `question` — direct match |
| `docs` | 3 | `documentation` — **name differs** (`docs` ≠ `documentation`) |
| `security vulnerability` | 26 | `security` — **name differs**, compound label |
| `security fix` | 0 | `security` — would map here if present |
| `duplicate` | (exists) | `other` — PDF explicitly lists duplicates under `other` |
| Many others | — | Require mapping rules or `other` |

**Other doctl labels with no obvious 1:1 mapping:** `api-parity`, `app-platform`, `blocked`, `configuration error`, `dependencies`, `do-api`, `go`, `good first issue`, `hacktoberfest`, `help wanted`, `Needs Investigation`, `packaging`, `snap`, `suggestion`, `troubleshooting`, `version 2.x`, `waiting-response`, `windows`, `wip`, `wontfix`, `work-around-available`, etc.

These are **metadata/triage/workflow labels**, not the customer's six-category taxonomy.

### Coverage gap

- **534 total issues** in doctl (GitHub search, 2026-07-18)
- **316 issues** carry **none** of: `bug`, `enhancement`, `question`, `docs`, `security vulnerability`, `security fix`

So a naive "take the first matching native label" approach leaves most issues without a mappable ground-truth signal.

### Multi-label problem

GitHub allows **multiple labels per issue**. The customer schema requires **exactly one** label per issue. The PDF acknowledges maintainer labels are inconsistent. You must define:

- Priority rules when multiple native labels exist (e.g., `security` beats `bug`)
- How to collapse workflow labels (`blocked`, `wontfix`) into the six categories or exclude from ground truth

---

## Label-by-label correctness assessment

| Customer label | Correct as exercise schema? | Correct as doctl native label? | Notes |
|---|---|---|---|
| `bug` | ✅ Yes | ✅ Native label exists | Strong anchor for ground truth |
| `enhancement` | ✅ Yes | ✅ Native label exists | Sparse (16 issues) — class imbalance risk |
| `question` | ✅ Yes | ✅ Native label exists | Sparse (12 issues) |
| `documentation` | ✅ Yes | ⚠️ Partial | doctl uses `docs`, not `documentation`; only 3 labeled issues |
| `security` | ✅ Yes | ⚠️ Partial | doctl uses `security vulnerability` / `security fix`, not `security` |
| `other` | ✅ Yes | ❌ Not a native label | By design — catch-all per PDF |

---

## Implications for ground truth construction

The labels are **correct for the customer scenario** but **not directly usable as ground truth without transformation**:

1. **Rename mapping:** `docs` → `documentation`; `security vulnerability` / `security fix` → `security`
2. **Multi-label resolution:** Pick one canonical label per issue via rules or manual review
3. **Unlabeled / ambiguous issues:** Exclude from scored set, assign `other`, or hand-label a sample
4. **Class imbalance:** `bug` dominates; `enhancement`, `question`, `documentation` are rare — affects metric interpretation
5. **PDF expectation:** You are **not** expected to hand-label all ~500 issues — but you **must** explain your ground-truth methodology

---

## Reasons summary

| Question | Answer |
|---|---|
| Are these the right labels for the exercise? | **Yes** — they are prescribed as the customer schema |
| Are they doctl's GitHub labels? | **No** — doctl uses a richer, different label namespace |
| Can we use maintainer labels as ground truth directly? | **Only with a documented mapping + inconsistency handling** |
| Is `other` a valid label? | **Yes** — explicitly defined for spam, duplicates, off-topic, ambiguous |
