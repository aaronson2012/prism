"""Emoji enforcement logic for Discord messages.

This module handles automatic emoji addition, deduplication, and distribution
in bot responses to ensure engaging, non-repetitive emoji usage.
"""
from __future__ import annotations

import re
from typing import List, Optional

# Cache emoji library availability at module level for performance
_EMOJI_LIB: Optional[object] = None
_EMOJI_LIB_CHECKED = False

def _get_emoji_lib() -> Optional[object]:
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


def has_emoji(text: str) -> bool:
    """Check if text contains any emoji (Unicode or custom Discord emoji)."""
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
    
    return False


def ensure_emoji_per_sentence(
    text: str,
    custom_tokens: List[str],
    unicode_tokens: List[str],
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
                    # Append before trailing whitespace
                    s = s.rstrip() + " " + tok + (" " if s.endswith(" ") else "")
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
    
    Args:
        text: Text containing Unicode emojis
        
    Returns:
        Text with duplicate Unicode emojis removed
    """
    emoji_lib = _get_emoji_lib()
    if not emoji_lib or not hasattr(emoji_lib, "is_emoji"):
        return text
    
    seen_uni: set[str] = set()
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        try:
            if emoji_lib.is_emoji(ch):
                if ch in seen_uni:
                    del chars[i]
                    continue
                seen_uni.add(ch)
        except Exception:
            # Ignore exceptions from emoji library; skip problematic character.
            pass
        i += 1
    return "".join(chars)


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
    
    Args:
        text: Text with potential Unicode emoji clusters
        
    Returns:
        Text with consecutive Unicode emojis removed
    """
    emoji_lib = _get_emoji_lib()
    if not emoji_lib or not hasattr(emoji_lib, "is_emoji"):
        return text
    
    out_chars = []
    prev_was_emoji = False
    for ch in text:
        try:
            is_e = emoji_lib.is_emoji(ch)
        except Exception:
            is_e = False
        
        if is_e and prev_was_emoji:
            continue
        
        out_chars.append(ch)
        prev_was_emoji = is_e
    
    return "".join(out_chars)


def enforce_emoji_distribution(
    text: str,
    custom_tokens: List[str],
    unicode_tokens: List[str],
    max_length: int = 1900
) -> str:
    """Apply complete emoji enforcement pipeline.
    
    Steps:
    1. Ensure each sentence has at least one emoji
    2. Deduplicate custom emojis
    3. Deduplicate Unicode emojis
    4. Declump adjacent custom emojis
    5. Declump adjacent Unicode emojis
    
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
    
    # Step 1: Ensure emoji per sentence
    result = ensure_emoji_per_sentence(text, custom_tokens, unicode_tokens, max_length)
    
    # Step 2: Deduplicate custom emojis
    result = deduplicate_custom_emojis(result)
    
    # Step 3: Deduplicate Unicode emojis
    result = deduplicate_unicode_emojis(result)
    
    # Step 4: Declump custom emojis
    result = declump_custom_emojis(result)
    
    # Step 5: Declump Unicode emojis
    result = declump_unicode_emojis(result)
    
    return result


def fallback_add_custom_emoji(text: str, custom_tokens: List[str]) -> str:
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

