"""Ground truth labeling pipeline: rules + LLM + scored set selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

from config import get_settings
from ground_truth.adjudicator import (
    AdjudicatorClient,
    AdjudicationResult,
    MockAdjudicator,
    OpenAIAdjudicator,
    load_adjudication_prompt,
)
from ground_truth.calibration import build_calibration_sample
from ground_truth.labels import CUSTOMER_LABELS, RULES_VERSION
from ground_truth.rules_engine import RuleResult, apply_rules_to_corpus, classify_with_rules
from ingestion.corpus_store import latest_version, load_issues_from_snapshot
from ingestion.github_client import GitHubClient
from ingestion.models import IssueRecord
from observability.events import GT_LLM_ISSUE, GT_LLM_START, GT_PIPELINE_COMPLETE, GT_RULES_COMPLETE
from observability.logging import configure_logging, get_logger


def get_context_hash(title: str, body: str, comments: str, prompt: str) -> str:
    combined = f"{title}\n{body}\n{comments}\n{prompt}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

SCORED_MIN = 80
SCORED_MAX = 150


@dataclass
class GroundTruthRecord:
    issue_id: str
    label: str | None
    tier: str
    source: str
    confidence: str
    mapping_reason: str
    adjudicator_model: str | None = None
    in_scored_set: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def select_scored_set(records: dict[str, GroundTruthRecord]) -> set[str]:
    """Pick 80-150 stratified issues from Tier A and B."""
    tier_ab = [
        record
        for record in records.values()
        if record.tier in {"A", "B"} and record.label in CUSTOMER_LABELS
    ]
    if len(tier_ab) <= SCORED_MAX:
        chosen = tier_ab
    else:
        by_class: dict[str, list[GroundTruthRecord]] = defaultdict(list)
        for record in tier_ab:
            by_class[record.label].append(record)
        chosen = []
        per_class = max(5, SCORED_MAX // len(CUSTOMER_LABELS))
        for label in sorted(CUSTOMER_LABELS):
            bucket = by_class.get(label, [])
            bucket.sort(key=lambda record: record.issue_id)
            chosen.extend(bucket[:per_class])
        if len(chosen) < SCORED_MIN:
            remaining = [record for record in tier_ab if record not in chosen]
            remaining.sort(key=lambda record: record.issue_id)
            chosen.extend(remaining[: SCORED_MIN - len(chosen)])
        chosen = chosen[:SCORED_MAX]

    return {record.issue_id for record in chosen}


def run_rules_stage(issues: list[IssueRecord]) -> tuple[dict[str, RuleResult], list[IssueRecord]]:
    results = apply_rules_to_corpus(issues)
    ambiguous: list[IssueRecord] = []
    for issue in issues:
        result = results[issue.issue_id]
        if result.confidence in {"MED", "LOW"} or result.proposed_label is None:
            ambiguous.append(issue)
    return results, ambiguous


def run_pipeline(
    issues: list[IssueRecord],
    adjudicator: AdjudicatorClient | None = None,
    *,
    skip_llm: bool = False,
) -> dict:
    configure_logging()
    log = get_logger()
    settings = get_settings()
    prompt = load_adjudication_prompt()

    rule_results, ambiguous_queue = run_rules_stage(issues)
    log.info(
        GT_RULES_COMPLETE,
        total=len(issues),
        high=sum(1 for result in rule_results.values() if result.confidence == "HIGH"),
        med=sum(1 for result in rule_results.values() if result.confidence == "MED"),
        low=sum(1 for result in rule_results.values() if result.confidence == "LOW"),
        ambiguous=len(ambiguous_queue),
    )

    # Load caches
    comments_cache_path = Path("data/ground_truth/comments_cache.json")
    comments_cache: dict[str, str] = {}
    if comments_cache_path.exists():
        try:
            comments_cache = json.loads(comments_cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    adjudication_cache_path = Path("data/ground_truth/adjudication_cache.json")
    adjudication_cache: dict[str, dict] = {}
    if adjudication_cache_path.exists():
        try:
            adjudication_cache = json.loads(adjudication_cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Fetch comments dynamically if GITHUB_TOKEN is available
    if not skip_llm and ambiguous_queue and settings.github_token:
        try:
            log.info("Fetching comments for ambiguous queue...")
            with GitHubClient(token=settings.github_token, api_base=settings.github_api_base) as gh:
                for issue in ambiguous_queue:
                    if issue.issue_id not in comments_cache:
                        raw_comments = gh.fetch_issue_comments(issue.repo, issue.issue_number)
                        formatted_list = []
                        for c in raw_comments:
                            user = c.get("user", {}).get("login", "unknown")
                            if "[bot]" in user:
                                continue
                            body_text = (c.get("body") or "").strip()
                            if body_text:
                                formatted_list.append(f"- {user}: {body_text}")
                        last_comments = formatted_list[-3:]
                        comments_cache[issue.issue_id] = "\n".join(last_comments)
            comments_cache_path.parent.mkdir(parents=True, exist_ok=True)
            comments_cache_path.write_text(json.dumps(comments_cache, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Failed to fetch comments dynamically", error=str(exc))

    adjudication_results: dict[str, AdjudicationResult] = {}
    if not skip_llm and ambiguous_queue:
        if adjudicator is None:
            if settings.do_api:
                adjudicator = OpenAIAdjudicator(
                    api_key=settings.do_api,
                    model=settings.adjudicator_model,
                    base_url=settings.si_api_base,
                )
            else:
                adjudicator = MockAdjudicator()
        model_name = getattr(adjudicator, "model", "unknown")

        to_adjudicate: list[tuple[IssueRecord, str, str]] = []
        for issue in ambiguous_queue:
            comments = comments_cache.get(issue.issue_id, "")
            h = get_context_hash(issue.title, issue.body, comments, prompt)
            if h in adjudication_cache:
                cached = adjudication_cache[h]
                adjudication_results[issue.issue_id] = AdjudicationResult(
                    label=cached.get("label"),
                    confidence=cached.get("confidence", "medium"),
                    rationale=cached.get("rationale", ""),
                    tier=cached.get("tier", "B"),
                    adjudicator_model=cached.get("adjudicator_model", model_name),
                    raw_output=cached.get("raw_output", ""),
                )
            else:
                to_adjudicate.append((issue, comments, h))

        log.info(
            GT_LLM_START,
            queue_size=len(ambiguous_queue),
            live_calls=len(to_adjudicate),
            cache_hits=len(ambiguous_queue) - len(to_adjudicate),
            model=model_name,
        )

        if to_adjudicate:
            def _adjudicate_one(item: tuple[IssueRecord, str, str]) -> tuple[str, str, AdjudicationResult]:
                issue, comments, h = item
                assert adjudicator is not None
                res = adjudicator.adjudicate(issue, prompt, comments=comments)
                return issue.issue_id, h, res

            workers = min(settings.concurrency, len(to_adjudicate))
            new_cache_entries = {}
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(_adjudicate_one, item) for item in to_adjudicate]
                for future in as_completed(futures):
                    issue_id, h, result = future.result()
                    adjudication_results[issue_id] = result
                    new_cache_entries[h] = {
                        "label": result.label,
                        "confidence": result.confidence,
                        "rationale": result.rationale,
                        "tier": result.tier,
                        "adjudicator_model": result.adjudicator_model,
                        "raw_output": result.raw_output,
                    }
                    log.info(GT_LLM_ISSUE, issue_id=issue_id, label=result.label, tier=result.tier)

            if new_cache_entries:
                adjudication_cache.update(new_cache_entries)
                adjudication_cache_path.parent.mkdir(parents=True, exist_ok=True)
                adjudication_cache_path.write_text(json.dumps(adjudication_cache, indent=2), encoding="utf-8")

    records: dict[str, GroundTruthRecord] = {}
    for issue in issues:
        rule = rule_results[issue.issue_id]
        if rule.confidence == "HIGH" and rule.proposed_label:
            records[issue.issue_id] = GroundTruthRecord(
                issue_id=issue.issue_id,
                label=rule.proposed_label,
                tier="A",
                source="rule",
                confidence=rule.confidence,
                mapping_reason=rule.mapping_reason,
            )
        elif issue.issue_id in adjudication_results:
            adj = adjudication_results[issue.issue_id]
            records[issue.issue_id] = GroundTruthRecord(
                issue_id=issue.issue_id,
                label=adj.label,
                tier=adj.tier,
                source="llm",
                confidence=adj.confidence.upper(),
                mapping_reason=adj.rationale,
                adjudicator_model=adj.adjudicator_model,
            )
        else:
            records[issue.issue_id] = GroundTruthRecord(
                issue_id=issue.issue_id,
                label=None,
                tier="C",
                source="unresolved",
                confidence=rule.confidence,
                mapping_reason=rule.mapping_reason,
            )

    scored_ids = select_scored_set(records)
    for issue_id in scored_ids:
        if issue_id in records:
            records[issue_id].in_scored_set = True

    per_class = Counter(record.label for record in records.values() if record.in_scored_set and record.label)
    metrics = {
        "rules_version": RULES_VERSION,
        "total_issues": len(issues),
        "rules_high": sum(1 for result in rule_results.values() if result.confidence == "HIGH"),
        "rules_med": sum(1 for result in rule_results.values() if result.confidence == "MED"),
        "rules_low": sum(1 for result in rule_results.values() if result.confidence == "LOW"),
        "llm_queue_size": len(ambiguous_queue),
        "llm_resolved": sum(1 for result in adjudication_results.values() if result.tier == "B"),
        "llm_unresolved": sum(1 for result in adjudication_results.values() if result.tier == "C"),
        "scored_set_size": len(scored_ids),
        "tier_a_in_scored": sum(1 for issue_id in scored_ids if records[issue_id].tier == "A"),
        "tier_b_in_scored": sum(1 for issue_id in scored_ids if records[issue_id].tier == "B"),
        "per_class_counts": dict(per_class),
        "adjudicator_model": settings.adjudicator_model if adjudication_results else None,
    }

    labeled_ids = [issue_id for issue_id, record in records.items() if record.label]
    labels_by_issue = {issue_id: record.label for issue_id, record in records.items()}
    calibration = build_calibration_sample(issues, labels_by_issue)

    log.info(GT_PIPELINE_COMPLETE, **metrics)
    return {
        "records": records,
        "ambiguous_issues": ambiguous_queue,
        "metrics": metrics,
        "calibration": calibration,
    }


def write_ground_truth_outputs(output_dir: Path, pipeline_result: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = pipeline_result["records"]
    labels_payload = {issue_id: record.to_dict() for issue_id, record in records.items()}
    (output_dir / "labels.json").write_text(json.dumps(labels_payload, indent=2), encoding="utf-8")
    (output_dir / "ambiguous_queue.json").write_text(
        json.dumps(
            [issue.model_dump(mode="json") for issue in pipeline_result["ambiguous_issues"]],
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "human_calibration.json").write_text(
        json.dumps(pipeline_result["calibration"], indent=2),
        encoding="utf-8",
    )
    (output_dir / "pipeline_metrics.json").write_text(
        json.dumps(pipeline_result["metrics"], indent=2),
        encoding="utf-8",
    )
    methodology = _build_methodology(pipeline_result["metrics"])
    (output_dir / "methodology.md").write_text(methodology, encoding="utf-8")


def _build_methodology(metrics: dict) -> str:
    return f"""# Ground Truth Methodology

## Pipeline

1. **Rules engine ({metrics.get('rules_version')})** — native label mapping + heuristics
2. **LLM adjudicator** — ambiguous queue only (`{metrics.get('adjudicator_model') or 'skipped'}`)
3. **Human calibration** — stratified sample in `human_calibration.json`

## Volumes

- Total issues: {metrics.get('total_issues')}
- Rules HIGH: {metrics.get('rules_high')}
- Rules MED: {metrics.get('rules_med')}
- Rules LOW: {metrics.get('rules_low')}
- LLM queue: {metrics.get('llm_queue_size')}
- LLM resolved (Tier B): {metrics.get('llm_resolved')}
- Scored set size: {metrics.get('scored_set_size')} (Tier A: {metrics.get('tier_a_in_scored')}, Tier B: {metrics.get('tier_b_in_scored')})

## Per-class scored counts

{json.dumps(metrics.get('per_class_counts', {}), indent=2)}

## Limitations

- Maintainer labels are noisy silver standard
- Sparse classes may have low counts
- LLM adjudicator must not be used as an eval comparison model
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ground truth dataset")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--mock-llm", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)
    output_dir = settings.resolve_path(settings.ground_truth_path)
    repo = settings.github_repo
    version = latest_version(corpus_root, repo)
    issues = load_issues_from_snapshot(corpus_root, repo, version)

    adjudicator: AdjudicatorClient | None = None
    if args.mock_llm:
        adjudicator = MockAdjudicator()

    result = run_pipeline(issues, adjudicator=adjudicator, skip_llm=args.skip_llm)
    write_ground_truth_outputs(output_dir, result)
    print(f"Ground truth written to {output_dir}")
    print(f"Scored set size: {result['metrics']['scored_set_size']}")


if __name__ == "__main__":
    main()
