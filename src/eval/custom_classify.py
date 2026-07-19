"""Ad-hoc classification outside the corpus snapshot."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from config import Settings, get_settings
from eval.orchestrator import build_classifier
from inference.classifier import classify_issue_with_retries
from inference.prompt import load_classification_prompt, prompt_version_hash
from ingestion.models import IssueRecord


def make_custom_issue(title: str, body: str) -> IssueRecord:
    return IssueRecord(
        issue_id="custom#adhoc",
        repo="custom/input",
        issue_number=0,
        title=title.strip(),
        body=body,
        state="open",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        labels=[],
        html_url="",
        body_length=len(body),
    )


def classify_custom_sync(
    title: str,
    body: str,
    model_a: str,
    model_b: str,
    *,
    use_mock: bool = False,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    issue = make_custom_issue(title, body)
    system_prompt = load_classification_prompt()
    prompt_version = settings.prompt_version or prompt_version_hash(system_prompt)
    run_id = "custom-adhoc"

    results = {}
    for model in (model_a, model_b):
        backend = build_classifier(model, settings, use_mock=use_mock)
        record = classify_issue_with_retries(
            backend,
            issue,
            run_id=run_id,
            prompt_version=prompt_version,
            system_prompt=system_prompt,
            settings=settings,
        )
        key = "model_a" if model == model_a else "model_b"
        results[key] = {
            "model": model,
            "predicted_label": record.predicted_label,
            "raw_output": record.raw_output,
            "status": record.status,
            "error_type": record.error_type,
            "latency_ms": record.latency_ms,
            "cost_usd": record.cost_usd,
            "cached_tokens": record.cached_tokens,
            "truncated": record.truncated,
            "sent_body_chars": record.sent_body_chars,
        }

    label_a = results["model_a"]["predicted_label"]
    label_b = results["model_b"]["predicted_label"]
    return {
        "title": issue.title,
        "body_chars": len(body),
        "model_a": results["model_a"],
        "model_b": results["model_b"],
        "agreement": label_a is not None and label_a == label_b,
    }


async def classify_custom(
    title: str,
    body: str,
    model_a: str,
    model_b: str,
    *,
    use_mock: bool = False,
) -> dict:
    return await asyncio.to_thread(
        classify_custom_sync,
        title,
        body,
        model_a,
        model_b,
        use_mock=use_mock,
    )
