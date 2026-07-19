import json
from pathlib import Path
from unittest.mock import patch
from ground_truth.rules_engine import classify_with_rules
from ground_truth.pipeline import get_context_hash, run_pipeline
from ground_truth.adjudicator import MockAdjudicator
from ingestion.models import IssueRecord


def _issue(num: int, title: str = "", body: str = "", labels: list[str] = None) -> IssueRecord:
    return IssueRecord(
        issue_id=f"test/repo#{num}",
        repo="test/repo",
        issue_number=num,
        title=title,
        body=body,
        state="closed",
        created_at="2026-07-19T00:00:00Z",
        updated_at="2026-07-19T00:00:00Z",
        labels=labels or [],
        html_url=f"https://github.com/test/repo/issues/{num}",
    )


def test_density_based_tie_breaker():
    # Title has "how to" (question, score 1)
    # Body has "error", "broken", "crash" (bug, score 3)
    # Since bug score (3) >= 2 * question score (1), it resolves to "bug" with MED confidence
    issue = _issue(1, title="how to use doctl", body="It throws an error and is broken, leading to a crash")
    result = classify_with_rules(issue)
    assert result.proposed_label == "bug"
    assert result.confidence == "MED"
    assert "density resolved" in result.mapping_reason


def test_density_conflict_unresolved():
    # Title has "how to" (question, score 1)
    # Body has "error" (bug, score 1)
    # Since scores are equal (1 vs 1), it cannot resolve and remains unresolved LOW confidence
    issue = _issue(2, title="how to configure", body="I see an error")
    result = classify_with_rules(issue)
    assert result.proposed_label is None
    assert result.confidence == "LOW"
    assert "conflicting heuristics" in result.mapping_reason


def test_native_heuristic_conflict_demotion():
    # Native label is "bug"
    # Text heuristic matches "question" ("how do i...") with score 1
    # Since customer ("bug") != heuristic ("question"), it demotes to LOW confidence
    issue = _issue(3, title="how do i auth init?", body="I don't know where the config is.", labels=["bug"])
    result = classify_with_rules(issue)
    assert result.proposed_label is None
    assert result.confidence == "LOW"
    assert "conflict: native label is 'bug'" in result.mapping_reason


def test_native_heuristic_no_conflict():
    # Native label is "bug"
    # Text heuristic matches "bug" ("crash") with score 1
    # Since categories match, it keeps HIGH confidence
    issue = _issue(4, title="command crash", body="It crashed", labels=["bug"])
    result = classify_with_rules(issue)
    assert result.proposed_label == "bug"
    assert result.confidence == "HIGH"


def test_context_hashing():
    title = "Title"
    body = "Body text"
    comments = "- User: comment"
    prompt = "Prompt instructions"
    h1 = get_context_hash(title, body, comments, prompt)
    h2 = get_context_hash(title, body, comments, prompt)
    h3 = get_context_hash(title, body, "different comments", prompt)
    
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256 length in hex


def test_pipeline_caching_and_run(tmp_path):
    comments_path = tmp_path / "comments_cache.json"
    adj_path = tmp_path / "adjudication_cache.json"
    
    with patch("ground_truth.pipeline.Path") as mock_path:
        def side_effect(val):
            if "comments_cache.json" in str(val):
                return comments_path
            if "adjudication_cache.json" in str(val):
                return adj_path
            return Path(val)
        mock_path.side_effect = side_effect
        
        # Conflict: Title matches "how to" (question, score 1) and body has "error" (bug, score 1)
        issue = _issue(5, title="how to configure?", body="I see an error")
        
        # Run 1: Should trigger adjudicator
        adjudicator = MockAdjudicator()
        result = run_pipeline([issue], adjudicator=adjudicator)
        assert len(result["records"]) == 1
        assert result["records"]["test/repo#5"].source == "llm"
        assert result["records"]["test/repo#5"].label == "question"
        
        assert adj_path.exists()
        
        # Run 2: Cache hit, adjudicate shouldn't be called
        call_count = 0
        original_adjudicate = adjudicator.adjudicate
        def mock_adjudicate(issue_rec, prompt, comments=""):
            nonlocal call_count
            call_count += 1
            return original_adjudicate(issue_rec, prompt, comments)
        adjudicator.adjudicate = mock_adjudicate
        
        result2 = run_pipeline([issue], adjudicator=adjudicator)
        assert result2["records"]["test/repo#5"].source == "llm"
        assert result2["records"]["test/repo#5"].label == "question"
        assert call_count == 0
