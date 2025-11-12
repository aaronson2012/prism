"""Tests for Discord message truncation logic."""
from prism.main import _clip_reply_to_limit, DISCORD_MESSAGE_LIMIT


def test_clip_reply_under_limit():
    """Test that messages under the limit are not truncated."""
    text = "Short message"
    result, was_truncated = _clip_reply_to_limit(text)
    assert result == text
    assert was_truncated is False


def test_clip_reply_at_limit():
    """Test that messages exactly at the limit are not truncated."""
    text = "x" * DISCORD_MESSAGE_LIMIT
    result, was_truncated = _clip_reply_to_limit(text)
    assert result == text
    assert was_truncated is False


def test_clip_reply_over_limit():
    """Test that messages over the limit are truncated without notice."""
    text = "x" * (DISCORD_MESSAGE_LIMIT + 100)
    result, was_truncated = _clip_reply_to_limit(text)
    assert len(result) <= DISCORD_MESSAGE_LIMIT
    assert was_truncated is True
    # Ensure no truncation notice is added
    assert "(Reply truncated" not in result
    assert "character limit" not in result


def test_clip_reply_removes_partial_emoji():
    """Test that partial custom emoji tokens are removed during truncation."""
    # Create a message that would leave a partial emoji token at the end
    base = "x" * (DISCORD_MESSAGE_LIMIT - 10)
    emoji_token = "<:test:123456789>"
    text = base + emoji_token
    
    result, was_truncated = _clip_reply_to_limit(text)
    assert len(result) <= DISCORD_MESSAGE_LIMIT
    assert was_truncated is True
    # Ensure no partial emoji tokens remain
    if "<" in result:
        # If there's a <, there should be a matching >
        last_open = result.rfind("<")
        assert ">" in result[last_open:]


def test_clip_reply_closes_code_blocks():
    """Test that unclosed code blocks are handled during truncation."""
    # Create a message with an unclosed code block that exceeds limit
    text = "x" * (DISCORD_MESSAGE_LIMIT - 50) + "\n```python\n" + "code here" * 100
    
    result, was_truncated = _clip_reply_to_limit(text)
    assert len(result) <= DISCORD_MESSAGE_LIMIT
    assert was_truncated is True
    # The function should either close the code block or remove it
    # Check that we don't have an odd number of ```
    assert result.count("```") % 2 == 0 or result.count("```") == 0


def test_clip_reply_empty_input():
    """Test handling of empty input."""
    result, was_truncated = _clip_reply_to_limit("")
    assert result == ""
    assert was_truncated is False


def test_clip_reply_whitespace_handling():
    """Test that trailing whitespace is removed after truncation."""
    text = "x" * (DISCORD_MESSAGE_LIMIT - 5) + "     " + "y" * 20
    result, was_truncated = _clip_reply_to_limit(text)
    assert len(result) <= DISCORD_MESSAGE_LIMIT
    assert was_truncated is True
    # Ensure no trailing whitespace
    assert result == result.rstrip()
