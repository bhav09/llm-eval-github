import asyncio
from datetime import datetime, timezone

import pytest

from inference.classifier import MockClassifier
from inference.models import PredictionRecord
from inference.runner import InferenceRunner, load_predictions
from ingestion.models import IssueRecord, make_issue_id


def _issue(number: int) -> IssueRecord:
    return IssueRecord(
        issue_id=make_issue_id("digitalocean/doctl", number),
        repo="digitalocean/doctl",
        issue_number=number,
        title=f"Issue {number}",
        body="example body",
        state="open",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        labels=["bug"],
        html_url=f"https://github.com/digitalocean/doctl/issues/{number}",
    )


@pytest.mark.asyncio
async def test_inference_runner_writes_predictions_and_checkpoint(tmp_path):
    issues = [_issue(1), _issue(2), _issue(3)]
    runner = InferenceRunner(MockClassifier(model="mock-a"), tmp_path)
    results = await runner.run("run-1", issues, concurrency=2)
    assert len(results) == 3
    loaded = load_predictions(tmp_path / "predictions.jsonl")
    assert len(loaded) == 3
    assert (tmp_path / "checkpoint.json").exists()

    # Resume should skip completed issues
    runner2 = InferenceRunner(MockClassifier(model="mock-a"), tmp_path)
    resumed = await runner2.run("run-1", issues, concurrency=2)
    assert len(resumed) == 0
    assert len(load_predictions(tmp_path / "predictions.jsonl")) == 3


@pytest.mark.asyncio
async def test_inference_runner_separate_models_share_checkpoint_file(tmp_path):
    issues = [_issue(1)]
    runner_a = InferenceRunner(MockClassifier(model="mock-a"), tmp_path)
    await runner_a.run("run-1", issues)
    runner_b = InferenceRunner(MockClassifier(model="mock-b"), tmp_path)
    await runner_b.run("run-1", issues)
    loaded = load_predictions(tmp_path / "predictions.jsonl")
    models = {record.model for record in loaded}
    assert models == {"mock-a", "mock-b"}
