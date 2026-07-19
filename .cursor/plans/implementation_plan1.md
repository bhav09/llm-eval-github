# Enhanced Funnel Elimination, Metrics Visibility & UX Polish

## Background

Currently the funnel only eliminates models between Stage 2 (Pilot) and Stage 3 (Full Eval) based on two binary thresholds: `error_rate > 20%` or `invalid_rate > 20%`. This means a model with 0% accuracy but no API errors would still survive. The user wants elimination decisions grounded in the full production question: *"Why is this model a good choice considering accuracy, latency, cost, scalability, and operational reliability?"*

Additionally, the Model Selection page looks empty before a run starts, and there's no way to inspect the metrics of eliminated models.

---

## Proposed Changes

### Component 1: Multi-Criteria Elimination Logic (Backend)

#### [MODIFY] [funnel.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/eval/funnel.py)

**Current elimination** (lines 146-155): Only checks `error_rate` and `invalid_rate` against flat thresholds.

**New elimination**: Compute a composite **"readiness score"** for each model after Stage 2, weighting all five axes the user cares about:

| Axis | Weight | Metric | Higher = Better? |
|---|---|---|---|
| Accuracy | 30% | `accuracy` | Yes |
| Latency | 20% | `1 / p95_latency_ms` (normalized) | Yes |
| Cost | 20% | `1 / cost_per_call` (normalized) | Yes |
| Scalability | 15% | `throughput_rps` (normalized) | Yes |
| Reliability | 15% | `1 - error_rate - invalid_rate` | Yes |

**Hard cutoff**: Any model with `error_rate + invalid_rate > 40%` is immediately eliminated (operational failure). All remaining models are ranked by composite score. The top N survivors advance (where N = `max(2, ceil(candidate_count * 0.5))` — i.e. at least half survive, minimum 2).

Each eliminated model gets a human-readable `elimination_reason` explaining which axes were weakest (e.g. "Eliminated: accuracy 35% (rank 6/6), cost $0.02/call (rank 5/6)").

**Enriched `_summarize` output**: Add `composite_score` and `rank` fields to each model result dict so the frontend can display them.

**Enriched `elimination_summary`**: The `pilot_rejected` entries will now include the full metrics snapshot (accuracy, cost, latency, throughput, reliability, composite_score), not just a reason string.

---

### Component 2: Eliminated Models Drawer (Frontend)

#### [MODIFY] [ModelSelectionPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/ModelSelectionPage.tsx)

**When to show**: After Stage 2 completes (both during the run and after results), the `stage2_pilot` artifact is available. We'll render an **"Eliminated Models"** expandable section below the funnel widget.

**UX approach — Progressive Disclosure**:
- A small summary pill appears below the funnel: `"N models eliminated after pilot — View details"`
- Clicking it expands a panel showing each eliminated model as a compact card with:
  - Model slug
  - Mini horizontal bar chart showing its composite score relative to the best survivor
  - Key weakness badges (e.g. 🔴 Low accuracy, 🟡 High cost)
  - The full `elimination_reason` string
- This same section persists in the completed results view, sitting between the funnel summary and the podium

> [!NOTE]
> This follows progressive disclosure — the core flow (funnel → podium → insights) is uninterrupted. The eliminated details are one click away for users who care, but don't clutter the default view.

---

### Component 3: Empty-State Enrichment (Frontend)

#### [MODIFY] [ModelSelectionPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/ModelSelectionPage.tsx)

The page currently shows only a title, a one-line description, the selection basis pill, and a Run button — leaving 70% of the viewport empty (as seen in the screenshot).

**Proposed layout changes**:

1. **Hero section**: Restructure the top area into a two-column layout:
   - **Left column**: Title, description, and the Run button
   - **Right column**: A "How it works" visual showing the 4 funnel stages as a mini vertical pipeline with icons and one-line descriptions, always visible (not just during a run)

2. **Selection Basis always expanded**: Since this is the only content on the idle page, auto-expand the selection basis panel and show all 6 candidate model cards in a grid. This immediately fills the page with meaningful information.

3. **Previous run summary card**: If there's a completed funnel in the URL params or recent history, show a compact "Last run" summary card with the winner slug, accuracy, and a "View details" button. This gives returning users immediate context.

---

### Component 4: Cross-Page Animations (Frontend)

#### [MODIFY] [index.css](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/index.css)

Add new reusable animation keyframes:

| Animation | Purpose | Duration |
|---|---|---|
| `stagger-fade-in` | Cards/list items fade in sequentially with a slight upward slide | 0.3s per item, 50ms stagger |
| `scale-in` | Podium pedestals and stat cards pop in from 0.95 scale | 0.35s ease-out |
| `shimmer` | Subtle gradient sweep across loading/skeleton states | 1.5s infinite |
| `count-up` | For numeric values (accuracy %, cost), CSS counters won't work — we'll use a lightweight JS hook | 600ms |

#### [MODIFY] [ModelSelectionPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/ModelSelectionPage.tsx)

- Funnel layers: stagger-fade-in when they mount
- Model checklist items: stagger-fade-in with 50ms delay between items
- Podium: scale-in animation when results load, with the 1st-place pedestal arriving 100ms after 2nd and 3rd
- Eliminated models panel: slide-down animation when expanded

#### [MODIFY] [EvalPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/EvalPage.tsx)

- StatCards: stagger-fade-in when tab content switches
- Benchmark comparison bars: width transitions (already have `duration-500`, will add stagger delays)
- Confusion matrix cells: stagger-fade-in by row

#### [NEW] [useCountUp.ts](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/hooks/useCountUp.ts)

A lightweight React hook that animates a number from 0 to its target value over 600ms using `requestAnimationFrame`. Used in podium accuracy percentages and stat card values to make numbers "count up" when they first appear.

---

## Open Questions

> [!IMPORTANT]
> **Survivor count after pilot**: The current plan keeps at least half the models (minimum 2). With 6 candidates, that means 3 survive to Stage 3. Should we keep this ratio, or would you prefer a fixed number (e.g. always keep top 3)?

> [!IMPORTANT]
> **"How it works" mini-pipeline**: Should this show static text, or should it be an animated step-through that auto-plays on first visit (like a brief onboarding animation)?

---

## Verification Plan

### Automated Tests
- `cd /Users/bhavishya/VSC\ Projects/llm-eval-github && .venv/bin/pytest tests/ -v` — Verify existing funnel tests pass with the new composite scoring (the mock classifier produces deterministic results, so the test assertions may need updating for the new elimination logic).
- `cd frontend && npm run build` — Verify TypeScript compilation.

### Manual Verification
- Open `http://localhost:5173/selection` and confirm the empty state is filled with the hero layout and expanded selection basis.
- Start a funnel run and confirm eliminated models appear after Stage 2 with full metrics.
- Confirm animations play smoothly without jank.
