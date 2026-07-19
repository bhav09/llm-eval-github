from datetime import datetime, timezone

import pytest

from ground_truth.rules_engine import classify_with_rules
from ingestion.models import IssueRecord, make_issue_id


def _issue(
    number: int,
    *,
    labels: list[str] | None = None,
    title: str = "",
    body: str = "",
) -> IssueRecord:
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


def test_single_native_bug_high_confidence():
    result = classify_with_rules(_issue(1, labels=["bug"], title="crash"))
    assert result.proposed_label == "bug"
    assert result.confidence == "HIGH"
    assert result.source == "rule_native"
    assert result.tier == "A"


def test_security_wins_over_bug():
    result = classify_with_rules(_issue(2, labels=["bug", "security vulnerability"]))
    assert result.proposed_label == "security"
    assert result.confidence == "HIGH"


def test_docs_maps_to_documentation():
    result = classify_with_rules(_issue(3, labels=["docs"]))
    assert result.proposed_label == "documentation"
    assert result.confidence == "HIGH"


def test_duplicate_maps_to_other():
    result = classify_with_rules(_issue(4, labels=["duplicate"]))
    assert result.proposed_label == "other"
    assert result.confidence == "HIGH"


def test_heuristic_question_med():
    result = classify_with_rules(_issue(5, title="How do I list droplets?", body=""))
    assert result.proposed_label == "question"
    assert result.confidence == "MED"
    assert result.source == "rule_heuristic"


def test_heuristic_security_cve():
    result = classify_with_rules(_issue(6, title="CVE-2024-1234 in dependency", body=""))
    assert result.proposed_label == "security"
    assert result.confidence == "MED"


def test_workflow_labels_alone_unresolved():
    result = classify_with_rules(_issue(7, labels=["blocked", "help wanted"], title="unclear", body=""))
    assert result.confidence in {"MED", "LOW"}
    if result.confidence == "LOW":
        assert result.proposed_label is None


def test_priority_resolution_bug_over_enhancement():
    result = classify_with_rules(_issue(8, labels=["bug", "enhancement"], title="x", body="y"))
    assert result.proposed_label == "bug"
    assert result.confidence == "HIGH"
    assert "priority resolved" in result.mapping_reason


def test_unlabeled_unclear_goes_to_med_or_low():
    result = classify_with_rules(_issue(9, labels=["blocked"], title="unclear behavior", body=""))
    assert result.confidence in {"MED", "LOW"}


def test_conflicting_heuristics_delegation():
    # Issue title matches "documentation" (README) and body matches "bug" (crash)
    result = classify_with_rules(_issue(10, title="Update README file", body="The app crashes with an error"))
    assert result.proposed_label is None
    assert result.confidence == "LOW"
    assert result.source == "unresolved"
    assert "conflicting heuristics" in result.mapping_reason
