"""GitHub API client for issue ingestion."""

from __future__ import annotations

from typing import Iterator

import httpx

from ingestion.models import IssueRecord


class GitHubClient:
    def __init__(
        self,
        token: str = "",
        api_base: str = "https://api.github.com",
        timeout: float = 30.0,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=api_base, headers=headers, timeout=timeout)
        self.api_base = api_base

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_issues(
        self,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 100,
    ) -> Iterator[dict]:
        owner, name = repo.split("/", 1)
        page = 1
        while True:
            response = self._client.get(
                f"/repos/{owner}/{name}/issues",
                params={"state": state, "per_page": per_page, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            for item in batch:
                if "pull_request" in item:
                    continue
                yield item
            if len(batch) < per_page:
                break
            page += 1

    def fetch_issue_records(self, repo: str) -> list[IssueRecord]:
        return [IssueRecord.from_github(repo, item) for item in self.fetch_issues(repo)]

    def fetch_issue_comments(self, repo: str, issue_number: int) -> list[dict]:
        owner, name = repo.split("/", 1)
        try:
            response = self._client.get(f"/repos/{owner}/{name}/issues/{issue_number}/comments")
            response.raise_for_status()
            return response.json()
        except Exception:
            return []
