"""Streaming metrics accumulator for eval runs."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ground_truth.labels import CUSTOMER_LABELS
from inference.models import PredictionRecord
from metrics.scoring import (
    accuracy,
    confusion_matrix,
    label_distribution,
    macro_f1,
    percentile,
    per_class_metrics,
)
from observability.logging import get_logger

log = get_logger()


@dataclass
class ModelMetricsState:
    latencies_ms: list[float] = field(default_factory=list)
    costs_usd: list[float] = field(default_factory=list)
    cache_savings_usd: list[float] = field(default_factory=list)
    cached_tokens: int = 0
    prompt_tokens: int = 0
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    ok_count: int = 0
    failed_count: int = 0
    predicted_labels: list[str] = field(default_factory=list)
    scored_true: list[str] = field(default_factory=list)
    scored_pred: list[str] = field(default_factory=list)


class MetricsAccumulator:
    """Incrementally aggregate prediction rows without loading all into memory at once."""

    def __init__(self, labels: set[str] | None = None) -> None:
        self.labels = sorted(labels or CUSTOMER_LABELS)
        self.models: dict[str, ModelMetricsState] = defaultdict(ModelMetricsState)
        self.agreement_total = 0
        self.agreement_matches = 0
        self.disagreements: list[dict] = []
        self._pair_preds: dict[str, dict[str, str]] = defaultdict(dict)

    def update(
        self,
        prediction: PredictionRecord,
        *,
        ground_truth: str | None = None,
        scored: bool = False,
    ) -> None:
        state = self.models[prediction.model]
        state.latencies_ms.append(prediction.latency_ms)
        state.costs_usd.append(prediction.cost_usd)
        state.cache_savings_usd.append(prediction.cache_savings_usd)
        state.cached_tokens += prediction.cached_tokens
        state.prompt_tokens += prediction.prompt_tokens

        if prediction.status == "ok" and prediction.predicted_label:
            state.ok_count += 1
            state.predicted_labels.append(prediction.predicted_label)
            if scored and ground_truth:
                state.scored_true.append(ground_truth)
                state.scored_pred.append(prediction.predicted_label)
        else:
            state.failed_count += 1
            state.errors[prediction.error_type or "unknown"] += 1

        self._pair_preds[prediction.issue_id][prediction.model] = prediction.predicted_label or ""

    def finalize_pairwise(self, model_a: str, model_b: str) -> None:
        for issue_id, preds in self._pair_preds.items():
            label_a = preds.get(model_a)
            label_b = preds.get(model_b)
            if label_a is None or label_b is None:
                continue
            self.agreement_total += 1
            if label_a == label_b:
                self.agreement_matches += 1
            else:
                self.disagreements.append(
                    {
                        "issue_id": issue_id,
                        "model_a": model_a,
                        "model_a_label": label_a,
                        "model_b": model_b,
                        "model_b_label": label_b,
                    }
                )

    def model_summary(self, model: str) -> dict:
        state = self.models[model]
        total_calls = state.ok_count + state.failed_count
        scored_accuracy = accuracy(state.scored_true, state.scored_pred)
        per_class = per_class_metrics(state.scored_true, state.scored_pred, self.labels)
        return {
            "model": model,
            "total_calls": total_calls,
            "ok_count": state.ok_count,
            "failed_count": state.failed_count,
            "error_breakdown": dict(state.errors),
            "latency_ms": {
                "p50": percentile(state.latencies_ms, 50),
                "p95": percentile(state.latencies_ms, 95),
                "p99": percentile(state.latencies_ms, 99),
            },
            "cost_usd": {
                "total": round(sum(state.costs_usd), 6),
                "per_call": round(sum(state.costs_usd) / total_calls, 6) if total_calls else 0.0,
                "cache_savings_total": round(sum(state.cache_savings_usd), 6),
            },
            "cache": {
                "prompt_tokens": state.prompt_tokens,
                "cached_tokens": state.cached_tokens,
                "hit_rate": round(state.cached_tokens / state.prompt_tokens, 4)
                if state.prompt_tokens
                else 0.0,
            },
            "label_distribution": label_distribution(state.predicted_labels),
            "scored": {
                "count": len(state.scored_true),
                "accuracy": scored_accuracy,
                "macro_f1": macro_f1(per_class),
                "per_class": per_class,
                "confusion_matrix": confusion_matrix(state.scored_true, state.scored_pred, self.labels),
            },
        }

    def finalize(self, model_a: str, model_b: str) -> dict:
        self.finalize_pairwise(model_a, model_b)
        agreement_rate = (
            round(self.agreement_matches / self.agreement_total, 4) if self.agreement_total else 0.0
        )
        return {
            "model_a": self.model_summary(model_a),
            "model_b": self.model_summary(model_b),
            "comparison": {
                "agreement_rate": agreement_rate,
                "agreement_total": self.agreement_total,
                "disagreement_count": len(self.disagreements),
                "disagreements": self.disagreements,
            },
        }


def compute_run_metrics(
    predictions: list[PredictionRecord],
    *,
    ground_truth: dict[str, str],
    scored_issue_ids: set[str],
    model_a: str,
    model_b: str,
) -> dict:
    started = time.perf_counter()
    log.info("metrics.compute.start", rows=len(predictions))
    accumulator = MetricsAccumulator()
    for prediction in predictions:
        truth = ground_truth.get(prediction.issue_id)
        accumulator.update(
            prediction,
            ground_truth=truth,
            scored=prediction.issue_id in scored_issue_ids and truth is not None,
        )
    metrics = accumulator.finalize(model_a, model_b)
    log.info(
        "metrics.compute.complete",
        rows=len(predictions),
        duration_sec=round(time.perf_counter() - started, 4),
    )
    return metrics


def load_predictions_stream(path: Path) -> list[PredictionRecord]:
    predictions = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                predictions.append(PredictionRecord.model_validate_json(line))
    return predictions


def write_metrics(path: Path, metrics: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
