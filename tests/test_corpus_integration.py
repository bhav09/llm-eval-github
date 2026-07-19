from config import get_settings
from ground_truth.rules_engine import apply_rules_to_corpus
from ingestion.corpus_store import load_issues_from_snapshot, validate_snapshot


def test_real_corpus_snapshot_validates():
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)
    manifest = validate_snapshot(corpus_root, "digitalocean/doctl", 1)
    assert manifest.count >= 500


def test_real_corpus_rules_coverage():
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)
    issues = load_issues_from_snapshot(corpus_root, "digitalocean/doctl", 1)
    rules = apply_rules_to_corpus(issues)
    high = sum(1 for result in rules.values() if result.confidence == "HIGH")
    assert len(issues) >= 500
    assert high >= 200
