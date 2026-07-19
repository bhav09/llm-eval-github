# Implementation Plan - Selection Landing Page, Top-2 Redirection, and Funnel Progress Enhancements

This plan outlines the changes to transition the default route of the application from the head-to-head Eval page to the Model Selection page, update selection logic and podium visibility, and add detailed progress tracking (a timer and a model-by-model progress list) during selection runs.

## Proposed Changes

---

### Backend Components

#### [MODIFY] [funnel.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/eval/funnel.py)
- Update `run_funnel` signature to accept optional `issue_index` and `issue_count` in its `progress_callback`.
- In `_run_stage`, track the number of cached/reused predictions (`already_count = len(already)`) and the total number of issues (`total_count = len(issues)`).
- Update the lambda passed as `progress_callback` to `self.orchestrator.run_single` to invoke the outer progress callback with `already_count + done` and `total_count`.

#### [MODIFY] [run_manager.py](file:///Users/bhavishya/VSC Projects/llm-eval-github/src/eval/run_manager.py)
- Update the internal `progress_cb` callback to accept `issue_index: int = 0` and `issue_count: int = 0` arguments.
- Store `issue_index` and `issue_count` in the `_funnel_progress[fid]` dictionary.

---

### Frontend Components

#### [MODIFY] [api.ts](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/lib/api.ts)
- Update the typescript type `FunnelStatus` to include `issue_index?: number` and `issue_count?: number` inside the `progress` object.

#### [MODIFY] [App.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/App.tsx)
- Change `/` route to redirect to `/selection` via `<Navigate to="/selection" replace />`.
- Add a new `/eval` route mapping to `<EvalPage />`.
- Update wildcard route (`*`) to redirect to `/selection`.

#### [MODIFY] [Layout.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/components/Layout.tsx)
- Update the `Eval` navigation menu link to point to `/eval` instead of `/`.

#### [MODIFY] [RunHistoryPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/RunHistoryPage.tsx)
- Update line 53: change evaluation runs' `viewUrl` mapping from `/?run=${r.run_id}` to `/eval?run=${r.run_id}`.
- Update line 109: change the empty history call-to-action link from `/` to `/eval`.

#### [MODIFY] [EvalPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/EvalPage.tsx)
- Initialize `modelA` and `modelB` states by reading `modelA` and `modelB` from URL search parameters if available.
- Add a `useEffect` responding to search parameter changes so that if `modelA` or `modelB` are set in the query string, their state variables are updated immediately.

#### [MODIFY] [ModelSelectionPage.tsx](file:///Users/bhavishya/VSC Projects/llm-eval-github/frontend/src/pages/ModelSelectionPage.tsx)
- **On Mount**: Remove the automatic fallback loading of the latest completed funnel run when no `funnel` ID is present in the query parameters. This ensures that the Selection page starts in a clean state with no podium shown.
- **Compare Button**: Find the top 2 ranked models from the podium (`first` and `second` place models). Update the button onClick handler to navigate to `/eval?modelA=slugA&modelB=slugB` so the user is immediately redirected to the Eval page with the correct dropdown selections.
- **FunnelWidget**:
  - Show the `FunnelWidget` container as soon as `isRunning` is true (rather than waiting for the first non-null `progress` poll response).
  - Add an elapsed time timer inside the widget that increments every second when a run is active.
  - Implement a model-by-model progress checklist indicating the status (Done, Running, or Pending) for each model in the active stage (using `funnel.pilot_model_slugs` for stage 2 and `funnel.full_model_slugs` for stage 3).
  - Show the issue-level progress (e.g. `Issue 7 of 15`) next to the currently active/running model.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/ -v` to ensure python changes do not break existing backend tests.
- Verify typescript builds using `tsc -b` inside the `frontend` folder.

### Manual Verification
1. Access the web app at `http://localhost:5173/` and verify redirect to `/selection` happens automatically.
2. Confirm no winners/podium are shown on landing by default (if no funnel query param is active).
3. Start a model selection run and verify:
   - The elapsed time timer starts ticking.
   - The list of models for the active stage is displayed showing Done, Running, and Pending statuses, with the active model showing real-time issue progress (e.g., `3/5` or `12/15`).
4. Once the selection completes, verify the podium/winners are shown.
5. Click "Compare top 2 on Eval page" and confirm it navigates to `/eval` with the two winners pre-selected in the dropdowns.
6. Verify that navigating back to history and viewing an old eval run redirects to `/eval?run=<id>` correctly.
