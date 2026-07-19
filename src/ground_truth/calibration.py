"""Human calibration sample generation."""

from __future__ import annotations

import random
from collections import defaultdict

from ingestion.models import IssueRecord

CALIBRATION_TARGET = 40


def build_calibration_sample(
    issues: list[IssueRecord],
    labels_by_issue: dict[str, str | None],
    *,
    seed: int = 42,
    target: int = CALIBRATION_TARGET,
) -> list[dict]:
    """Select stratified issue IDs for manual human review."""
    issue_map = {issue.issue_id: issue for issue in issues}
    by_label: dict[str, list[str]] = defaultdict(list)
    for issue_id, label in labels_by_issue.items():
        if label and issue_id in issue_map:
            by_label[label].append(issue_id)

    rng = random.Random(seed)
    selected: list[str] = []
    labels_ordered = sorted(by_label.keys())
    per_class = max(3, target // max(len(labels_ordered), 1))

    for label in labels_ordered:
        pool = by_label[label][:]
        rng.shuffle(pool)
        selected.extend(pool[:per_class])

    if len(selected) < target:
        remaining = [
            issue_id
            for issue_id, label in labels_by_issue.items()
            if label and issue_id not in selected and issue_id in issue_map
        ]
        rng.shuffle(remaining)
        selected.extend(remaining[: target - len(selected)])

    selected = selected[:target]
    return [
        {
            "issue_id": issue_id,
            "expected_auto_label": labels_by_issue.get(issue_id),
            "human_label": None,
            "reviewer_notes": "",
            "native_labels": issue_map[issue_id].labels,
        }
        for issue_id in selected
    ]
