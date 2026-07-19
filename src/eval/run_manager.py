"""Background eval run management for the API."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings
from eval.funnel import FunnelOrchestrator
from eval.orchestrator import DB_PATH, RUNS_DIR, EvalOrchestrator, load_ground_truth, make_run_id
from eval.persistence import FunnelRun, RunManifest
from inference.runner import load_predictions
from ingestion.corpus_store import latest_version, load_issues_from_snapshot
from observability.logging import configure_logging, get_logger

log = get_logger()


def _prioritize_scored(issues: list, settings) -> list:
    """Reorder so scored-set issues come first, shuffling both sets to ensure randomness.

    Small sample limits then capture a random sample of scored issues.
    Falls back to a random shuffle of original issues if ground truth can't be loaded.
    """
    import random
    try:
        gt_path = settings.resolve_path(settings.ground_truth_path) / "labels.json"
        if not gt_path.exists():
            shuffled = list(issues)
            random.shuffle(shuffled)
            return shuffled
        _, scored_ids = load_ground_truth(gt_path)
        scored = [i for i in issues if i.issue_id in scored_ids]
        unscored = [i for i in issues if i.issue_id not in scored_ids]
        random.shuffle(scored)
        random.shuffle(unscored)
        return scored + unscored
    except Exception:  # noqa: BLE001
        shuffled = list(issues)
        random.shuffle(shuffled)
        return shuffled


@dataclass
class RunProgress:
    run_id: str
    status: str = "queued"
    completed: int = 0
    total: int = 0
    failed: int = 0
    started_at: float = field(default_factory=time.time)
    error: str | None = None


class RunManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._progress: RunProgress | None = None
        self._orchestrator = EvalOrchestrator()
        self._cancel_events: dict[str, asyncio.Event] = {}
        # Funnel state (separate from single-comparison runs).
        self._funnel_task: asyncio.Task | None = None
        self._funnel_progress: dict[str, dict] = {}  # funnel_id -> {stage, model_index, model_count, current_slug}
        self._funnel_cancel_events: dict[str, asyncio.Event] = {}
        self._funnel_orchestrator = FunnelOrchestrator()

    @property
    def active_run_id(self) -> str | None:
        return self._progress.run_id if self._progress and self._progress.status == "running" else None

    async def start_run(
        self,
        model_a: str,
        model_b: str,
        *,
        limit: int | None = None,
        use_mock: bool = False,
        custom_settings: dict | None = None,
    ) -> RunManifest:
        async with self._lock:
            if self._task and not self._task.done():
                raise RuntimeError("A run is already in progress")

            run_id = make_run_id()
            settings = get_settings()
            if custom_settings:
                settings = settings.model_copy()
                for k, v in custom_settings.items():
                    if v is not None and hasattr(settings, k):
                        setattr(settings, k, v)

            from eval.orchestrator import EvalOrchestrator
            orchestrator = EvalOrchestrator(settings)

            corpus_root = settings.resolve_path(settings.corpus_path)
            version = latest_version(corpus_root, settings.github_repo)
            issues = load_issues_from_snapshot(corpus_root, settings.github_repo, version)
            if limit is not None:
                # Prioritize scored-set issues so small samples produce meaningful
                # metrics. Without this, "first N" sampling grabs the newest issues
                # which don't overlap with the ground-truth scored set, yielding
                # 0 accuracy/F1. Reorder so scored issues come first (in original
                # order), then take the first `limit`.
                issues = _prioritize_scored(issues, settings)
                issues = issues[:limit]

            self._progress = RunProgress(
                run_id=run_id,
                status="running",
                total=len(issues) * 2,
            )
            cancel_event = asyncio.Event()
            self._cancel_events[run_id] = cancel_event

            async def _run() -> None:
                configure_logging()
                try:
                    manifest = await orchestrator.run_comparison(
                        model_a,
                        model_b,
                        issues,
                        run_id=run_id,
                        corpus_version=version,
                        use_mock=use_mock,
                        progress_callback=self._on_progress,
                        cancel_event=cancel_event,
                    )
                    if self._progress:
                        self._progress.status = manifest.status
                        self._progress.completed = manifest.completed
                        self._progress.failed = manifest.failed
                except Exception as exc:  # noqa: BLE001
                    log.error("eval.run.failed", run_id=run_id, error=str(exc))
                    if self._progress:
                        self._progress.status = "failed"
                        self._progress.error = str(exc)
                    self._mark_failed(run_id, str(exc))
                finally:
                    self._cancel_events.pop(run_id, None)

            self._task = asyncio.create_task(_run())
            manifest = RunManifest(
                run_id=run_id,
                timestamp=datetime.now(UTC).isoformat(),
                corpus_version=version,
                model_a=model_a,
                model_b=model_b,
                concurrency=settings.concurrency,
                prompt_version="pending",
                status="running",
                total=len(issues) * 2,
            )
            return manifest

    def _on_progress(self, run_id: str, completed: int, failed: int) -> None:
        if self._progress and self._progress.run_id == run_id:
            self._progress.completed = completed
            self._progress.failed = failed

    async def cancel_run(self, run_id: str) -> dict:
        """Signal a running run to stop. Returns the current status.

        The orchestrator finishes in-flight calls, writes partial metrics, and
        marks the manifest as 'aborted'. Returns 404-ish (None) if the run isn't
        tracked by this manager.
        """
        event = self._cancel_events.get(run_id)
        if event is None:
            # Either the run already finished or it's not running in this process.
            return {"run_id": run_id, "status": "not_running"}
        event.set()
        # Wait for the background task to drain and finalize so the caller sees
        # the aborted manifest + metrics when it next polls.
        if self._task and self._progress and self._progress.run_id == run_id:
            try:
                await asyncio.wait_for(self._task, timeout=120.0)
            except asyncio.TimeoutError:
                pass
        return {"run_id": run_id, "status": "aborted"}

    def _mark_failed(self, run_id: str, error: str) -> None:
        path = RUNS_DIR / run_id / "manifest.json"
        if not path.exists():
            return
        manifest = RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
        manifest.status = "failed"
        manifest.finished_at = manifest.finished_at or manifest.started_at
        data = manifest.model_dump()
        data["error"] = error
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._orchestrator.db.upsert_run(manifest)

    def get_progress(self, run_id: str) -> dict | None:
        if self._progress and self._progress.run_id == run_id:
            elapsed = max(time.time() - self._progress.started_at, 0.001)
            rps = self._progress.completed / elapsed
            remaining = max(self._progress.total - self._progress.completed, 0)
            eta_sec = remaining / rps if rps > 0 else None
            return {
                "run_id": run_id,
                "status": self._progress.status,
                "completed": self._progress.completed,
                "total": self._progress.total,
                "failed": self._progress.failed,
                "rps": round(rps, 2),
                "eta_sec": round(eta_sec, 1) if eta_sec is not None else None,
                "error": self._progress.error,
            }
        manifest = self._orchestrator.db.get_run(run_id)
        if not manifest:
            return None
        return {
            "run_id": run_id,
            "status": manifest["status"],
            "completed": manifest.get("completed", 0),
            "total": manifest.get("total", 0),
            "failed": manifest.get("failed", 0),
            "rps": None,
            "eta_sec": None,
            "error": manifest.get("error"),
        }

    def get_issue_detail(self, run_id: str, issue_id: str) -> dict | None:
        settings = get_settings()
        run_path = RUNS_DIR / run_id
        manifest_path = run_path / "manifest.json"
        if not manifest_path.exists():
            return None
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        predictions = [row for row in load_predictions(run_path / "predictions.jsonl") if row.issue_id == issue_id]
        if not predictions:
            return None
        gt_path = settings.resolve_path(settings.ground_truth_path) / "labels.json"
        ground_truth, scored_ids = load_ground_truth(gt_path)
        corpus_root = settings.resolve_path(settings.corpus_path)
        version = manifest.get("corpus_version") or latest_version(corpus_root, settings.github_repo)
        issues = load_issues_from_snapshot(corpus_root, settings.github_repo, version)
        issue_map = {issue.issue_id: issue for issue in issues}
        issue = issue_map.get(issue_id)
        by_model = {row.model: row.model_dump() for row in predictions}
        return {
            "issue_id": issue_id,
            "title": issue.title if issue else "",
            "body_snippet": (issue.body[:500] + "…") if issue and len(issue.body) > 500 else (issue.body if issue else ""),
            "html_url": issue.html_url if issue else "",
            "ground_truth": ground_truth.get(issue_id),
            "in_scored_set": issue_id in scored_ids,
            "predictions": by_model,
            "model_a": manifest.get("model_a"),
            "model_b": manifest.get("model_b"),
        }

    # ---- Funnel (4-stage model selection) ----

    async def start_funnel(
        self,
        *,
        use_mock: bool = False,
        custom_settings: dict | None = None,
    ) -> FunnelRun:
        async with self._lock:
            if self._funnel_task and not self._funnel_task.done():
                raise RuntimeError("A funnel is already in progress")
            from eval.funnel import make_funnel_id, FunnelOrchestrator

            settings = get_settings()
            if custom_settings:
                settings = settings.model_copy()
                for k, v in custom_settings.items():
                    if v is not None and hasattr(settings, k):
                        setattr(settings, k, v)

            funnel_orchestrator = FunnelOrchestrator(settings)
            funnel_id = make_funnel_id()
            cancel_event = asyncio.Event()
            self._funnel_cancel_events[funnel_id] = cancel_event

            def progress_cb(
                fid: str,
                stage: int,
                model_index: int,
                model_count: int,
                current_slug: str | None,
                issue_index: int = 0,
                issue_count: int = 0,
            ) -> None:
                self._funnel_progress[fid] = {
                    "stage": stage,
                    "model_index": model_index,
                    "model_count": model_count,
                    "current_slug": current_slug,
                    "issue_index": issue_index,
                    "issue_count": issue_count,
                }

            async def _run() -> None:
                configure_logging()
                try:
                    funnel = await funnel_orchestrator.run_funnel(
                        use_mock=use_mock,
                        cancel_event=cancel_event,
                        progress_callback=progress_cb,
                        funnel_id=funnel_id,
                    )
                    self._funnel_progress.pop(funnel.funnel_id, None)
                except Exception as exc:  # noqa: BLE001
                    log.error("funnel.run.failed", funnel_id=funnel_id, error=str(exc))
                finally:
                    self._funnel_cancel_events.pop(funnel_id, None)

            self._funnel_task = asyncio.create_task(_run())
            return FunnelRun(
                funnel_id=funnel_id,
                timestamp=datetime.now(UTC).isoformat(),
                status="running",
                stage_reached=0,
            )

    async def cancel_funnel(self, funnel_id: str) -> dict:
        event = self._funnel_cancel_events.get(funnel_id)
        if event is None:
            return {"funnel_id": funnel_id, "status": "not_running"}
        event.set()
        if self._funnel_task:
            try:
                await asyncio.wait_for(self._funnel_task, timeout=120.0)
            except asyncio.TimeoutError:
                pass
        return {"funnel_id": funnel_id, "status": "aborted"}

    def get_funnel_progress(self, funnel_id: str) -> dict | None:
        return self._funnel_progress.get(funnel_id)


run_manager = RunManager()
