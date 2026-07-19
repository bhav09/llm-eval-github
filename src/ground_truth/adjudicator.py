"""LLM adjudicator for ambiguous ground truth cases."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from openai import OpenAI

from config import ROOT_DIR, get_settings
from ground_truth.labels import CUSTOMER_LABELS
from inference.context import truncate_issue_text
from ingestion.models import IssueRecord

PROMPT_PATH = ROOT_DIR / "config" / "ground_truth_adjudication_v1.txt"


@dataclass(frozen=True)
class AdjudicationResult:
    label: str | None
    confidence: Literal["high", "medium", "low"]
    rationale: str
    tier: Literal["B", "C"]
    adjudicator_model: str
    raw_output: str


class AdjudicatorClient(Protocol):
    def adjudicate(
        self,
        issue: IssueRecord,
        system_prompt: str,
        comments: str = "",
    ) -> AdjudicationResult: ...


def load_adjudication_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _parse_adjudication_response(content: str, model: str) -> AdjudicationResult:
    raw = content.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
        if not match:
            return AdjudicationResult(
                label=None,
                confidence="low",
                rationale="unparseable response",
                tier="C",
                adjudicator_model=model,
                raw_output=raw,
            )
        payload = json.loads(match.group())

    label = str(payload.get("label", "")).lower().strip()
    confidence = str(payload.get("confidence", "medium")).lower().strip()
    rationale = str(payload.get("rationale", ""))

    if label not in CUSTOMER_LABELS:
        return AdjudicationResult(
            label=None,
            confidence="low",
            rationale=f"invalid label: {label}",
            tier="C",
            adjudicator_model=model,
            raw_output=raw,
        )

    if confidence not in {"high", "medium"}:
        confidence = "medium"

    tier: Literal["B", "C"] = "B" if confidence in {"high", "medium"} else "C"
    return AdjudicationResult(
        label=label,
        confidence=confidence,  # type: ignore[arg-type]
        rationale=rationale,
        tier=tier,
        adjudicator_model=model,
        raw_output=raw,
    )


class OpenAIAdjudicator:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://inference.do-ai.run/v1",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def adjudicate(
        self,
        issue: IssueRecord,
        system_prompt: str,
        comments: str = "",
    ) -> AdjudicationResult:
        settings = get_settings()
        prefix = (
            f"Issue #{issue.issue_number}\n"
            f"Native labels: {', '.join(issue.labels) or 'none'}\n"
        )
        body_to_truncate = issue.body
        if comments:
            body_to_truncate += f"\n\n=== Comment Thread ===\n{comments}"

        truncation = truncate_issue_text(
            issue.title,
            body_to_truncate,
            system_prompt=system_prompt,
            body_truncate_chars=settings.body_truncate_chars,
            model_context_tokens=settings.model_context_tokens,
            completion_budget=settings.completion_budget,
            title_overhead_chars=len(prefix) + 32,
        )
        user_content = prefix + truncation.user_content
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        return _parse_adjudication_response(content, self.model)


class MockAdjudicator:
    """Test double: assigns label from simple heuristics."""

    def __init__(self, model: str = "mock-adjudicator") -> None:
        self.model = model

    def adjudicate(
        self,
        issue: IssueRecord,
        system_prompt: str,
        comments: str = "",
    ) -> AdjudicationResult:
        text = (issue.title + " " + issue.body + " " + comments).lower()
        if "security" in text or "cve-" in text:
            label = "security"
        elif "?" in issue.title:
            label = "question"
        elif "doc" in text:
            label = "documentation"
        else:
            label = "other"
        return AdjudicationResult(
            label=label,
            confidence="high",
            rationale="mock adjudication",
            tier="B",
            adjudicator_model=self.model,
            raw_output=json.dumps({"label": label, "confidence": "high", "rationale": "mock"}),
        )
