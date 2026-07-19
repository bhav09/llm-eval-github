"""Classification prompt loading and versioning."""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import ROOT_DIR

PROMPT_PATH = ROOT_DIR / "config" / "prompt_classification_v1.txt"


def load_classification_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_version_hash(prompt: str | None = None) -> str:
    text = prompt if prompt is not None else load_classification_prompt()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
