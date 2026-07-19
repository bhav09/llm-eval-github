import json

from inference.classifier import MockClassifier, build_truncation, classify_issue_with_retries, parse_label
from inference.prompt import load_classification_prompt


def test_parse_label_valid_json():
    label, raw = parse_label(json.dumps({"label": "bug"}))
    assert label == "bug"
    assert raw


def test_parse_label_invalid():
    label, _ = parse_label("not json")
    assert label is None


def test_mock_classifier(sample_issue):
    prompt = load_classification_prompt()
    truncation = build_truncation(sample_issue, prompt)
    backend = MockClassifier()
    output = backend.classify(sample_issue, prompt, truncation)
    assert output.label == "bug"
    assert output.cached_tokens > 0


def test_classify_issue_with_retries(sample_issue):
    prompt = load_classification_prompt()
    record = classify_issue_with_retries(
        MockClassifier(),
        sample_issue,
        run_id="test-run",
        prompt_version="v1",
        system_prompt=prompt,
    )
    assert record.status == "ok"
    assert record.predicted_label == "bug"
    assert record.run_id == "test-run"
