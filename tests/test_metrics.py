from inference.models import PredictionRecord
from metrics.accumulator import MetricsAccumulator, compute_run_metrics
from metrics.scoring import accuracy, confusion_matrix, macro_f1, per_class_metrics


def _pred(issue_id: str, model: str, label: str, *, status: str = "ok") -> PredictionRecord:
    return PredictionRecord(
        run_id="r1",
        issue_id=issue_id,
        model=model,
        prompt_version="v1",
        predicted_label=label if status == "ok" else None,
        status=status,
        latency_ms=10.0,
        prompt_tokens=100,
        cached_tokens=50,
        cost_usd=0.001,
        cache_savings_usd=0.0002,
    )


def test_scoring_helpers():
    y_true = ["bug", "enhancement", "bug"]
    y_pred = ["bug", "bug", "other"]
    assert accuracy(y_true, y_pred) == 0.3333
    per_class = per_class_metrics(y_true, y_pred)
    assert "bug" in per_class
    assert macro_f1(per_class) >= 0
    matrix = confusion_matrix(y_true, y_pred)
    assert matrix["bug"]["bug"] == 1


def test_metrics_accumulator_scored_and_ops():
    accumulator = MetricsAccumulator()
    accumulator.update(_pred("i1", "model-a", "bug"), ground_truth="bug", scored=True)
    accumulator.update(_pred("i1", "model-b", "bug"), ground_truth="bug", scored=True)
    accumulator.update(_pred("i2", "model-a", "enhancement"), ground_truth="bug", scored=True)
    accumulator.update(_pred("i2", "model-b", "bug"), ground_truth="bug", scored=True)
    metrics = accumulator.finalize("model-a", "model-b")
    assert metrics["model_a"]["scored"]["count"] == 2
    assert metrics["comparison"]["agreement_rate"] == 0.5
    assert metrics["comparison"]["disagreement_count"] == 1


def test_compute_run_metrics_excludes_failed_from_scored():
    predictions = [
        _pred("i1", "model-a", "bug"),
        _pred("i1", "model-b", "bug"),
        _pred("i2", "model-a", "bug", status="error"),
        _pred("i2", "model-b", "bug"),
    ]
    metrics = compute_run_metrics(
        predictions,
        ground_truth={"i1": "bug", "i2": "bug"},
        scored_issue_ids={"i1", "i2"},
        model_a="model-a",
        model_b="model-b",
    )
    assert metrics["model_a"]["scored"]["count"] == 1
    assert metrics["model_a"]["failed_count"] == 1
