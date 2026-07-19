from pathlib import Path

from config import ROOT_DIR, get_settings


def test_settings_defaults():
    settings = get_settings()
    assert settings.concurrency == 8
    assert settings.github_repo == "digitalocean/doctl"
    assert settings.corpus_path == Path("data/corpus")


def test_root_dir_exists():
    assert ROOT_DIR.exists()
    assert (ROOT_DIR / "project.md").exists()
