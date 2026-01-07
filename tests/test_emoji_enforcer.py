"""Tests for emoji enforcer module."""
from prism.services.emoji_enforcer import (
    has_emoji,
    ensure_emoji_per_sentence,
    deduplicate_custom_emojis,
    declump_custom_emojis,
    fallback_add_custom_emoji,
    enforce_emoji_distribution,
    strip_invalid_emoji_shortcodes,
)


def test_has_emoji_with_custom():
    """Test detection of custom Discord emojis."""
    assert has_emoji("Hello <:smile:123456>")
    assert has_emoji("Test <a:dancing:789>")
    assert not has_emoji("No emoji here")


def test_ensure_emoji_per_sentence_adds_to_missing():
    """Test that emojis are added to sentences without them."""
    text = "First sentence. Second sentence. Third sentence."
    custom = ["<:test:123>", "<:test2:456>"]
    unicode = []
    
    result = ensure_emoji_per_sentence(text, custom, unicode)
    
    # Should have added emojis
    assert "<:test:123>" in result or "<:test2:456>" in result
    # Sentences should still be intact
    assert "First sentence" in result
    assert "Second sentence" in result


def test_ensure_emoji_per_sentence_preserves_existing():
    """Test that sentences with emojis are not modified."""
    text = "Has emoji <:smile:123>. No emoji here."
    custom = ["<:test:456>"]
    unicode = []
    
    result = ensure_emoji_per_sentence(text, custom, unicode)
    
    # Original emoji should still be there
    assert "<:smile:123>" in result
    # Should have added to second sentence
    assert "<:test:456>" in result


def test_ensure_emoji_per_sentence_respects_max_length():
    """Test that result doesn't exceed max length."""
    text = "A" * 1800
    custom = ["<:test:123>"]
    unicode = []
    
    result = ensure_emoji_per_sentence(text, custom, unicode, max_length=1900)
    
    # If it can't add safely, should return original
    assert len(result) <= 1900


def test_deduplicate_custom_emojis():
    """Test removal of duplicate custom emojis."""
    text = "Test <:smile:123> and <:wave:456> and <:smile:123> again"
    
    result = deduplicate_custom_emojis(text)
    
    # Should only have one occurrence of :smile:123
    assert result.count("<:smile:123>") == 1
    assert "<:wave:456>" in result


def test_deduplicate_custom_emojis_preserves_order():
    """Test that first occurrence is kept."""
    text = "<:a:1> <:b:2> <:a:1>"
    
    result = deduplicate_custom_emojis(text)
    
    # Should keep first :a:1 and remove second
    parts = result.split()
    assert parts[0] == "<:a:1>"
    assert parts[1] == "<:b:2>"
    assert len(parts) == 2


def test_declump_custom_emojis():
    """Test collapsing of adjacent custom emojis."""
    text = "Test <:a:1> <:b:2> <:c:3> here"
    
    result = declump_custom_emojis(text)
    
    # Should collapse to single emoji
    assert result == "Test <:a:1> here"


def test_declump_custom_emojis_preserves_spaced():
    """Test that well-spaced emojis are preserved."""
    text = "Word <:a:1> another <:b:2> word"
    
    result = declump_custom_emojis(text)
    
    # Should keep both since they're not adjacent
    assert "<:a:1>" in result
    assert "<:b:2>" in result


def test_fallback_add_custom_emoji_when_missing():
    """Test adding emoji when none present."""
    text = "This has no custom emoji."
    custom = ["<:test:123>"]
    
    result = fallback_add_custom_emoji(text, custom)
    
    assert "<:test:123>" in result
    assert "This has no custom emoji" in result


def test_fallback_add_custom_emoji_skips_if_present():
    """Test that emoji is not added if already present."""
    text = "Already has <:smile:456> emoji."
    custom = ["<:test:123>"]
    
    result = fallback_add_custom_emoji(text, custom)
    
    # Should not add new emoji
    assert result == text
    assert "<:test:123>" not in result


def test_fallback_add_custom_emoji_after_sentence():
    """Test that emoji is added after first sentence."""
    text = "First sentence. Second sentence."
    custom = ["<:test:123>"]
    
    result = fallback_add_custom_emoji(text, custom)
    
    # Should appear after first sentence
    first_part = result.split("Second")[0]
    assert "<:test:123>" in first_part


def test_enforce_emoji_distribution_integration():
    """Test complete emoji enforcement pipeline."""
    text = "First. Second. First."
    custom = ["<:a:1>", "<:b:2>"]
    unicode = ["😀", "😊"]
    
    result = enforce_emoji_distribution(text, custom, unicode)
    
    # Should have emojis
    assert "<:a:1>" in result or "<:b:2>" in result or "😀" in result or "😊" in result
    # Original text should be preserved
    assert "First" in result
    assert "Second" in result


def test_enforce_emoji_distribution_empty_tokens():
    """Test that empty token lists don't crash."""
    text = "Test sentence."
    
    result = enforce_emoji_distribution(text, [], [])
    
    # Should return unchanged
    assert result == text


def test_enforce_emoji_distribution_empty_text():
    """Test that empty text is handled gracefully."""
    result = enforce_emoji_distribution("", ["<:test:123>"], ["😀"])

    assert result == ""


def test_strip_invalid_emoji_shortcodes_basic():
    """Test stripping of invalid emoji shortcodes."""
    text = "Hello :invalidemoji: world"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == "Hello world"


def test_strip_invalid_emoji_shortcodes_double_space():
    """Test that double spaces are collapsed to single space."""
    text = "Hello :fake: there"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == "Hello there"
    assert "  " not in result


def test_strip_invalid_emoji_shortcodes_multiple():
    """Test stripping multiple invalid shortcodes."""
    text = "Start :one: middle :two: end"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == "Start middle end"
    assert ":one:" not in result
    assert ":two:" not in result


def test_strip_invalid_emoji_shortcodes_preserves_valid_custom():
    """Test that valid Discord custom emojis are not stripped."""
    text = "Hello <:smile:123456> world"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == text


def test_strip_invalid_emoji_shortcodes_preserves_animated():
    """Test that animated Discord emojis are not stripped."""
    text = "Hello <a:dancing:789> world"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == text


def test_strip_invalid_emoji_shortcodes_no_colons():
    """Test that text without colons is returned unchanged."""
    text = "No colons here"
    result = strip_invalid_emoji_shortcodes(text)
    assert result == text


def test_strip_invalid_emoji_shortcodes_empty():
    """Test that empty string is handled gracefully."""
    assert strip_invalid_emoji_shortcodes("") == ""


def test_strip_invalid_emoji_shortcodes_at_boundaries():
    """Test stripping at start and end of text."""
    assert strip_invalid_emoji_shortcodes(":start: text") == "text"
    assert strip_invalid_emoji_shortcodes("text :end:") == "text"


def test_enforce_emoji_distribution_strips_invalid():
    """Test that enforce_emoji_distribution strips invalid shortcodes."""
    text = "Hello :fake: world."
    result = enforce_emoji_distribution(text, [], [])
    assert ":fake:" not in result
    assert "  " not in result


def test_strip_invalid_emoji_shortcodes_preserves_valid_unicode():
    """Test that valid Unicode emoji shortcodes are preserved."""
    # Test with valid Unicode emoji shortcodes
    text = "Hello :fire: world"
    result = strip_invalid_emoji_shortcodes(text)
    assert ":fire:" in result
    assert result == "Hello :fire: world"


def test_strip_invalid_emoji_shortcodes_mixed_valid_invalid():
    """Test mixed valid and invalid shortcodes."""
    text = "Valid :fire: and invalid :fakemoji: here"
    result = strip_invalid_emoji_shortcodes(text)
    # Valid emoji should be preserved
    assert ":fire:" in result
    # Invalid emoji should be removed
    assert ":fakemoji:" not in result
    # Check overall structure
    assert "Valid :fire: and invalid here" == result


def test_strip_invalid_emoji_shortcodes_multiple_valid():
    """Test multiple valid Unicode emoji shortcodes."""
    text = "Love :red_heart: and fire :fire: and thumbs :thumbs_up:"
    result = strip_invalid_emoji_shortcodes(text)
    assert ":red_heart:" in result
    assert ":fire:" in result
    assert ":thumbs_up:" in result
    assert result == text

