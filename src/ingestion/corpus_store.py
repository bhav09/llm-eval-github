"""Corpus snapshot storage and validation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from ingestion.models import IssueRecord
from observability.events import (
    CORPUS_LOAD_COMPLETE,
    CORPUS_VALIDATION_FAIL,
    CORPUS_VALIDATION_PASS,
)
from observability.logging import get_logger

log = get_logger()


class RepoManifest(BaseModel):
    repo: str
    version: int
    fetched_at: str
    count: int
    sha256: str
    github_api_version: str = "2022-11-28"
    issues_path: str


class CorpusRootManifest(BaseModel):
    repos: list[RepoManifest] = Field(default_factory=list)


def body_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def enrich_issue(issue: IssueRecord) -> IssueRecord:
    return issue.model_copy(
        update={
            "body_sha256": body_sha256(issue.body),
            "body_length": len(issue.body),
        }
    )


def issues_jsonl_path(corpus_root: Path, repo: str, version: int) -> Path:
    short = repo.split("/")[-1]
    return corpus_root / short / f"v{version}" / "issues.jsonl"


def repo_manifest_path(corpus_root: Path, repo: str, version: int) -> Path:
    short = repo.split("/")[-1]
    return corpus_root / short / f"v{version}" / "manifest.json"


def root_manifest_path(corpus_root: Path) -> Path:
    return corpus_root / "manifest.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_issues_snapshot(
    corpus_root: Path,
    repo: str,
    version: int,
    issues: list[IssueRecord],
) -> RepoManifest:
    enriched = [enrich_issue(issue) for issue in issues]
    path = issues_jsonl_path(corpus_root, repo, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for issue in enriched:
            handle.write(issue.model_dump_json())
            handle.write("\n")
    manifest = RepoManifest(
        repo=repo,
        version=version,
        fetched_at=datetime.now(UTC).isoformat(),
        count=len(enriched),
        sha256=file_sha256(path),
        issues_path=str(path.relative_to(corpus_root)),
    )
    repo_manifest_path(corpus_root, repo, version).write_text(
        manifest.model_dump_json(indent=2),
        encoding="utf-8",
    )
    _update_root_manifest(corpus_root, manifest)
    return manifest


def _update_root_manifest(corpus_root: Path, manifest: RepoManifest) -> None:
    root_path = root_manifest_path(corpus_root)
    if root_path.exists():
        root = CorpusRootManifest.model_validate_json(root_path.read_text(encoding="utf-8"))
    else:
        root = CorpusRootManifest()
    root.repos = [entry for entry in root.repos if entry.repo != manifest.repo]
    root.repos.append(manifest)
    root_path.parent.mkdir(parents=True, exist_ok=True)
    root_path.write_text(root.model_dump_json(indent=2), encoding="utf-8")


def load_issues_from_snapshot(
    corpus_root: Path,
    repo: str,
    version: int | None = None,
) -> list[IssueRecord]:
    if version is None:
        version = latest_version(corpus_root, repo)
    path = issues_jsonl_path(corpus_root, repo, version)
    issues = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                issues.append(IssueRecord.model_validate_json(line))
    log.info(CORPUS_LOAD_COMPLETE, repo=repo, version=version, count=len(issues))
    return issues


def latest_version(corpus_root: Path, repo: str) -> int:
    short = repo.split("/")[-1]
    repo_dir = corpus_root / short
    if not repo_dir.exists():
        raise FileNotFoundError(f"No corpus for repo {repo}")
    versions = []
    for child in repo_dir.iterdir():
        if child.is_dir() and child.name.startswith("v"):
            versions.append(int(child.name[1:]))
    if not versions:
        raise FileNotFoundError(f"No versions for repo {repo}")
    return max(versions)


def validate_snapshot(corpus_root: Path, repo: str, version: int) -> RepoManifest:
    manifest = RepoManifest.model_validate_json(
        repo_manifest_path(corpus_root, repo, version).read_text(encoding="utf-8")
    )
    path = issues_jsonl_path(corpus_root, repo, version)
    line_count = sum(1 for line in path.open(encoding="utf-8") if line.strip())
    errors: list[str] = []
    if line_count != manifest.count:
        errors.append(f"count mismatch: manifest={manifest.count} file={line_count}")
    if file_sha256(path) != manifest.sha256:
        errors.append("sha256 mismatch")
    if errors:
        log.error(CORPUS_VALIDATION_FAIL, repo=repo, version=version, errors=errors)
        raise ValueError("; ".join(errors))
    log.info(CORPUS_VALIDATION_PASS, repo=repo, version=version, count=manifest.count)
    return manifest


def load_jsonl_issues(path: Path) -> list[IssueRecord]:
    issues = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                issues.append(IssueRecord.model_validate_json(line))
    return issues
