import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ingestion.corpus_store import (
    enrich_issue,
    file_sha256,
    issues_jsonl_path,
    load_issues_from_snapshot,
    validate_snapshot,
    write_issues_snapshot,
)
from ingestion.models import IssueRecord, make_issue_id


def _issue(number: int, labels: list[str] | None = None, title: str = "t", body: str = "b") -> IssueRecord:
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


def test_enrich_issue_sets_sha256():
    issue = enrich_issue(_issue(1, body="hello"))
    assert issue.body_sha256
    assert issue.body_length == 5


def test_write_and_load_snapshot(tmp_path: Path):
    issues = [_issue(1, labels=["bug"]), _issue(2, labels=["question"], title="How do I?")]
    manifest = write_issues_snapshot(tmp_path, "digitalocean/doctl", 1, issues)
    assert manifest.count == 2
    assert issues_jsonl_path(tmp_path, "digitalocean/doctl", 1).exists()
    loaded = load_issues_from_snapshot(tmp_path, "digitalocean/doctl", 1)
    assert len(loaded) == 2
    assert loaded[0].issue_id == "digitalocean/doctl#1"


def test_validate_snapshot_passes(tmp_path: Path):
    issues = [_issue(1)]
    write_issues_snapshot(tmp_path, "digitalocean/doctl", 1, issues)
    manifest = validate_snapshot(tmp_path, "digitalocean/doctl", 1)
    assert manifest.count == 1


def test_validate_snapshot_fails_on_tamper(tmp_path: Path):
    issues = [_issue(1)]
    write_issues_snapshot(tmp_path, "digitalocean/doctl", 1, issues)
    path = issues_jsonl_path(tmp_path, "digitalocean/doctl", 1)
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="count mismatch|sha256"):
        validate_snapshot(tmp_path, "digitalocean/doctl", 1)


def test_root_manifest_updated(tmp_path: Path):
    write_issues_snapshot(tmp_path, "digitalocean/doctl", 1, [_issue(1)])
    root = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(root["repos"]) == 1
    assert root["repos"][0]["repo"] == "digitalocean/doctl"
