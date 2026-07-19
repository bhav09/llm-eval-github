"""Ground truth label constants and mappings."""

from typing import Final

CUSTOMER_LABELS: Final[frozenset[str]] = frozenset(
    {"bug", "enhancement", "question", "documentation", "security", "other"}
)

# Priority when multiple native category labels exist (highest first)
LABEL_PRIORITY: Final[list[str]] = [
    "security",
    "bug",
    "enhancement",
    "question",
    "documentation",
    "other",
]

NATIVE_TO_CUSTOMER: Final[dict[str, str]] = {
    "bug": "bug",
    "enhancement": "enhancement",
    "suggestion": "enhancement",
    "question": "question",
    "docs": "documentation",
    "security vulnerability": "security",
    "security fix": "security",
    "duplicate": "other",
}

WORKFLOW_LABELS: Final[frozenset[str]] = frozenset(
    {
        "blocked",
        "wontfix",
        "help wanted",
        "good first issue",
        "hacktoberfest",
        "hacktoberfest-accepted",
        "waiting-response",
        "Needs Investigation",
        "DO NOT MERGE",
        "do not merge yet",
        "wip",
        "work-around-available",
    }
)

RULES_VERSION = "v1"
