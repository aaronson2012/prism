"""Tests for source formatting functionality."""
from prism.main import _format_sources


def test_format_sources_empty():
    """Test that empty sources list returns empty string."""
    assert _format_sources([]) == ""


def test_format_sources_with_url_and_title():
    """Test formatting sources with both URL and title."""
    sources = [
        {"url": "https://example.com/article1", "title": "Example Article 1"},
        {"url": "https://example.com/article2", "title": "Example Article 2"},
    ]
    result = _format_sources(sources)
    
    assert result.startswith("\n\n**Sources:**\n")
    assert "- Example Article 1: https://example.com/article1" in result
    assert "- Example Article 2: https://example.com/article2" in result


def test_format_sources_with_url_only():
    """Test formatting sources with URL but no title."""
    sources = [
        {"url": "https://example.com/article1"},
    ]
    result = _format_sources(sources)
    
    assert result.startswith("\n\n**Sources:**\n")
    assert "- https://example.com/article1" in result


def test_format_sources_with_link_field():
    """Test formatting sources using 'link' field instead of 'url'."""
    sources = [
        {"link": "https://example.com/article1", "title": "Example Article"},
    ]
    result = _format_sources(sources)
    
    assert "- Example Article: https://example.com/article1" in result


def test_format_sources_with_href_field():
    """Test formatting sources using 'href' field."""
    sources = [
        {"href": "https://example.com/article1", "name": "Example Article"},
    ]
    result = _format_sources(sources)
    
    assert "- Example Article: https://example.com/article1" in result


def test_format_sources_invalid_entries():
    """Test that invalid source entries are filtered out."""
    sources = [
        {"url": "https://example.com/valid", "title": "Valid Source"},
        {"title": "No URL"},  # Should be filtered out
        "not a dict",  # Should be filtered out
        {},  # Should be filtered out
    ]
    result = _format_sources(sources)
    
    assert "Valid Source" in result
    assert "No URL" not in result
    # Should only have one source line
    assert result.count("- ") == 1


def test_format_sources_mixed_formats():
    """Test formatting sources with mixed field names."""
    sources = [
        {"url": "https://example.com/1", "title": "Source 1"},
        {"link": "https://example.com/2", "name": "Source 2"},
        {"href": "https://example.com/3"},
    ]
    result = _format_sources(sources)
    
    assert "- Source 1: https://example.com/1" in result
    assert "- Source 2: https://example.com/2" in result
    assert "- https://example.com/3" in result
    assert result.count("- ") == 3
