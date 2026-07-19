"""Parallel inference runner with checkpoint/resume."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from config import Settings, get_settings
from inference.classifier import ClassifierBackend, classify_issue_with_retries
from inference.models import CheckpointState, PredictionRecord
from inference.prompt import load_classification_prompt, prompt_version_hash
from ingestion.models import IssueRecord
from observability.logging import get_logger

log = get_logger()


class InferenceRunner:
    def __init__(
        self,
        backend: ClassifierBackend,
        run_dir: Path,
        settings: Settings | None = None,
    ) -> None:
        self.backend = backend
        self.run_dir = run_dir
        self.settings = settings or get_settings()
        self.system_prompt = load_classification_prompt()
        self.prompt_version = self.settings.prompt_version or prompt_version_hash(self.system_prompt)
        self.predictions_path = run_dir / "predictions.jsonl"
        self.checkpoint_path = run_dir / "checkpoint.json"
        self._predictions_file = None
        # Hard wall-clock cap per issue. Allows our retry loop to run but
        # guarantees a stuck call can't hang the run indefinitely. The
        # underlying thread can't be killed in Python, but asyncio.wait_for
        # lets the runner move on and mark the issue as timed out.
        self._hard_timeout_sec = self.settings.request_timeout_sec * (self.settings.max_retries + 1)

    def _checkpoint_key(self, issue_id: str) -> str:
        return f"{self.backend.model}:{issue_id}"

    def _load_checkpoint(self) -> set[str]:
        if not self.checkpoint_path.exists():
            return set()
        state = CheckpointState.model_validate_json(self.checkpoint_path.read_text(encoding="utf-8"))
        if state.prompt_version != self.prompt_version:
            return set()
        prefix = f"{self.backend.model}:"
        return {key for key in state.completed_keys if key.startswith(prefix)}

    def _save_checkpoint(self, run_id: str, completed: set[str]) -> None:
        existing: set[str] = set()
        if self.checkpoint_path.exists():
            state = CheckpointState.model_validate_json(
                self.checkpoint_path.read_text(encoding="utf-8")
            )
            if state.prompt_version == self.prompt_version:
                prefix = f"{self.backend.model}:"
                existing = {key for key in state.completed_keys if not key.startswith(prefix)}
        state = CheckpointState(
            run_id=run_id,
            model=self.backend.model,
            prompt_version=self.prompt_version,
            completed_keys=sorted(existing | completed),
        )
        self.checkpoint_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    def _append_prediction(self, record: PredictionRecord) -> None:
        if self._predictions_file is None:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            # "a" mode opens with O_APPEND on POSIX, so each write() is atomic
            # and appends at EOF. Combined with a single write() per record
            # (json + newline together), two runners sharing this file won't
            # interleave or corrupt lines.
            self._predictions_file = self.predictions_path.open("a", encoding="utf-8")
        self._predictions_file.write(record.model_dump_json() + "\n")
        self._predictions_file.flush()

    def close(self) -> None:
        if self._predictions_file:
            self._predictions_file.close()
            self._predictions_file = None

    async def run(
        self,
        run_id: str,
        issues: list[IssueRecord],
        *,
        concurrency: int | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> list[PredictionRecord]:
        concurrency = concurrency or self.settings.concurrency
        completed = self._load_checkpoint()
        pending = [issue for issue in issues if self._checkpoint_key(issue.issue_id) not in completed]
        results: list[PredictionRecord] = []
        lock = asyncio.Lock()
        counter = {"done": len(completed), "failed": 0}

        classify_fn = partial(
            classify_issue_with_retries,
            run_id=run_id,
            prompt_version=self.prompt_version,
            system_prompt=self.system_prompt,
            settings=self.settings,
        )

        async def process_one(issue: IssueRecord, executor: ThreadPoolExecutor) -> None:
            loop = asyncio.get_running_loop()
            try:
                record = await asyncio.wait_for(
                    loop.run_in_executor(executor, classify_fn, self.backend, issue),
                    timeout=self._hard_timeout_sec,
                )
            except asyncio.TimeoutError:
                log.warning(
                    "inference.hard_timeout",
                    run_id=run_id,
                    model=self.backend.model,
                    issue_id=issue.issue_id,
                    hard_timeout_sec=self._hard_timeout_sec,
                )
                record = PredictionRecord(
                    run_id=run_id,
                    issue_id=issue.issue_id,
                    model=self.backend.model,
                    prompt_version=self.prompt_version,
                    status="error",
                    error_type="timeout",
                    retry_count=self.settings.max_retries + 1,
                    truncated=False,
                    original_body_chars=len(issue.body),
                    sent_body_chars=0,
                )
            async with lock:
                self._append_prediction(record)
                completed.add(self._checkpoint_key(issue.issue_id))
                counter["done"] += 1
                if record.status != "ok":
                    counter["failed"] += 1
                if counter["done"] % self.settings.checkpoint_every_n == 0:
                    self._save_checkpoint(run_id, completed)
                if progress_callback:
                    progress_callback(run_id, counter["done"], counter["failed"])
            results.append(record)

        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            sem = asyncio.Semaphore(concurrency)

            async def bounded(issue: IssueRecord) -> None:
                # Stop dispatching new work once the run is cancelled. In-flight
                # threads can't be killed in Python, but we avoid starting new
                # ones so the run drains promptly and partial metrics can compute.
                if cancel_event and cancel_event.is_set():
                    return
                async with sem:
                    if cancel_event and cancel_event.is_set():
                        return
                    await process_one(issue, executor)

            await asyncio.gather(*[bounded(issue) for issue in pending])

        self._save_checkpoint(run_id, completed)
        self.close()
        log.info(
            "inference.complete",
            run_id=run_id,
            model=self.backend.model,
            total=len(issues),
            new=len(pending),
            duration_sec=round(time.perf_counter() - started, 2),
        )
        return results


def load_predictions(path: Path) -> list[PredictionRecord]:
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(PredictionRecord.model_validate_json(line))
    return records
