"""Eval run orchestration: dual-model inference, metrics, persistence."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from config import ROOT_DIR, Settings, get_settings
from eval.persistence import RunManifest, RunStore
from ground_truth.labels import CUSTOMER_LABELS
from inference.classifier import MockClassifier, OpenAIClassifier
from inference.prompt import prompt_version_hash
from inference.runner import InferenceRunner, load_predictions
from ingestion.corpus_store import latest_version, load_issues_from_snapshot
from ingestion.models import IssueRecord
from metrics.accumulator import compute_run_metrics, write_metrics
from observability.logging import configure_logging, get_logger

log = get_logger()
RESULTS_DIR = ROOT_DIR / "results"
RUNS_DIR = RESULTS_DIR / "runs"
DB_PATH = RESULTS_DIR / "eval.db"


def load_ground_truth(path: Path) -> tuple[dict[str, str], set[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    labels: dict[str, str] = {}
    scored: set[str] = set()
    for issue_id, record in payload.items():
        label = record.get("label")
        if label in CUSTOMER_LABELS:
            labels[issue_id] = label
        if record.get("in_scored_set"):
            scored.add(issue_id)
    return labels, scored


def make_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def build_classifier(model: str, settings: Settings, *, use_mock: bool):
    if use_mock:
        import sys
        if not ("pytest" in sys.modules or "unittest" in sys.modules):
            raise ValueError("Mock inference is disabled.")
        return MockClassifier(model=model)
    if not settings.do_api:
        raise ValueError("DO_API is required for live inference.")
    return OpenAIClassifier(
        model=model,
        api_key=settings.do_api,
        base_url=settings.si_api_base,
        timeout=float(settings.request_timeout_sec),
    )


class EvalOrchestrator:
    def __init__(
        self,
        settings: Settings | None = None,
        results_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.results_dir = results_dir or RUNS_DIR
        self.db = RunStore(DB_PATH)

    def run_dir(self, run_id: str) -> Path:
        return self.results_dir / run_id

    async def run_single(
        self,
        model: str,
        issues: list[IssueRecord],
        *,
        run_id: str,
        corpus_version: int,
        use_mock: bool = False,
        progress_callback: Callable[[str, int, int], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        predictions_path: Path | None = None,
    ) -> tuple[RunManifest, dict]:
        """Run a single model on `issues` and return (manifest, metrics).

        Used by the funnel's pilot and full-eval stages. Writes predictions to
        `predictions_path` (or `run_dir/predictions.jsonl` if not given) and a
        `metrics.json` next to it. Passes `model_a=model_b=model` to the metrics
        accumulator so the pairwise comparison step is a no-op.
        """
        configure_logging()
        run_path = self.run_dir(run_id)
        run_path.mkdir(parents=True, exist_ok=True)
        prompt_version = self.settings.prompt_version or prompt_version_hash()
        ground_truth_path = self.settings.resolve_path(self.settings.ground_truth_path) / "labels.json"
        ground_truth, scored_ids = load_ground_truth(ground_truth_path)

        pred_path = predictions_path or (run_path / "predictions.jsonl")
        pred_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = RunManifest(
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(),
            corpus_version=corpus_version,
            repo=self.settings.github_repo,
            model_a=model,
            model_b=model,
            concurrency=self.settings.concurrency,
            prompt_version=prompt_version,
            status="running",
            total=len(issues),
            sampled_issue_ids=[issue.issue_id for issue in issues],
        )
        manifest_path = run_path / "manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        backend = build_classifier(model, self.settings, use_mock=use_mock)
        runner = InferenceRunner(backend, run_path, self.settings)
        # Override the runner's predictions path so the funnel can isolate
        # per-model prediction files in pilot/{slug}/ and full/{slug}/.
        runner.predictions_path = pred_path
        runner._predictions_file = None  # reset so it opens pred_path on first append

        state = {"completed": 0, "failed": 0}

        def on_issue(_rid: str, done: int, failed: int) -> None:
            state["completed"] = done
            state["failed"] = failed
            manifest.completed = done
            manifest.failed = failed
            if progress_callback:
                progress_callback(run_id, done, failed)

        await runner.run(
            run_id,
            issues,
            concurrency=self.settings.concurrency,
            progress_callback=on_issue,
            cancel_event=cancel_event,
        )

        predictions = load_predictions(pred_path)
        metrics = compute_run_metrics(
            predictions,
            ground_truth=ground_truth,
            scored_issue_ids=scored_ids,
            model_a=model,
            model_b=model,
        )
        write_metrics(run_path / "metrics.json", metrics)

        was_cancelled = bool(cancel_event and cancel_event.is_set())
        manifest.status = "aborted" if was_cancelled else "complete"
        manifest.completed = state["completed"]
        manifest.failed = state["failed"]
        manifest.finished_at = datetime.now(UTC).isoformat()
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return manifest, metrics

    async def run_comparison(
        self,
        model_a: str,
        model_b: str,
        issues: list[IssueRecord],
        *,
        run_id: str | None = None,
        corpus_version: int,
        use_mock: bool = False,
        progress_callback: Callable[[str, int, int], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> RunManifest:
        configure_logging()
        run_id = run_id or make_run_id()
        run_path = self.run_dir(run_id)
        run_path.mkdir(parents=True, exist_ok=True)
        prompt_version = self.settings.prompt_version or prompt_version_hash()
        ground_truth_path = self.settings.resolve_path(self.settings.ground_truth_path) / "labels.json"
        ground_truth, scored_ids = load_ground_truth(ground_truth_path)

        manifest = RunManifest(
            run_id=run_id,
            timestamp=datetime.now(UTC).isoformat(),
            corpus_version=corpus_version,
            repo=self.settings.github_repo,
            model_a=model_a,
            model_b=model_b,
            concurrency=self.settings.concurrency,
            prompt_version=prompt_version,
            status="running",
            total=len(issues) * 2,
            sampled_issue_ids=[issue.issue_id for issue in issues],
        )
        manifest_path = run_path / "manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        self.db.upsert_run(manifest)

        # Run both models concurrently against the same issue list. Each runner
        # writes to the shared predictions.jsonl (atomic append per record), so
        # every issue that completes has BOTH model_a and model_b predictions —
        # no null label_b when the run is cancelled mid-way. Concurrency is split
        # across the two models so total in-flight calls stay within budget.
        per_model_concurrency = max(1, self.settings.concurrency // 2)
        backend_a = build_classifier(model_a, self.settings, use_mock=use_mock)
        backend_b = build_classifier(model_b, self.settings, use_mock=use_mock)
        runner_a = InferenceRunner(backend_a, run_path, self.settings)
        runner_b = InferenceRunner(backend_b, run_path, self.settings)

        # Shared counters across both runners; the progress callbacks fire from
        # each runner's worker, so guard with a lock.
        state = {"completed": 0, "failed": 0}
        state_lock = asyncio.Lock()

        async def on_issue_a(_run_id: str, done: int, failed: int) -> None:
            async with state_lock:
                state["completed"] += 1
                if failed > 0:
                    state["failed"] += 1
                manifest.completed = state["completed"]
                manifest.failed = state["failed"]
                if state["completed"] % 5 == 0 or state["completed"] == manifest.total:
                    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
                    self.db.upsert_run(manifest)
                if progress_callback:
                    progress_callback(run_id, state["completed"], state["failed"])

        async def on_issue_b(_run_id: str, done: int, failed: int) -> None:
            async with state_lock:
                state["completed"] += 1
                if failed > 0:
                    state["failed"] += 1
                manifest.completed = state["completed"]
                manifest.failed = state["failed"]
                if state["completed"] % 5 == 0 or state["completed"] == manifest.total:
                    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
                    self.db.upsert_run(manifest)
                if progress_callback:
                    progress_callback(run_id, state["completed"], state["failed"])

        # The runner's progress_callback is synchronous; wrap the async update in
        # a sync shim that schedules it on the running loop.
        loop = asyncio.get_running_loop()

        def sync_progress_a(_rid: str, done: int, failed: int) -> None:
            asyncio.run_coroutine_threadsafe(on_issue_a(_rid, done, failed), loop)

        def sync_progress_b(_rid: str, done: int, failed: int) -> None:
            asyncio.run_coroutine_threadsafe(on_issue_b(_rid, done, failed), loop)

        async def run_both() -> None:
            await asyncio.gather(
                runner_a.run(
                    run_id,
                    issues,
                    concurrency=per_model_concurrency,
                    progress_callback=sync_progress_a,
                    cancel_event=cancel_event,
                ),
                runner_b.run(
                    run_id,
                    issues,
                    concurrency=per_model_concurrency,
                    progress_callback=sync_progress_b,
                    cancel_event=cancel_event,
                ),
            )

        await run_both()

        # Compute metrics on whatever predictions exist — works for both complete
        # and cancelled runs, so a mid-run terminate still yields eval results.
        all_predictions = load_predictions(run_path / "predictions.jsonl")
        metrics = compute_run_metrics(
            all_predictions,
            ground_truth=ground_truth,
            scored_issue_ids=scored_ids,
            model_a=model_a,
            model_b=model_b,
        )
        write_metrics(run_path / "metrics.json", metrics)

        errors_path = run_path / "errors.jsonl"
        with errors_path.open("w", encoding="utf-8") as handle:
            for record in all_predictions:
                if record.status != "ok":
                    handle.write(record.model_dump_json())
                    handle.write("\n")

        was_cancelled = bool(cancel_event and cancel_event.is_set())
        manifest.status = "aborted" if was_cancelled else "complete"
        manifest.completed = state["completed"]
        manifest.failed = state["failed"]
        manifest.finished_at = datetime.now(UTC).isoformat()
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        self.db.upsert_run(manifest)
        self.db.index_predictions(run_id, run_path / "predictions.jsonl")

        log.info(
            "eval.run.complete",
            run_id=run_id,
            model_a=model_a,
            model_b=model_b,
            completed=state["completed"],
            failed=state["failed"],
            cancelled=was_cancelled,
        )
        return manifest

    async def run_from_corpus(
        self,
        model_a: str,
        model_b: str,
        *,
        use_mock: bool = False,
        limit: int | None = None,
    ) -> RunManifest:
        corpus_root = self.settings.resolve_path(self.settings.corpus_path)
        version = latest_version(corpus_root, self.settings.github_repo)
        issues = load_issues_from_snapshot(corpus_root, self.settings.github_repo, version)
        if limit is not None:
            # Prioritize scored-set issues so small samples produce meaningful metrics.
            gt_path = self.settings.resolve_path(self.settings.ground_truth_path) / "labels.json"
            if gt_path.exists():
                _, scored_ids = load_ground_truth(gt_path)
                scored = [i for i in issues if i.issue_id in scored_ids]
                unscored = [i for i in issues if i.issue_id not in scored_ids]
                issues = scored + unscored
            issues = issues[:limit]
        return await self.run_comparison(
            model_a,
            model_b,
            issues,
            corpus_version=version,
            use_mock=use_mock,
        )


def load_run_metrics(run_id: str, results_dir: Path | None = None) -> dict:
    path = (results_dir or RUNS_DIR) / run_id / "metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


def reload_run(run_id: str, results_dir: Path | None = None) -> dict:
    run_path = (results_dir or RUNS_DIR) / run_id
    manifest = RunManifest.model_validate_json((run_path / "manifest.json").read_text(encoding="utf-8"))
    metrics = load_run_metrics(run_id, results_dir)
    predictions = load_predictions(run_path / "predictions.jsonl")
    return {
        "manifest": manifest.model_dump(),
        "metrics": metrics,
        "prediction_count": len(predictions),
    }
