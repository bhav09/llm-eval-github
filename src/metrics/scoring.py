"""Classification scoring helpers."""

from __future__ import annotations

from collections import defaultdict

from ground_truth.labels import CUSTOMER_LABELS


def _sorted_labels(labels: set[str] | None = None) -> list[str]:
    return sorted(labels or CUSTOMER_LABELS)


def confusion_matrix(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str] | None = None,
) -> dict[str, dict[str, int]]:
    label_list = labels or _sorted_labels(set(y_true) | set(y_pred))
    matrix: dict[str, dict[str, int]] = {
        truth: {pred: 0 for pred in label_list} for truth in label_list
    }
    for truth, pred in zip(y_true, y_pred, strict=True):
        if truth in matrix and pred in matrix[truth]:
            matrix[truth][pred] += 1
    return matrix


def per_class_metrics(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    label_list = labels or _sorted_labels(set(y_true) | set(y_pred))
    metrics: dict[str, dict[str, float]] = {}
    for label in label_list:
        tp = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == label and pred == label)
        fp = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth != label and pred == label)
        fn = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == label and pred != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": float(tp + fn),
        }
    return metrics


def macro_f1(per_class: dict[str, dict[str, float]]) -> float:
    if not per_class:
        return 0.0
    return round(sum(values["f1"] for values in per_class.values()) / len(per_class), 4)


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    correct = sum(1 for truth, pred in zip(y_true, y_pred, strict=True) if truth == pred)
    return round(correct / len(y_true), 4)


def label_distribution(labels: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for label in labels:
        counts[label] += 1
    return dict(sorted(counts.items()))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return round(ordered[index], 2)
