"""Tests for stratified model selection."""

from __future__ import annotations

from eval.model_catalog import stratified_select, tag_model


def test_tag_model_parses_known_slug():
    m = tag_model("alibaba-qwen3-32b")
    assert m["family"] == "qwen"
    assert m["parameter_b"] == 32
    assert m["size_class"] == "large"
    assert m["reasoning"] is False
    assert m["instruct"] is True
    assert m["cache_supported"] is True


def test_tag_model_infers_unknown_slug():
    m = tag_model("some-unknown-7b-instruct")
    assert m["family"] == "some"
    assert m["parameter_b"] == 7
    assert m["size_class"] == "small"
    assert m["instruct"] is True


def test_tag_model_reasoning_detection():
    assert tag_model("deepseek-r1-distill-llama-70b")["reasoning"] is True
    assert tag_model("arcee-trinity-large-thinking")["reasoning"] is True
    assert tag_model("mistral-3-14B")["reasoning"] is False


def test_stratified_select_caps_at_k():
    slugs = [
        "alibaba-qwen3-32b",
        "openai-gpt-oss-120b",
        "openai-gpt-oss-20b",
        "llama3.3-70b-instruct",
        "mistral-3-14B",
        "deepseek-r1-distill-llama-70b",
        "deepseek-3.2",
        "glm-5.1",
        "kimi-k2.5",
        "gemma-4-31B-it",
    ]
    selected = stratified_select(slugs, k=6)
    assert len(selected) <= 6
    assert len(selected) >= 1
    # Every selected model has a selection_reason.
    for m in selected:
        assert m["selection_reason"]


def test_stratified_select_covers_distinct_groups():
    # Two small models, two very_large, one reasoning, one medium.
    slugs = [
        "some-7b-instruct",
        "other-7b-chat",
        "big-70b-instruct",
        "huge-120b-instruct",
        "deepseek-r1-distill-llama-70b",
        "mistral-3-14B",
    ]
    selected = stratified_select(slugs, k=6)
    size_classes = {m["size_class"] for m in selected}
    # Should cover at least 3 distinct size classes.
    assert len(size_classes) >= 3
    # Should not pick both 7b models from the small group (one representative per group).
    small = [m for m in selected if m["size_class"] == "small"]
    assert len(small) <= 1


def test_stratified_select_deterministic():
    slugs = [
        "alibaba-qwen3-32b",
        "openai-gpt-oss-120b",
        "mistral-3-14B",
        "deepseek-r1-distill-llama-70b",
        "gemma-4-31B-it",
        "openai-gpt-oss-20b",
    ]
    a = stratified_select(slugs, k=6)
    b = stratified_select(slugs, k=6)
    assert [m["slug"] for m in a] == [m["slug"] for m in b]
