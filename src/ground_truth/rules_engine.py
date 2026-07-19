"""Deterministic rules engine for ground truth labeling."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from ground_truth.labels import (
    CUSTOMER_LABELS,
    LABEL_PRIORITY,
    NATIVE_TO_CUSTOMER,
    RULES_VERSION,
    WORKFLOW_LABELS,
)
from ingestion.models import IssueRecord

Confidence = Literal["HIGH", "MED", "LOW"]
Source = Literal["rule_native", "rule_heuristic", "unresolved"]


@dataclass(frozen=True)
class RuleResult:
    proposed_label: str | None
    confidence: Confidence
    source: Source
    mapping_reason: str
    tier: Literal["A", "B", "C"] | None = None
    rules_version: str = RULES_VERSION


SECURITY_PATTERNS = [
    re.compile(r"\bCVE-\d", re.I),
    re.compile(r"\bGHSA-", re.I),
    re.compile(r"\bsecurity\b", re.I),
    re.compile(r"\bvulnerabilit", re.I),
]
QUESTION_PATTERNS = [
    re.compile(r"^how do i\b", re.I),
    re.compile(r"^how to\b", re.I),
    re.compile(r"\?\s*$"),
]
DOCUMENTATION_PATTERNS = [
    re.compile(r"\bdocumentation\b", re.I),
    re.compile(r"\bREADME\b", re.I),
    re.compile(r"\bdocs typo\b", re.I),
]
ENHANCEMENT_PATTERNS = [
    re.compile(r"\bfeature request\b", re.I),
    re.compile(r"\bwould be nice\b", re.I),
    re.compile(r"\badd support\b", re.I),
]
BUG_PATTERNS = [
    re.compile(r"\bcrash", re.I),
    re.compile(r"\berror\b", re.I),
    re.compile(r"\bdoesn't work\b", re.I),
    re.compile(r"\bfails?\b", re.I),
    re.compile(r"\bbroken\b", re.I),
]
DUPLICATE_PATTERNS = [
    re.compile(r"\bduplicate of #\d+", re.I),
    re.compile(r"\bsame as #\d+", re.I),
]


def _map_native_labels(labels: list[str]) -> tuple[str | None, str]:
    mapped: list[tuple[str, str]] = []
    for label in labels:
        lower = label.lower()
        if lower in WORKFLOW_LABELS or lower in {k.lower() for k in WORKFLOW_LABELS}:
            continue
        customer = NATIVE_TO_CUSTOMER.get(label) or NATIVE_TO_CUSTOMER.get(lower)
        if customer:
            mapped.append((customer, label))
    if not mapped:
        return None, "no mappable native labels"
    if len(mapped) == 1:
        customer, native = mapped[0]
        return customer, f"single native label: {native}"
    customers = {customer for customer, _ in mapped}
    if len(customers) == 1:
        natives = ", ".join(native for _, native in mapped)
        return mapped[0][0], f"multiple native labels same category: {natives}"
    for priority_label in LABEL_PRIORITY:
        for customer, native in mapped:
            if customer == priority_label:
                return customer, f"priority resolved ({native} over others)"
    return None, f"conflicting native labels: {[n for _, n in mapped]}"


def _heuristic_label(title: str, body: str) -> tuple[str | None, str]:
    text = f"{title}\n{body}"
    
    # High-value security override (CVE or GHSA)
    if any(pattern.search(text) for pattern in SECURITY_PATTERNS[:2]):
        return "security", "heuristic override: security (CVE/GHSA detected)"

    checks: list[tuple[str, list[re.Pattern[str]]]] = [
        ("other", DUPLICATE_PATTERNS),
        ("security", SECURITY_PATTERNS),
        ("question", QUESTION_PATTERNS),
        ("documentation", DOCUMENTATION_PATTERNS),
        ("enhancement", ENHANCEMENT_PATTERNS),
        ("bug", BUG_PATTERNS),
    ]

    label_scores: dict[str, int] = {}
    for label, patterns in checks:
        score = sum(len(pattern.findall(text)) for pattern in patterns)
        if score > 0:
            label_scores[label] = score

    if not label_scores:
        return None, "no heuristic match"

    if len(label_scores) == 1:
        matched_label = list(label_scores.keys())[0]
        return matched_label, f"heuristic match: {matched_label}"

    # Density tie-breaker for conflicting heuristics
    sorted_hits = sorted(label_scores.items(), key=lambda x: x[1], reverse=True)
    top_label, top_score = sorted_hits[0]
    runner_up_label, runner_up_score = sorted_hits[1]

    if (top_score - runner_up_score) >= 2:
        return top_label, f"heuristic match (density resolved): {top_label} (score {top_score} vs {runner_up_label} {runner_up_score})"

    return None, f"conflicting heuristics: {list(label_scores.keys())}"


def classify_with_rules(issue: IssueRecord) -> RuleResult:
    customer, reason = _map_native_labels(issue.labels)
    heuristic, hreason = _heuristic_label(issue.title, issue.body)

    if customer and customer in CUSTOMER_LABELS:
        # Cross-validate native label with text heuristics
        if heuristic and customer != heuristic:
            return RuleResult(
                proposed_label=None,
                confidence="LOW",
                source="unresolved",
                mapping_reason=f"conflict: native label is '{customer}', but text heuristics suggest '{heuristic}'",
            )
        
        if "single native" in reason or "same category" in reason or "priority resolved" in reason:
            return RuleResult(
                proposed_label=customer,
                confidence="HIGH",
                source="rule_native",
                mapping_reason=reason,
                tier="A",
            )

    if reason.startswith("conflicting"):
        return RuleResult(
            proposed_label=None,
            confidence="LOW",
            source="unresolved",
            mapping_reason=reason,
        )

    if heuristic:
        return RuleResult(
            proposed_label=heuristic,
            confidence="MED",
            source="rule_heuristic",
            mapping_reason=hreason,
        )
    elif "conflicting heuristics" in hreason:
        return RuleResult(
            proposed_label=None,
            confidence="LOW",
            source="unresolved",
            mapping_reason=hreason,
        )

    return RuleResult(
        proposed_label=None,
        confidence="LOW",
        source="unresolved",
        mapping_reason=reason if customer is None else reason,
    )


def apply_rules_to_corpus(issues: list[IssueRecord]) -> dict[str, RuleResult]:
    return {issue.issue_id: classify_with_rules(issue) for issue in issues}
