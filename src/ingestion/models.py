"""Corpus issue models."""

from datetime import datetime

from pydantic import BaseModel, Field


def make_issue_id(repo: str, issue_number: int) -> str:
    return f"{repo}#{issue_number}"


class IssueRecord(BaseModel):
    issue_id: str
    repo: str
    issue_number: int
    title: str
    body: str = ""
    state: str
    created_at: datetime
    updated_at: datetime
    labels: list[str] = Field(default_factory=list)
    html_url: str
    body_sha256: str = ""
    body_length: int = 0

    @classmethod
    def from_github(cls, repo: str, payload: dict) -> "IssueRecord":
        body = payload.get("body") or ""
        number = payload["number"]
        return cls(
            issue_id=make_issue_id(repo, number),
            repo=repo,
            issue_number=number,
            title=payload.get("title") or "",
            body=body,
            state=payload.get("state") or "open",
            created_at=payload["created_at"],
            updated_at=payload["updated_at"],
            labels=[label["name"] for label in payload.get("labels", [])],
            html_url=payload.get("html_url") or "",
            body_length=len(body),
        )
