"""Emoji enforcement logic for Discord messages.

This module handles automatic emoji addition, deduplication, and distribution
in bot responses to ensure engaging, non-repetitive emoji usage.
"""
from __future__ import annotations

import re

# Pattern for invalid/hallucinated emoji shortcodes like :invalidemoji:
# These are NOT valid Discord custom emoji tokens (which look like <:name:id>)
# Uses negative lookbehind (?<!<a?)(?<!<) to avoid matching inside valid tokens
_INVALID_EMOJI_PATTERN = re.compile(r"(\s?)(?<!<)(?<!<a):([A-Za-z0-9_]+):(?!\d+>)(\s?)")

# Cache emoji library availability at module level for performance
_EMOJI_LIB: object | None = None
_EMOJI_LIB_CHECKED = False

def _get_emoji_lib() -> object | None:
    """Get cached emoji library or None if not available."""
    global _EMOJI_LIB, _EMOJI_LIB_CHECKED
    if not _EMOJI_LIB_CHECKED:
        try:
            import emoji as _emoji_lib  # type: ignore
            _EMOJI_LIB = _emoji_lib
        except (ImportError, Exception):
            _EMOJI_LIB = None
        _EMOJI_LIB_CHECKED = True
    return _EMOJI_LIB


def strip_invalid_emoji_shortcodes(text: str) -> str:
    """Remove hallucinated emoji shortcodes like :invalidemoji: from text.

    AI models sometimes hallucinate emoji shortcodes that don't exist in Discord.
    These look like :name: but are NOT valid Discord custom emoji tokens
    (which have the format <:name:id> or <a:name:id>).

    This function strips these invalid shortcodes while preserving valid Unicode
    emoji shortcodes (e.g., :fire:, :thumbs_up:) and normalizes surrounding
    whitespace to avoid double spaces.

    Args:
        text: Text potentially containing invalid emoji shortcodes

    Returns:
        Text with invalid shortcodes removed and whitespace normalized
    """
    if not text or ":" not in text:
        return text

    emoji_lib = _get_emoji_lib()
    # Check once if emoji library has the emojize method we need
    has_emojize = emoji_lib is not None and hasattr(emoji_lib, "emojize")

    def _replace_invalid(match: re.Match) -> str:
        shortcode_name = match.group(2)
        shortcode = f":{shortcode_name}:"
        
        # Check if this is a valid Unicode emoji shortcode
        if has_emojize:
            try:
                converted = emoji_lib.emojize(shortcode, language="en")
                # The emoji library's emojize() returns the Unicode emoji character
                # if the shortcode is valid, otherwise returns the shortcode unchanged.
                # We rely on this behavior to determine validity.
                if converted != shortcode:
                    # Keep the shortcode as-is
                    return match.group(0)
            except Exception:
                # If emoji library fails, treat as invalid
                pass
        
        # Invalid shortcode - remove it and normalize whitespace
        leading_space = match.group(1)
        trailing_space = match.group(3)
        # If there was space on both sides, collapse to single space
        if leading_space and trailing_space:
            return " "
        # Otherwise remove entirely
        return ""

    return _INVALID_EMOJI_PATTERN.sub(_replace_invalid, text)


def has_emoji(text: str) -> bool:
    """Check if text contains any emoji (Unicode or custom Discord emoji)."""
    if not text:
        return False

    # Check for custom Discord emoji
    if re.search(r"<a?:[A-Za-z0-9_]+:\d+>", text):
        return True

    # Check for Unicode emoji using cached emoji library
    emoji_lib = _get_emoji_lib()
    if emoji_lib and hasattr(emoji_lib, "emoji_list"):
        try:
            return bool(emoji_lib.emoji_list(text))
        except Exception:
            pass

    # Fallback: check for common emoji Unicode ranges if library unavailable
    # This catches basic emojis even without the emoji library
    for char in text:
        code = ord(char)
        # Common emoji ranges
        if (0x1F600 <= code <= 0x1F64F or  # Emoticons
            0x1F300 <= code <= 0x1F5FF or  # Misc Symbols and Pictographs
            0x1F680 <= code <= 0x1F6FF or  # Transport and Map
            0x1F1E0 <= code <= 0x1F1FF or  # Flags
            0x2600 <= code <= 0x26FF or    # Misc symbols
            0x2700 <= code <= 0x27BF or    # Dingbats
            0xFE00 <= code <= 0xFE0F or    # Variation Selectors
            0x1F900 <= code <= 0x1F9FF or  # Supplemental Symbols
            0x1FA00 <= code <= 0x1FA6F or  # Chess Symbols, Extended-A
            0x1FA70 <= code <= 0x1FAFF):   # Symbols Extended-A
            return True

    return False


def ensure_emoji_per_sentence(
    text: str,
    custom_tokens: list[str],
    unicode_tokens: list[str],
    max_length: int = 1900
) -> str:
    """Ensure each sentence has at least one emoji.
    
    Args:
        text: The text to process
        custom_tokens: List of custom Discord emoji tokens to use
        unicode_tokens: List of Unicode emoji tokens to use
        max_length: Maximum allowed length for the result
        
    Returns:
        Text with emojis added to sentences that lack them
    """
    if not text or not (custom_tokens or unicode_tokens):
        return text
    
    # Split on sentence boundaries while keeping delimiters
    parts = re.split(r"(\s*(?<=[.!?])\s+)", text)
    
    if not parts or len(parts) == 1:
        return text
    
    out_parts = []
    idx_ctok = 0
    idx_utok = 0
    
    for i, seg in enumerate(parts):
        if i % 2 == 0:  # sentence chunk
            s = seg
            if s.strip() and not has_emoji(s):
                tok = None
                if custom_tokens:
                    tok = custom_tokens[idx_ctok % len(custom_tokens)]
                    idx_ctok += 1
                elif unicode_tokens:
                    tok = unicode_tokens[idx_utok % len(unicode_tokens)]
                    idx_utok += 1

                if tok:
                    # Check for trailing whitespace before stripping
                    had_trailing_space = s.endswith(" ")
                    # Append emoji after content, preserving trailing space if present
                    s = s.rstrip() + " " + tok + (" " if had_trailing_space else "")
            out_parts.append(s)
        else:
            out_parts.append(seg)
    
    candidate = "".join(out_parts)
    return candidate if len(candidate) <= max_length else text


def deduplicate_custom_emojis(text: str) -> str:
    """Remove duplicate custom Discord emoji tokens, keeping only first occurrence.
    
    Args:
        text: Text containing custom emoji tokens
        
    Returns:
        Text with duplicate custom emojis removed
    """
    used_custom: set[str] = set()
    
    def _dedupe_custom(match):
        tok = match.group(0)
        if tok in used_custom:
            return ""  # drop duplicates
        used_custom.add(tok)
        return tok
    
    return re.sub(r"<a?:[A-Za-z0-9_]+:\d+>", _dedupe_custom, text)


def deduplicate_unicode_emojis(text: str) -> str:
    """Remove duplicate Unicode emojis, keeping only first occurrence.

    Handles multi-codepoint emojis (ZWJ sequences, skin tone modifiers, etc.)
    by using emoji_list() to find complete emoji sequences.

    Args:
        text: Text containing Unicode emojis

    Returns:
        Text with duplicate Unicode emojis removed
    """
    emoji_lib = _get_emoji_lib()
    if not emoji_lib or not hasattr(emoji_lib, "emoji_list"):
        return text

    try:
        emoji_matches = emoji_lib.emoji_list(text)
    except Exception:
        return text

    if not emoji_matches:
        return text

    # Build result by processing text segments and emojis
    seen_emojis: set[str] = set()
    result_parts: list[str] = []
    last_end = 0

    for match in emoji_matches:
        # Add text before this emoji
        start = match.get("match_start", 0)
        end = match.get("match_end", start)
        emoji_str = match.get("emoji", "")

        if start > last_end:
            result_parts.append(text[last_end:start])

        # Only include emoji if not seen before
        if emoji_str and emoji_str not in seen_emojis:
            result_parts.append(emoji_str)
            seen_emojis.add(emoji_str)

        last_end = end

    # Add remaining text after last emoji
    if last_end < len(text):
        result_parts.append(text[last_end:])

    return "".join(result_parts)


def declump_custom_emojis(text: str) -> str:
    """Collapse runs of adjacent custom emojis into a single token.
    
    Transforms patterns like '<:a:1> <:b:2>' into just '<:a:1>'.
    
    Args:
        text: Text with potential emoji clusters
        
    Returns:
        Text with emoji clusters reduced to single emoji
    """
    cluster_re = re.compile(r"(<a?:[A-Za-z0-9_]+:\d+>)(?:\s*<a?:[A-Za-z0-9_]+:\d+>)+")
    
    prev = None
    result = text
    while prev != result:
        prev = result
        result = cluster_re.sub(lambda m: m.group(1), result)
    
    return result


def declump_unicode_emojis(text: str) -> str:
    """Remove consecutive Unicode emoji characters.

    Handles multi-codepoint emojis (ZWJ sequences, skin tone modifiers, etc.)
    by using emoji_list() to find complete emoji sequences.

    Args:
        text: Text with potential Unicode emoji clusters

    Returns:
        Text with consecutive Unicode emojis removed
    """
    emoji_lib = _get_emoji_lib()
    if not emoji_lib or not hasattr(emoji_lib, "emoji_list"):
        return text

    try:
        emoji_matches = emoji_lib.emoji_list(text)
    except Exception:
        return text

    if not emoji_matches:
        return text

    # Build result, skipping emojis that immediately follow another emoji
    result_parts: list[str] = []
    last_end = 0
    prev_emoji_end: int | None = None

    for match in emoji_matches:
        start = match.get("match_start", 0)
        end = match.get("match_end", start)
        emoji_str = match.get("emoji", "")

        # Add text between previous position and this emoji
        if start > last_end:
            result_parts.append(text[last_end:start])
            # Reset: there's text between emojis, so not consecutive
            prev_emoji_end = None

        # Check if this emoji immediately follows previous emoji (consecutive)
        # We consider emojis consecutive if only whitespace separates them
        is_consecutive = False
        if prev_emoji_end is not None:
            between = text[prev_emoji_end:start]
            if not between or between.isspace():
                is_consecutive = True

        if not is_consecutive:
            result_parts.append(emoji_str)

        prev_emoji_end = end
        last_end = end

    # Add remaining text after last emoji
    if last_end < len(text):
        result_parts.append(text[last_end:])

    return "".join(result_parts)


def enforce_emoji_distribution(
    text: str,
    custom_tokens: list[str],
    unicode_tokens: list[str],
    max_length: int = 1900
) -> str:
    """Apply complete emoji enforcement pipeline.

    Steps:
    1. Strip invalid/hallucinated emoji shortcodes
    2. Ensure each sentence has at least one emoji
    3. Deduplicate custom emojis
    4. Deduplicate Unicode emojis
    5. Declump adjacent custom emojis
    6. Declump adjacent Unicode emojis

    Args:
        text: Original text
        custom_tokens: Available custom Discord emoji tokens
        unicode_tokens: Available Unicode emoji characters
        max_length: Maximum allowed result length

    Returns:
        Text with emoji enforcement applied
    """
    if not text:
        return text

    # Step 1: Strip invalid/hallucinated emoji shortcodes like :invalidemoji:
    result = strip_invalid_emoji_shortcodes(text)

    # Step 2: Ensure emoji per sentence
    result = ensure_emoji_per_sentence(result, custom_tokens, unicode_tokens, max_length)

    # Step 3: Deduplicate custom emojis
    result = deduplicate_custom_emojis(result)

    # Step 4: Deduplicate Unicode emojis
    result = deduplicate_unicode_emojis(result)

    # Step 5: Declump custom emojis
    result = declump_custom_emojis(result)

    # Step 6: Declump Unicode emojis
    result = declump_unicode_emojis(result)

    return result


def fallback_add_custom_emoji(text: str, custom_tokens: list[str]) -> str:
    """Add at least one custom emoji if none present.
    
    Adds the first available custom emoji after the first sentence.
    
    Args:
        text: Text that might lack custom emojis
        custom_tokens: Available custom Discord emoji tokens
        
    Returns:
        Text with at least one custom emoji
    """
    if not custom_tokens or not text:
        return text
    
    # Check if already has custom emoji
    if "<:" in text or "<a:" in text:
        return text
    
    addtok = " " + custom_tokens[0]
    
    # Don't make text too long
    if len(text) + len(addtok) > 1900:
        return text
    
    # Try to add after first sentence
    m = re.search(r"([.!?])\s", text)
    if m:
        idx = m.end()
        return text[:idx] + addtok + text[idx:]
    
    # Otherwise append
    return text + addtok

