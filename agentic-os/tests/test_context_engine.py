from unittest.mock import patch

from agent.context_engine import (
    MEMORY_CONTEXT_MAX_CHARS,
    _MEMORY_CONTEXT_HEAD_CHARS,
    _MEMORY_CONTEXT_TAIL_CHARS,
    _MEMORY_CONTEXT_TRUNCATION_MARKER,
    sanitize_memory_context,
)


def test_sanitize_memory_context_empty():
    assert sanitize_memory_context("") == ""
    assert sanitize_memory_context("   \n   ") == ""


def test_sanitize_memory_context_no_redaction_needed():
    text = "Hello, this is a normal memory context."
    # Should strip whitespace
    assert sanitize_memory_context(f"   {text}   ") == text


def test_sanitize_memory_context_redaction():
    # Should redact sensitive info like openai keys
    text = "Here is my key: sk-svcacct-test1234567890abcdef"
    sanitized = sanitize_memory_context(text)
    assert "sk-svcacct-test1234567890abcdef" not in sanitized
    assert "..." in sanitized # mask_secret uses '...' by default for long secrets instead of "***" in some cases, or leaves prefix and suffix.


@patch("agent.context_engine.redact_sensitive_text")
def test_sanitize_memory_context_calls_redact(mock_redact):
    mock_redact.return_value = "clean text"

    result = sanitize_memory_context("  dirty text  ")

    mock_redact.assert_called_once_with(
        "dirty text",
        force=True,
        redact_url_credentials=True,
    )
    assert result == "clean text"


def test_sanitize_memory_context_exact_max_chars():
    # Create a string exactly equal to max chars that doesn't trigger redaction
    # using 'a' * 6000
    text = "a" * MEMORY_CONTEXT_MAX_CHARS

    result = sanitize_memory_context(text)

    assert len(result) == MEMORY_CONTEXT_MAX_CHARS
    assert result == text


def test_sanitize_memory_context_truncation():
    # Create a string larger than max chars
    head_content = "H" * _MEMORY_CONTEXT_HEAD_CHARS
    tail_content = "T" * _MEMORY_CONTEXT_TAIL_CHARS
    middle_content = "M" * 2000 # To push it over the 6000 max

    text = head_content + middle_content + tail_content

    result = sanitize_memory_context(text)

    expected_result = (
        head_content + _MEMORY_CONTEXT_TRUNCATION_MARKER + tail_content
    )

    assert result == expected_result
