from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ingestion.github_client import GitHubClient
from ingestion.models import IssueRecord


@pytest.fixture
def github_issue_payload():
    return {
        "number": 42,
        "title": "Bug report",
        "body": "Something broke",
        "state": "open",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "labels": [{"name": "bug"}],
        "html_url": "https://github.com/digitalocean/doctl/issues/42",
    }


def test_fetch_issues_skips_pull_requests(github_issue_payload):
    client = GitHubClient(token="test")
    mock_response = MagicMock()
    mock_response.json.return_value = [
        github_issue_payload,
        {**github_issue_payload, "number": 43, "pull_request": {"url": "x"}},
    ]
    mock_response.raise_for_status = MagicMock()
    client._client = MagicMock()
    client._client.get.return_value = mock_response

    items = list(client.fetch_issues("digitalocean/doctl"))
    assert len(items) == 1
    assert items[0]["number"] == 42


def test_fetch_issue_records(github_issue_payload):
    client = GitHubClient(token="test")
    mock_response = MagicMock()
    mock_response.json.return_value = [github_issue_payload]
    mock_response.raise_for_status = MagicMock()
    client._client = MagicMock()
    client._client.get.return_value = mock_response

    records = client.fetch_issue_records("digitalocean/doctl")
    assert len(records) == 1
    assert isinstance(records[0], IssueRecord)
    assert records[0].issue_id == "digitalocean/doctl#42"
    assert records[0].labels == ["bug"]
