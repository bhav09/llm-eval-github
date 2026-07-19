import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ground_truth.adjudicator import MockAdjudicator, _parse_adjudication_response
from ground_truth.calibration import build_calibration_sample
from ground_truth.pipeline import run_pipeline, select_scored_set, GroundTruthRecord
from ingestion.models import IssueRecord, make_issue_id


def _issue(number: int, *, labels=None, title="", body="") -> IssueRecord:
    return IssueRecord(
        issue_id=make_issue_id("digitalocean/doctl", number),
        repo="digitalocean/doctl",
        issue_number=number,
        title=title,
        body=body,
        state="open",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        labels=labels or [],
        html_url=f"https://github.com/digitalocean/doctl/issues/{number}",
    )


def test_parse_adjudication_response_valid():
    raw = json.dumps({"label": "bug", "confidence": "high", "rationale": "clear bug"})
    result = _parse_adjudication_response(raw, "test-model")
    assert result.label == "bug"
    assert result.tier == "B"
    assert result.confidence == "high"


def test_parse_adjudication_response_invalid_label():
    raw = json.dumps({"label": "invalid", "confidence": "high", "rationale": "x"})
    result = _parse_adjudication_response(raw, "test-model")
    assert result.label is None
    assert result.tier == "C"


def test_select_scored_set_respects_bounds():
    records = {}
    for index in range(200):
        label = ["bug", "enhancement", "question", "documentation", "security", "other"][index % 6]
        issue_id = f"digitalocean/doctl#{index}"
        records[issue_id] = GroundTruthRecord(
            issue_id=issue_id,
            label=label,
            tier="A" if index % 2 == 0 else "B",
            source="rule",
            confidence="HIGH",
            mapping_reason="test",
        )
    scored = select_scored_set(records)
    assert 80 <= len(scored) <= 150


def test_run_pipeline_with_mock_llm():
    issues = [
        _issue(1, labels=["bug"]),
        _issue(2, labels=["bug", "enhancement"], title="conflict"),
        _issue(3, title="How do I?", body="help"),
        _issue(4, title="CVE-2024-9999", body="security issue"),
    ]
    result = run_pipeline(issues, adjudicator=MockAdjudicator(), skip_llm=False)
    records = result["records"]
    assert records["digitalocean/doctl#1"].tier == "A"
    assert records["digitalocean/doctl#1"].in_scored_set
    assert result["metrics"]["llm_queue_size"] >= 1
    assert result["metrics"]["scored_set_size"] >= 1
    assert len(result["calibration"]) <= 40


def test_calibration_stratified():
    issues = [_issue(i, labels=["bug"]) for i in range(10)]
    labels = {issue.issue_id: "bug" for issue in issues}
    sample = build_calibration_sample(issues, labels, target=5, seed=1)
    assert len(sample) == 5
    assert all(entry["human_label"] is None for entry in sample)
