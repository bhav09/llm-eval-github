"""End-to-end funnel test using mock inference."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from eval.funnel import FunnelOrchestrator


@pytest.mark.asyncio
async def test_funnel_runs_all_stages_and_recommends_two(tmp_path: Path, monkeypatch):
    settings = _settings_with_tmp(tmp_path)
    _write_corpus_and_ground_truth(tmp_path)

    orch = FunnelOrchestrator(
        settings=settings,
        db_path=tmp_path / "test_eval.db",
        funnels_dir=tmp_path / "funnels",
    )

    # Stub fetch_live_models to return a fixed set of 6 mock slugs.
    async def fake_fetch_live_models():
        return [
            "some-7b-instruct",
            "mistral-3-14B",
            "alibaba-qwen3-32b",
            "llama3.3-70b-instruct",
            "openai-gpt-oss-120b",
            "deepseek-r1-distill-llama-70b",
        ]

    monkeypatch.setattr("eval.funnel.fetch_live_models", fake_fetch_live_models)

    funnel = await orch.run_funnel(use_mock=True)

    assert funnel.status == "complete"
    assert funnel.stage_reached == 4
    assert funnel.recommended_a is not None
    assert funnel.recommended_b is not None
    assert funnel.recommended_a != funnel.recommended_b
    assert len(funnel.pilot_model_slugs) <= 6
    assert len(funnel.full_model_slugs) >= 2
    assert "Evaluated" in funnel.rationale

    # The funnel should NOT have written the real recommendations.json on a mock run.
    rec_path = Path("config/recommendations.json")
    if rec_path.exists():
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        # The real file should not contain test slugs.
        assert "some-7b-instruct" not in (rec.get("model_a", ""), rec.get("model_b", ""))


@pytest.mark.asyncio
async def test_funnel_eliminates_error_heavy_models(tmp_path: Path, monkeypatch):
    settings = _settings_with_tmp(tmp_path)
    _write_corpus_and_ground_truth(tmp_path)

    # Inject a classifier backend that always errors for one slug. We patch
    # build_classifier (used by run_single) so the runner gets our failing
    # backend for the "always-fails-7b" slug and the normal MockClassifier
    # for everything else.
    from eval.orchestrator import build_classifier as real_build_classifier
    from inference.classifier import MockClassifier
    from inference.models import PredictionRecord

    class AlwaysFailsBackend:
        model = "always-fails-7b"

        def classify(self, issue, system_prompt, truncation):
            raise RuntimeError("intentional failure")

    def fake_build_classifier(model, settings, *, use_mock):
        if model == "always-fails-7b":
            return AlwaysFailsBackend()
        return real_build_classifier(model, settings, use_mock=use_mock)

    monkeypatch.setattr("eval.orchestrator.build_classifier", fake_build_classifier)

    async def fake_fetch_live_models():
        return [
            "always-fails-7b",
            "mistral-3-14B",
            "alibaba-qwen3-32b",
            "llama3.3-70b-instruct",
        ]

    monkeypatch.setattr("eval.funnel.fetch_live_models", fake_fetch_live_models)

    orch = FunnelOrchestrator(
        settings=settings,
        db_path=tmp_path / "test_eval.db",
        funnels_dir=tmp_path / "funnels",
    )
    funnel = await orch.run_funnel(use_mock=True)

    # The always-fails model should not be in the full-eval survivors.
    assert "always-fails-7b" not in funnel.full_model_slugs
    assert funnel.status == "complete"


def _settings_with_tmp(tmp_path: Path):
    from config import Settings

    settings = Settings()
    settings.corpus_path = tmp_path / "corpus"
    settings.ground_truth_path = tmp_path / "ground_truth"
    return settings


def _write_corpus_and_ground_truth(tmp_path: Path):
    import json

    from ingestion.models import IssueRecord, make_issue_id

    corpus_dir = tmp_path / "corpus" / "doctl" / "v1"
    corpus_dir.mkdir(parents=True, exist_ok=True)

    issues = []
    for i in range(1, 21):
        issues.append(
            IssueRecord(
                issue_id=make_issue_id("digitalocean/doctl", i),
                repo="digitalocean/doctl",
                issue_number=i,
                title=f"Issue {i}",
                body=f"Body {i} with some bug crash error text" if i % 2 == 0 else f"Feature request {i}",
                state="open",
                created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                labels=["bug"] if i % 2 == 0 else ["enhancement"],
                html_url=f"https://github.com/digitalocean/doctl/issues/{i}",
                body_length=20,
            )
        )

    with (corpus_dir / "issues.jsonl").open("w", encoding="utf-8") as fh:
        for issue in issues:
            fh.write(json.dumps(issue.model_dump(mode="json")) + "\n")

    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        issue.issue_id: {
            "label": "bug" if i % 2 == 0 else "enhancement",
            "in_scored_set": True,
            "tier": "A",
            "source": "rule",
            "confidence": "HIGH",
        }
        for i, issue in enumerate(issues, 1)
    }
    (gt_dir / "labels.json").write_text(json.dumps(payload), encoding="utf-8")
