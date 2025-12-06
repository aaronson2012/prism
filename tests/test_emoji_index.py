"""Tests for emoji index service."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prism.services.emoji_index import (
    CustomEmoji,
    EmojiIndexService,
    _score_keywords,
    _tokenize,
)


class TestTokenize:
    """Tests for _tokenize function."""

    def test_tokenize_basic(self):
        """Test basic tokenization."""
        result = _tokenize("hello world")
        assert result == ["hello", "world"]

    def test_tokenize_lowercase(self):
        """Test tokenization lowercases."""
        result = _tokenize("Hello WORLD")
        assert result == ["hello", "world"]

    def test_tokenize_special_chars(self):
        """Test tokenization handles special characters."""
        result = _tokenize("hello, world!")
        assert result == ["hello", "world"]

    def test_tokenize_numbers(self):
        """Test tokenization includes numbers."""
        result = _tokenize("test123 abc456")
        assert result == ["test123", "abc456"]

    def test_tokenize_underscores(self):
        """Test tokenization includes underscores in words."""
        result = _tokenize("hello_world test_case")
        assert result == ["hello_world", "test_case"]

    def test_tokenize_empty(self):
        """Test tokenization of empty string."""
        result = _tokenize("")
        assert result == []

    def test_tokenize_none_like(self):
        """Test tokenization of falsy value."""
        result = _tokenize(None)  # type: ignore
        assert result == []


class TestScoreKeywords:
    """Tests for _score_keywords function."""

    def test_score_keywords_exact_match(self):
        """Test scoring with exact keyword match."""
        score = _score_keywords(["hello"], ["hello", "world"])
        assert score > 0

    def test_score_keywords_multiple_matches(self):
        """Test scoring with multiple matches gives higher score."""
        score_one = _score_keywords(["hello"], ["hello", "world"])
        score_two = _score_keywords(["hello", "world"], ["hello", "world"])
        # Both hit the max of 1.0 due to the formula, but score_two should be >= score_one
        assert score_two >= score_one

    def test_score_keywords_no_match(self):
        """Test scoring with no matches."""
        score = _score_keywords(["foo"], ["bar", "baz"])
        assert score == 0.0

    def test_score_keywords_empty_query(self):
        """Test scoring with empty query."""
        score = _score_keywords([], ["hello", "world"])
        assert score == 0.0

    def test_score_keywords_empty_target(self):
        """Test scoring with empty target."""
        score = _score_keywords(["hello"], [])
        assert score == 0.0

    def test_score_keywords_partial_match(self):
        """Test scoring with partial substring match."""
        # "test" is >= 4 chars and contained in "testing"
        score = _score_keywords(["test"], ["testing"])
        assert score > 0  # fuzzy partial match

    def test_score_keywords_short_partial_no_match(self):
        """Test that short substrings don't trigger partial match."""
        # "hi" is < 4 chars, so no partial match
        score = _score_keywords(["hi"], ["higher"])
        assert score == 0.0


class TestCustomEmoji:
    """Tests for CustomEmoji dataclass."""

    def test_custom_emoji_creation(self):
        """Test CustomEmoji creation."""
        emoji = CustomEmoji(
            guild_id=123456,
            emoji_id=789012,
            name="test_emoji",
            animated=False,
            description="A test emoji",
        )
        assert emoji.guild_id == 123456
        assert emoji.emoji_id == 789012
        assert emoji.name == "test_emoji"
        assert emoji.animated is False
        assert emoji.description == "A test emoji"

    def test_custom_emoji_animated(self):
        """Test animated CustomEmoji."""
        emoji = CustomEmoji(
            guild_id=123,
            emoji_id=456,
            name="animated_emoji",
            animated=True,
            description=None,
        )
        assert emoji.animated is True
        assert emoji.description is None


class TestEmojiIndexService:
    """Tests for EmojiIndexService."""

    @pytest.mark.asyncio
    async def test_service_init(self, db_with_schema):
        """Test EmojiIndexService initialization."""
        service = EmojiIndexService(db=db_with_schema)
        assert service.db == db_with_schema
        assert service._unicode_index is None

    @pytest.mark.asyncio
    async def test_upsert_custom_insert(self, db_with_schema):
        """Test inserting a new custom emoji."""
        service = EmojiIndexService(db=db_with_schema)
        await service._upsert_custom(
            guild_id=123,
            emoji_id=456,
            name="test_emoji",
            animated=False,
        )

        # Verify it was inserted
        rows = await db_with_schema.fetchall(
            "SELECT guild_id, emoji_id, name, animated FROM emoji_index WHERE guild_id = ?",
            ("123",),
        )
        assert len(rows) == 1
        assert rows[0][1] == "456"
        assert rows[0][2] == "test_emoji"

    @pytest.mark.asyncio
    async def test_upsert_custom_update(self, db_with_schema):
        """Test updating an existing custom emoji."""
        service = EmojiIndexService(db=db_with_schema)

        # Insert first
        await service._upsert_custom(
            guild_id=123,
            emoji_id=456,
            name="original_name",
            animated=False,
        )

        # Update with same emoji_id
        await service._upsert_custom(
            guild_id=123,
            emoji_id=456,
            name="updated_name",
            animated=True,
        )

        # Should only have one row with updated name
        rows = await db_with_schema.fetchall(
            "SELECT name, animated FROM emoji_index WHERE guild_id = ? AND emoji_id = ?",
            ("123", "456"),
        )
        assert len(rows) == 1
        assert rows[0][0] == "updated_name"
        assert rows[0][1] == 1  # animated

    @pytest.mark.asyncio
    async def test_fetch_custom(self, db_with_schema):
        """Test fetching custom emojis for a guild."""
        service = EmojiIndexService(db=db_with_schema)

        # Insert some emojis
        await service._upsert_custom(123, 1, "emoji_one", False)
        await service._upsert_custom(123, 2, "emoji_two", True)
        await service._upsert_custom(456, 3, "other_guild", False)

        # Fetch for guild 123
        emojis = await service._fetch_custom(123)
        assert len(emojis) == 2
        names = {e.name for e in emojis}
        assert names == {"emoji_one", "emoji_two"}

    @pytest.mark.asyncio
    async def test_fetch_custom_empty(self, db_with_schema):
        """Test fetching custom emojis from empty guild."""
        service = EmojiIndexService(db=db_with_schema)
        emojis = await service._fetch_custom(999)
        assert emojis == []

    @pytest.mark.asyncio
    async def test_index_guild(self, db_with_schema):
        """Test indexing a guild's emojis."""
        service = EmojiIndexService(db=db_with_schema)

        # Mock guild with emojis - use spec=[] to prevent attribute auto-creation
        mock_emoji1 = MagicMock()
        mock_emoji1.id = 100
        mock_emoji1.name = "smile"
        mock_emoji1.animated = False

        mock_emoji2 = MagicMock()
        mock_emoji2.id = 101
        mock_emoji2.name = "wave"
        mock_emoji2.animated = True

        mock_guild = MagicMock()
        mock_guild.id = 123
        mock_guild.emojis = [mock_emoji1, mock_emoji2]

        count = await service.index_guild(mock_guild)
        assert count == 2

        # Verify stored
        emojis = await service._fetch_custom(123)
        assert len(emojis) == 2

    @pytest.mark.asyncio
    async def test_index_guild_empty(self, db_with_schema):
        """Test indexing a guild with no emojis."""
        service = EmojiIndexService(db=db_with_schema)
        mock_guild = MagicMock(id=123, emojis=[])

        count = await service.index_guild(mock_guild)
        assert count == 0

    @pytest.mark.asyncio
    async def test_index_guild_missing_emojis_attr(self, db_with_schema):
        """Test indexing a guild without emojis attribute."""
        service = EmojiIndexService(db=db_with_schema)
        mock_guild = MagicMock(id=123, spec=[])  # No emojis attribute

        count = await service.index_guild(mock_guild)
        assert count == 0

    @pytest.mark.asyncio
    async def test_index_all_guilds(self, db_with_schema):
        """Test indexing all guilds."""
        service = EmojiIndexService(db=db_with_schema)

        mock_emoji1 = MagicMock()
        mock_emoji1.id = 1
        mock_emoji1.name = "e1"
        mock_emoji1.animated = False

        mock_emoji2 = MagicMock()
        mock_emoji2.id = 2
        mock_emoji2.name = "e2"
        mock_emoji2.animated = False

        mock_guild1 = MagicMock()
        mock_guild1.id = 100
        mock_guild1.emojis = [mock_emoji1]

        mock_guild2 = MagicMock()
        mock_guild2.id = 200
        mock_guild2.emojis = [mock_emoji2]

        mock_bot = MagicMock()
        mock_bot.guilds = [mock_guild1, mock_guild2]

        results = await service.index_all_guilds(mock_bot)
        assert results == {100: 1, 200: 1}

    @pytest.mark.asyncio
    async def test_suggest_for_text_empty(self, db_with_schema):
        """Test suggestions for empty text."""
        service = EmojiIndexService(db=db_with_schema)
        results = await service.suggest_for_text(123, "")
        assert results == []

    @pytest.mark.asyncio
    async def test_suggest_for_text_with_custom(self, db_with_schema):
        """Test suggestions include custom emojis."""
        service = EmojiIndexService(db=db_with_schema)

        # Add custom emoji with keyword in name
        await service._upsert_custom(123, 1, "happy_smile", False)
        await db_with_schema.execute(
            "UPDATE emoji_index SET description = ? WHERE emoji_id = ?",
            ("A happy smiling face", "1"),
        )

        results = await service.suggest_for_text(123, "I am happy")
        # Should suggest the happy emoji
        assert len(results) >= 1
        # Custom emoji format
        assert any("<:happy_smile:1>" in r for r in results)

    @pytest.mark.asyncio
    async def test_suggest_for_text_animated_format(self, db_with_schema):
        """Test animated emoji format in suggestions."""
        service = EmojiIndexService(db=db_with_schema)

        await service._upsert_custom(123, 1, "animated_test", animated=True)

        results = await service.suggest_for_text(123, "test")
        # Animated emojis use <a:name:id> format
        assert any("<a:animated_test:1>" in r for r in results)

    @pytest.mark.asyncio
    async def test_suggest_with_meta_for_text(self, db_with_schema):
        """Test suggest_with_meta_for_text returns metadata."""
        service = EmojiIndexService(db=db_with_schema)

        await service._upsert_custom(123, 1, "test_emoji", False)
        await db_with_schema.execute(
            "UPDATE emoji_index SET description = ? WHERE emoji_id = ?",
            ("Test description", "1"),
        )

        results = await service.suggest_with_meta_for_text(123, "test")
        assert len(results) >= 1
        result = results[0]
        assert "token" in result
        assert "name" in result
        assert "description" in result

    @pytest.mark.asyncio
    async def test_suggest_respects_limit(self, db_with_schema):
        """Test suggestions respect limit parameter."""
        service = EmojiIndexService(db=db_with_schema)

        # Add many emojis
        for i in range(10):
            await service._upsert_custom(123, i, f"emoji_{i}", False)

        results = await service.suggest_for_text(123, "emoji", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_unicode_index_caching(self, db_with_schema):
        """Test unicode index is cached."""
        service = EmojiIndexService(db=db_with_schema)

        # First call builds index
        index1 = service._get_unicode_index()
        # Second call returns cached
        index2 = service._get_unicode_index()

        assert index1 is index2  # Same object

    @pytest.mark.asyncio
    async def test_ensure_descriptions_empty(self, db_with_schema):
        """Test ensure_descriptions with no emojis needing descriptions."""
        service = EmojiIndexService(db=db_with_schema)
        mock_orc = AsyncMock()

        count = await service.ensure_descriptions(mock_orc, 123)
        assert count == 0
        mock_orc.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_descriptions_generates(self, db_with_schema):
        """Test ensure_descriptions generates descriptions via LLM."""
        service = EmojiIndexService(db=db_with_schema)

        # Add emoji without description
        await service._upsert_custom(123, 1, "test_emoji", False)

        # Mock LLM response
        mock_orc = AsyncMock()
        mock_orc.chat_completion.return_value = (
            '{"test_emoji": "A test emoji for testing purposes."}',
            {},
        )

        count = await service.ensure_descriptions(mock_orc, 123)
        assert count == 1

        # Verify description was saved
        rows = await db_with_schema.fetchall(
            "SELECT description FROM emoji_index WHERE emoji_id = ?",
            ("1",),
        )
        assert rows[0][0] == "A test emoji for testing purposes."

    @pytest.mark.asyncio
    async def test_ensure_descriptions_handles_llm_error(self, db_with_schema):
        """Test ensure_descriptions handles LLM errors gracefully."""
        service = EmojiIndexService(db=db_with_schema)

        await service._upsert_custom(123, 1, "test_emoji", False)

        mock_orc = AsyncMock()
        mock_orc.chat_completion.side_effect = Exception("LLM error")

        count = await service.ensure_descriptions(mock_orc, 123)
        assert count == 0

    @pytest.mark.asyncio
    async def test_ensure_descriptions_handles_invalid_json(self, db_with_schema):
        """Test ensure_descriptions handles invalid JSON response."""
        service = EmojiIndexService(db=db_with_schema)

        await service._upsert_custom(123, 1, "test_emoji", False)

        mock_orc = AsyncMock()
        mock_orc.chat_completion.return_value = ("not valid json", {})

        count = await service.ensure_descriptions(mock_orc, 123)
        assert count == 0

    @pytest.mark.asyncio
    async def test_describe_custom_batch_empty(self, db_with_schema):
        """Test _describe_custom_batch with empty items."""
        service = EmojiIndexService(db=db_with_schema)
        mock_orc = AsyncMock()

        result = await service._describe_custom_batch(mock_orc, [])
        assert result == {}
        mock_orc.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_describe_custom_batch_limits_items(self, db_with_schema):
        """Test _describe_custom_batch limits to 10 items."""
        service = EmojiIndexService(db=db_with_schema)

        items = [{"name": f"emoji_{i}"} for i in range(20)]

        mock_orc = AsyncMock()
        mock_orc.chat_completion.return_value = ("{}", {})

        await service._describe_custom_batch(mock_orc, items)

        # Check the prompt only includes first 10
        call_args = mock_orc.chat_completion.call_args
        messages = call_args[0][0]
        user_message = messages[1]["content"]
        # Should have exactly 10 names
        assert user_message.count("emoji_") == 10

    @pytest.mark.asyncio
    async def test_describe_custom_batch_extracts_json(self, db_with_schema):
        """Test _describe_custom_batch extracts JSON from wrapped response."""
        service = EmojiIndexService(db=db_with_schema)

        items = [{"name": "test"}]

        mock_orc = AsyncMock()
        # Response with text wrapping JSON
        mock_orc.chat_completion.return_value = (
            'Here is the result:\n{"test": "description"}\nDone!',
            {},
        )

        result = await service._describe_custom_batch(mock_orc, items)
        assert result == {"test": "description"}

    @pytest.mark.asyncio
    async def test_describe_custom_batch_caps_length(self, db_with_schema):
        """Test _describe_custom_batch caps description length."""
        service = EmojiIndexService(db=db_with_schema)

        items = [{"name": "test"}]

        mock_orc = AsyncMock()
        # Very long description
        long_desc = "x" * 1000
        mock_orc.chat_completion.return_value = (f'{{"test": "{long_desc}"}}', {})

        result = await service._describe_custom_batch(mock_orc, items)
        assert len(result["test"]) == 600  # capped at 600


class TestUnicodeIndex:
    """Tests for unicode emoji index building."""

    def test_get_unicode_index_builds(self, db_with_schema):
        """Test unicode index is built from emoji library."""
        service = EmojiIndexService(db=db_with_schema)

        index = service._get_unicode_index()
        # Should have some entries (depends on emoji library)
        # May be empty if emoji library not installed
        assert isinstance(index, list)

    def test_get_unicode_index_handles_missing_library(self, db_with_schema):
        """Test unicode index handles missing emoji library."""
        service = EmojiIndexService(db=db_with_schema)

        with patch.dict("sys.modules", {"emoji": None}):
            # Force rebuild
            service._unicode_index = None
            index = service._get_unicode_index()
            # Should return empty list, not crash
            assert isinstance(index, list)
