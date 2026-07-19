import pytest
from datetime import datetime, timezone

from ingestion.models import IssueRecord, make_issue_id


@pytest.fixture
def sample_issue() -> IssueRecord:
    return IssueRecord(
        issue_id=make_issue_id("digitalocean/doctl", 1),
        repo="digitalocean/doctl",
        issue_number=1,
        title="Login fails on Windows",
        body="The auth command crashes with error code 1",
        state="open",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        labels=["bug"],
        html_url="https://github.com/digitalocean/doctl/issues/1",
        body_length=42,
    )
