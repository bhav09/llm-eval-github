"""Context window budgeting and issue text truncation."""

from __future__ import annotations

from dataclasses import dataclass

CHARS_PER_TOKEN_ESTIMATE = 4


@dataclass(frozen=True)
class TruncationInfo:
    title: str
    body: str
    original_body_chars: int
    sent_body_chars: int
    truncated: bool
    user_content: str


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def truncate_issue_text(
    title: str,
    body: str,
    *,
    system_prompt: str,
    body_truncate_chars: int = 8000,
    model_context_tokens: int = 32768,
    completion_budget: int = 256,
    title_overhead_chars: int = 32,
) -> TruncationInfo:
    original_len = len(body)
    system_tokens = estimate_tokens(system_prompt)
    title_part = f"Title: {title}\n\nBody:\n"
    title_tokens = estimate_tokens(title_part) + estimate_tokens(" " * title_overhead_chars)
    available_body_tokens = model_context_tokens - system_tokens - completion_budget - title_tokens
    max_body_chars_from_tokens = max(0, available_body_tokens * CHARS_PER_TOKEN_ESTIMATE)
    max_body_chars = min(body_truncate_chars, max_body_chars_from_tokens)

    if max_body_chars <= 0:
        truncated_body = ""
        truncated = original_len > 0
    elif original_len <= max_body_chars:
        truncated_body = body
        truncated = False
    else:
        # Perform middle truncation to preserve stack traces/logs at the end
        placeholder = "\n\n... [TRUNCATED LOGS/STACK TRACE CONTD.] ...\n\n"
        placeholder_len = len(placeholder)
        if max_body_chars > placeholder_len + 100:
            first_half_len = max_body_chars // 2
            second_half_len = max_body_chars - first_half_len - placeholder_len
            truncated_body = body[:first_half_len] + placeholder + body[-second_half_len:]
        else:
            truncated_body = body[:max_body_chars]
        truncated = True

    user_content = f"{title_part}{truncated_body}"
    return TruncationInfo(
        title=title,
        body=truncated_body,
        original_body_chars=original_len,
        sent_body_chars=len(truncated_body),
        truncated=truncated,
        user_content=user_content,
    )


def halve_body(truncation: TruncationInfo, system_prompt: str, **kwargs) -> TruncationInfo:
    """Retry helper: halve allowed body size from current truncation."""
    new_cap = max(256, truncation.sent_body_chars // 2)
    return truncate_issue_text(
        truncation.title,
        truncation.body[: new_cap - 1] if truncation.body else "",
        system_prompt=system_prompt,
        body_truncate_chars=new_cap,
        **kwargs,
    )
