"""Issue classifier via DO Serverless Inference."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from config import Settings, get_settings
from ground_truth.labels import CUSTOMER_LABELS
from inference.context import TruncationInfo, truncate_issue_text
from inference.cost import compute_cost
from inference.models import PredictionRecord
from inference.prompt import load_classification_prompt
from ingestion.models import IssueRecord


@dataclass(frozen=True)
class ClassificationOutput:
    label: str | None
    raw_output: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    latency_ms: float


class ClassifierBackend(Protocol):
    model: str

    def classify(
        self,
        issue: IssueRecord,
        system_prompt: str,
        truncation: TruncationInfo,
    ) -> ClassificationOutput: ...


def parse_label(content: str) -> tuple[str | None, str]:
    raw = content.strip()
    try:
        payload = json.loads(raw)
        label = str(payload.get("label", "")).lower().strip()
        if label in CUSTOMER_LABELS:
            return label, raw
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group())
                label = str(payload.get("label", "")).lower().strip()
                if label in CUSTOMER_LABELS:
                    return label, raw
            except json.JSONDecodeError:
                pass
    return None, raw


class OpenAIClassifier:
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://inference.do-ai.run/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._timeout = timeout
        # max_retries=0: we run our own retry loop in classify_issue_with_retries.
        # Without this the SDK silently retries stuck calls with exponential backoff,
        # which makes a single hung request look like an indefinite stall.
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )

    def classify(
        self,
        issue: IssueRecord,
        system_prompt: str,
        truncation: TruncationInfo,
    ) -> ClassificationOutput:
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncation.user_content},
            ],
            temperature=0,
            timeout=self._timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        content = response.choices[0].message.content or ""
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cached_tokens = 0
        if usage and hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
            cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0
        if usage and hasattr(usage, "cache_read_input_tokens"):
            cached_tokens = cached_tokens or getattr(usage, "cache_read_input_tokens", 0) or 0
        label, raw = parse_label(content)
        return ClassificationOutput(
            label=label,
            raw_output=raw,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            latency_ms=latency_ms,
        )


class MockClassifier:
    """Deterministic classifier for tests."""

    def __init__(self, model: str = "mock-classifier") -> None:
        self.model = model

    def classify(
        self,
        issue: IssueRecord,
        system_prompt: str,
        truncation: TruncationInfo,
    ) -> ClassificationOutput:
        text = (issue.title + " " + truncation.body).lower()
        if "cve" in text or "security" in text:
            label = "security"
        elif "?" in issue.title or text.startswith("how "):
            label = "question"
        elif "doc" in text:
            label = "documentation"
        elif "feature" in text or "enhancement" in issue.labels:
            label = "enhancement"
        elif "bug" in issue.labels or "crash" in text or "error" in text:
            label = "bug"
        else:
            label = "other"
        raw = json.dumps({"label": label})
        return ClassificationOutput(
            label=label,
            raw_output=raw,
            prompt_tokens=100,
            completion_tokens=10,
            cached_tokens=80,
            latency_ms=5.0,
        )


def build_truncation(issue: IssueRecord, system_prompt: str, settings: Settings | None = None) -> TruncationInfo:
    settings = settings or get_settings()
    return truncate_issue_text(
        issue.title,
        issue.body,
        system_prompt=system_prompt,
        body_truncate_chars=settings.body_truncate_chars,
        model_context_tokens=getattr(settings, "model_context_tokens", 32768),
        completion_budget=getattr(settings, "completion_budget", 256),
    )


def classify_issue_with_retries(
    backend: ClassifierBackend,
    issue: IssueRecord,
    *,
    run_id: str,
    prompt_version: str,
    system_prompt: str,
    settings: Settings | None = None,
) -> PredictionRecord:
    settings = settings or get_settings()
    truncation = build_truncation(issue, system_prompt, settings)
    retries = 0
    last_error = "unknown"

    while retries <= settings.max_retries:
        try:
            output = backend.classify(issue, system_prompt, truncation)
            cost = compute_cost(
                backend.model,
                output.prompt_tokens,
                output.completion_tokens,
                output.cached_tokens,
            )
            status = "ok" if output.label else "error"
            error_type = None if output.label else "parse"
            return PredictionRecord(
                run_id=run_id,
                issue_id=issue.issue_id,
                model=backend.model,
                prompt_version=prompt_version,
                predicted_label=output.label,
                raw_output=output.raw_output,
                status=status,
                error_type=error_type,
                retry_count=retries,
                latency_ms=output.latency_ms,
                prompt_tokens=output.prompt_tokens,
                completion_tokens=output.completion_tokens,
                cached_tokens=output.cached_tokens,
                cost_usd=cost.cost_usd,
                cache_savings_usd=cost.cache_savings_usd,
                truncated=truncation.truncated,
                original_body_chars=truncation.original_body_chars,
                sent_body_chars=truncation.sent_body_chars,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = _classify_error(exc)
            if last_error == "rate_limit":
                # Back off before the next attempt so we don't burn through all
                # retries in a burst and end up with null predictions.
                time.sleep(min(2.0 * (retries + 1), 10.0))
            if last_error == "context_length" and truncation.sent_body_chars > 256:
                truncation = truncate_issue_text(
                    issue.title,
                    issue.body,
                    system_prompt=system_prompt,
                    body_truncate_chars=max(256, truncation.sent_body_chars // 2),
                )
            retries += 1
            if retries > settings.max_retries:
                break

    return PredictionRecord(
        run_id=run_id,
        issue_id=issue.issue_id,
        model=backend.model,
        prompt_version=prompt_version,
        status="error",
        error_type=last_error,
        retry_count=retries,
        truncated=truncation.truncated,
        original_body_chars=truncation.original_body_chars,
        sent_body_chars=truncation.sent_body_chars,
    )


def _classify_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "rate limit" in message or "429" in message:
        return "rate_limit"
    if "timeout" in message or "timed out" in message:
        return "timeout"
    if "context" in message or "maximum context" in message or "too many tokens" in message:
        return "context_length"
    return "other"
