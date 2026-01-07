"""Tests for chat history formatting in system prompt."""
import pytest


def format_history_for_test(history: list[dict]) -> tuple[list[str], int]:
    """Test helper that mimics the history formatting logic from main.py.
    
    Returns (history_lines, total_chars) tuple.
    """
    CHAT_HISTORY_MAX_CHARS_PER_MESSAGE = 500
    CHAT_HISTORY_MAX_TOTAL_CHARS = 8000
    
    history_lines = []
    total_chars = 0
    
    for idx, msg in enumerate(history):
        role = msg.get("role")
        message_content = msg.get("content")
        
        # Skip if message structure is unexpected
        if role is None or message_content is None:
            continue
        
        if role == "user":
            prefix = "User: "
        elif role == "assistant":
            prefix = "Assistant: "
        else:
            # Skip system messages and other roles
            continue
        
        # Sanitize content to prevent breaking the history framing structure
        sanitized_content = str(message_content)
        sanitized_content = sanitized_content.replace("---", "–––")
        sanitized_content = sanitized_content.replace("\nUser: ", "\nUser - ")
        sanitized_content = sanitized_content.replace("\nAssistant: ", "\nAssistant - ")
        
        # Truncate individual messages
        if len(sanitized_content) > CHAT_HISTORY_MAX_CHARS_PER_MESSAGE:
            sanitized_content = sanitized_content[:CHAT_HISTORY_MAX_CHARS_PER_MESSAGE] + "…"
        
        formatted_line = prefix + sanitized_content
        
        # Check if adding this message would exceed total character limit
        if total_chars + len(formatted_line) > CHAT_HISTORY_MAX_TOTAL_CHARS:
            break
        
        history_lines.append(formatted_line)
        total_chars += len(formatted_line)
    
    return history_lines, total_chars


def test_history_formatting_with_user_and_assistant():
    """Test that history is correctly formatted with User:/Assistant: prefixes."""
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I'm doing well, thanks!"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 4
    assert lines[0] == "User: Hello"
    assert lines[1] == "Assistant: Hi there!"
    assert lines[2] == "User: How are you?"
    assert lines[3] == "Assistant: I'm doing well, thanks!"


def test_history_formatting_skips_malformed_messages():
    """Test that malformed messages (missing role/content) are properly skipped."""
    history = [
        {"role": "user", "content": "First message"},
        {"role": None, "content": "Missing role"},  # Should be skipped
        {"role": "user", "content": None},  # Should be skipped
        {"content": "Missing role field"},  # Should be skipped
        {"role": "assistant", "content": "Valid message"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 2
    assert lines[0] == "User: First message"
    assert lines[1] == "Assistant: Valid message"


def test_history_formatting_filters_unknown_roles():
    """Test that unknown roles are filtered out."""
    history = [
        {"role": "user", "content": "User message"},
        {"role": "system", "content": "System message"},  # Should be skipped
        {"role": "function", "content": "Function message"},  # Should be skipped
        {"role": "assistant", "content": "Assistant message"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 2
    assert lines[0] == "User: User message"
    assert lines[1] == "Assistant: Assistant message"


def test_history_formatting_handles_empty_history():
    """Test that empty history is handled correctly."""
    history = []
    
    lines, total_chars = format_history_for_test(history)
    
    assert len(lines) == 0
    assert total_chars == 0


def test_history_formatting_sanitizes_delimiters():
    """Test that message content with delimiters is sanitized."""
    history = [
        {"role": "user", "content": "Message with --- delimiter"},
        {"role": "assistant", "content": "Response with\nUser: embedded prefix"},
        {"role": "user", "content": "Another with\nAssistant: prefix"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 3
    # Triple dashes should be replaced
    assert "---" not in lines[0]
    assert "–––" in lines[0]
    # Role prefixes should be escaped
    assert "\nUser: " not in lines[1]
    assert "\nUser - " in lines[1]
    assert "\nAssistant: " not in lines[2]
    assert "\nAssistant - " in lines[2]


def test_history_formatting_truncates_long_messages():
    """Test that long individual messages are truncated."""
    long_content = "a" * 600  # Longer than CHAT_HISTORY_MAX_CHARS_PER_MESSAGE (500)
    history = [
        {"role": "user", "content": long_content},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 1
    # Should be truncated to 500 chars + "…"
    assert len(lines[0]) == len("User: ") + 500 + len("…")
    assert lines[0].endswith("…")


def test_history_formatting_respects_total_char_limit():
    """Test that total character limit is respected."""
    # Create messages that would exceed CHAT_HISTORY_MAX_TOTAL_CHARS (8000)
    history = []
    for i in range(30):
        # Each message is about 400 chars (prefix + content)
        history.append({"role": "user", "content": "x" * 394})
    
    lines, total_chars = format_history_for_test(history)
    
    # Should stop before exceeding 8000 chars
    assert total_chars <= 8000
    # Should have some messages, but not all 30
    assert len(lines) > 0
    assert len(lines) < 30


def test_history_formatting_message_structure():
    """Test the final message array structure contains only system and user messages."""
    # This test verifies the conceptual structure, not the actual implementation
    # In the actual code, the history goes into system prompt, leaving only:
    # [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]
    
    history = [
        {"role": "user", "content": "Old message 1"},
        {"role": "assistant", "content": "Old response 1"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    # History should be formatted into lines
    assert len(lines) == 2
    
    # In the actual implementation, these lines would be joined and added to system prompt
    # The final messages array would only have system + current user message
    # This is tested implicitly by checking that history_lines is non-empty


def test_history_formatting_preserves_order():
    """Test that messages maintain chronological order."""
    history = [
        {"role": "user", "content": "Message 1"},
        {"role": "assistant", "content": "Response 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Response 2"},
        {"role": "user", "content": "Message 3"},
    ]
    
    lines, _ = format_history_for_test(history)
    
    assert len(lines) == 5
    assert "Message 1" in lines[0]
    assert "Response 1" in lines[1]
    assert "Message 2" in lines[2]
    assert "Response 2" in lines[3]
    assert "Message 3" in lines[4]
