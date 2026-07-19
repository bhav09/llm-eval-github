import json
from datetime import datetime, timezone

import pytest

from eval.orchestrator import EvalOrchestrator, reload_run
from eval.persistence import RunStore
from ground_truth.labels import CUSTOMER_LABELS
from ingestion.models import IssueRecord, make_issue_id


def _issue(number: int) -> IssueRecord:
    return IssueRecord(
        issue_id=make_issue_id("digitalocean/doctl", number),
        repo="digitalocean/doctl",
        issue_number=number,
        title=f"Issue {number}",
        body="example",
        state="open",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        labels=["bug"],
        html_url=f"https://github.com/digitalocean/doctl/issues/{number}",
    )


@pytest.fixture
def tiny_ground_truth(tmp_path, monkeypatch):
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    labels = {
        "digitalocean/doctl#1": {
            "issue_id": "digitalocean/doctl#1",
            "label": "bug",
            "in_scored_set": True,
        },
        "digitalocean/doctl#2": {
            "issue_id": "digitalocean/doctl#2",
            "label": "enhancement",
            "in_scored_set": True,
        },
    }
    (gt_dir / "labels.json").write_text(json.dumps(labels), encoding="utf-8")

    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ground_truth_path", gt_dir)
    return gt_dir


@pytest.mark.asyncio
async def test_eval_orchestrator_mock_run(tmp_path, tiny_ground_truth, monkeypatch):
    from config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ground_truth_path", tiny_ground_truth)

    orchestrator = EvalOrchestrator(settings=settings, results_dir=tmp_path / "runs")
    db_path = tmp_path / "eval.db"
    monkeypatch.setattr("eval.orchestrator.DB_PATH", db_path)

    issues = [_issue(1), _issue(2)]
    manifest = await orchestrator.run_comparison(
        "mock-a",
        "mock-b",
        issues,
        corpus_version=1,
        use_mock=True,
    )
    assert manifest.status == "complete"
    assert manifest.completed == 4
    metrics_path = tmp_path / "runs" / manifest.run_id / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert "model_a" in metrics
    assert "comparison" in metrics

    reloaded = reload_run(manifest.run_id, results_dir=tmp_path / "runs")
    assert reloaded["prediction_count"] == 4


def test_run_store_roundtrip(tmp_path):
    from eval.persistence import RunManifest

    store = RunStore(tmp_path / "eval.db")
    manifest = RunManifest(
        run_id="test-run",
        timestamp="2024-01-01T00:00:00Z",
        corpus_version=1,
        model_a="a",
        model_b="b",
        concurrency=4,
        prompt_version="abc",
        status="complete",
    )
    store.upsert_run(manifest)
    runs = store.list_runs()
    assert runs[0]["run_id"] == "test-run"
