from inference.context import estimate_tokens, truncate_issue_text


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 8) == 2


def test_truncate_issue_text_respects_char_cap():
    system_prompt = "x" * 100
    body = "y" * 20000
    info = truncate_issue_text(
        "Short title",
        body,
        system_prompt=system_prompt,
        body_truncate_chars=1000,
        model_context_tokens=32768,
    )
    assert info.truncated
    assert info.sent_body_chars <= 1000
    assert "Title: Short title" in info.user_content


def test_truncate_issue_text_small_body_not_truncated():
    system_prompt = "classify issues"
    body = "small body"
    info = truncate_issue_text("Title", body, system_prompt=system_prompt)
    assert not info.truncated
    assert info.sent_body_chars == len(body)
