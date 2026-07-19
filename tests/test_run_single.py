"""Tests for the single-model run primitive."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.orchestrator import EvalOrchestrator
from ingestion.models import IssueRecord, make_issue_id


@pytest.mark.asyncio
async def test_run_single_produces_manifest_and_metrics(tmp_path: Path):
    settings = _settings_with_tmp_corpus(tmp_path)
    orch = EvalOrchestrator(settings=settings, results_dir=tmp_path / "runs")

    issue = _sample_issue(1, "bug", "The auth command crashes with error code 1", ["bug"])
    # Write a ground-truth label so the issue is scored.
    _write_ground_truth(tmp_path, {issue.issue_id: "bug"})

    manifest, metrics = await orch.run_single(
        "mock-classifier",
        [issue],
        run_id="test-single",
        corpus_version=1,
        use_mock=True,
    )
    assert manifest.status == "complete"
    assert manifest.model_a == "mock-classifier"
    assert manifest.model_b == "mock-classifier"  # single-model: both slots same
    # Metrics should have one model with scored count = 1.
    assert metrics["model_a"]["scored"]["count"] == 1


def _sample_issue(number: int, title: str, body: str, labels: list[str]) -> IssueRecord:
    return IssueRecord(
        issue_id=make_issue_id("digitalocean/doctl", number),
        repo="digitalocean/doctl",
        issue_number=number,
        title=title,
        body=body,
        state="open",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        labels=labels,
        html_url=f"https://github.com/digitalocean/doctl/issues/{number}",
        body_length=len(body),
    )


def _settings_with_tmp_corpus(tmp_path: Path):
    from config import Settings

    corpus_dir = tmp_path / "corpus" / "doctl" / "v1"
    corpus_dir.mkdir(parents=True)
    settings = Settings()
    # pydantic-settings ignores init kwargs for aliased fields, so override
    # the paths after construction. These are mutable by default.
    settings.corpus_path = tmp_path / "corpus"
    settings.ground_truth_path = tmp_path / "ground_truth"
    return settings


def _write_ground_truth(tmp_path: Path, labels: dict[str, str]):
    import json

    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir(parents=True, exist_ok=True)
    payload = {iid: {"label": lbl, "in_scored_set": True, "tier": "A", "source": "rule", "confidence": "HIGH"} for iid, lbl in labels.items()}
    (gt_dir / "labels.json").write_text(json.dumps(payload), encoding="utf-8")
