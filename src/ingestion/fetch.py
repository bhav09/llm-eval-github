"""Fetch GitHub issues and persist corpus snapshot."""

from __future__ import annotations

import argparse
import time

from config import get_settings
from ingestion.corpus_store import latest_version, write_issues_snapshot
from ingestion.github_client import GitHubClient
from ingestion.models import IssueRecord
from observability.events import CORPUS_FETCH_COMPLETE, CORPUS_FETCH_PAGE, CORPUS_FETCH_START
from observability.logging import configure_logging, get_logger


def fetch_and_store(repo: str, version: int | None = None) -> int:
    configure_logging()
    log = get_logger()
    settings = get_settings()
    corpus_root = settings.resolve_path(settings.corpus_path)

    if version is None:
        try:
            version = latest_version(corpus_root, repo) + 1
        except FileNotFoundError:
            version = 1

    log.info(CORPUS_FETCH_START, repo=repo, version=version)
    started = time.perf_counter()

    with GitHubClient(token=settings.github_token, api_base=settings.github_api_base) as client:
        records: list[IssueRecord] = []
        for raw in client.fetch_issues(repo):
            records.append(IssueRecord.from_github(repo, raw))
            if len(records) % 100 == 0:
                log.info(CORPUS_FETCH_PAGE, repo=repo, fetched=len(records))

    manifest = write_issues_snapshot(corpus_root, repo, version, records)
    duration = time.perf_counter() - started
    log.info(
        CORPUS_FETCH_COMPLETE,
        repo=repo,
        version=version,
        count=manifest.count,
        duration_sec=round(duration, 2),
    )
    return manifest.count


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GitHub issues into corpus snapshot")
    parser.add_argument("--repo", default=None, help="owner/name")
    parser.add_argument("--version", type=int, default=None)
    args = parser.parse_args()
    settings = get_settings()
    repo = args.repo or settings.github_repo
    count = fetch_and_store(repo, args.version)
    print(f"Stored {count} issues for {repo}")


if __name__ == "__main__":
    main()
