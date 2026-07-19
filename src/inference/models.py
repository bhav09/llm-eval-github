"""Inference request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

PredictionStatus = Literal["ok", "error"]


class PredictionRecord(BaseModel):
    run_id: str
    issue_id: str
    model: str
    prompt_version: str
    predicted_label: str | None = None
    raw_output: str = ""
    status: PredictionStatus = "ok"
    error_type: str | None = None
    retry_count: int = 0
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    cache_savings_usd: float = 0.0
    truncated: bool = False
    original_body_chars: int = 0
    sent_body_chars: int = 0


class CheckpointState(BaseModel):
    run_id: str
    model: str = ""
    prompt_version: str
    completed_keys: list[str] = Field(default_factory=list)
    completed_issue_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def migrate_completed_ids(self) -> "CheckpointState":
        if self.completed_issue_ids and not self.completed_keys:
            self.completed_keys = list(self.completed_issue_ids)
        return self
