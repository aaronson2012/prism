"""Tests for reaction engine service."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from prism.services.reaction_engine import ReactionEngine, ReactionEngineConfig, _FALLBACK_UNICODE_EMOJIS
from prism.services.db import Database
from prism.services.emoji_index import EmojiIndexService
from prism.services.rate_limit import RateLimiter


@pytest.fixture
async def db():
    """Create an in-memory database."""
    database = await Database.init(":memory:")
    yield database
    await database.close()


@pytest.fixture
async def emoji_index(db):
    """Create an emoji index service."""
    return EmojiIndexService(db)


@pytest.fixture
def rate_limiter():
    """Create a rate limiter."""
    return RateLimiter()


@pytest.fixture
def reaction_engine(db, emoji_index, rate_limiter):
    """Create a reaction engine."""
    return ReactionEngine(db, emoji_index, rate_limiter, ReactionEngineConfig())


@pytest.mark.asyncio
async def test_fallback_emojis_exist():
    """Test that fallback emojis are defined."""
    assert len(_FALLBACK_UNICODE_EMOJIS) > 0
    # Check structure
    for emoji_char, name, desc in _FALLBACK_UNICODE_EMOJIS:
        assert isinstance(emoji_char, str)
        assert isinstance(name, str)
        assert isinstance(desc, str)
        assert len(emoji_char) > 0
        assert len(name) > 0


@pytest.mark.asyncio
async def test_maybe_react_with_fallback_emojis(reaction_engine):
    """Test that reaction engine uses fallback emojis when no custom emojis available."""
    # Mock OpenRouter client
    orc = AsyncMock()
    # Return a decision that chooses the first fallback emoji
    orc.chat_completion = AsyncMock(return_value=(
        '{"emoji": "👍", "score": 0.8, "reason": "Positive message"}',
        {}
    ))
    
    # Mock message object
    message = MagicMock()
    message.author.bot = False
    message.webhook_id = None
    message.guild = MagicMock()
    message.guild.id = 12345
    message.guild.emojis = []  # No custom emojis
    message.channel = MagicMock()
    message.channel.id = 67890
    message.author.id = 11111
    message.content = "i like dogs"
    message.id = 99999
    message.add_reaction = AsyncMock()
    
    # Call maybe_react
    result = await reaction_engine.maybe_react(orc, message)
    
    # Should successfully add a reaction
    assert result == 1
    message.add_reaction.assert_called_once_with("👍")


@pytest.mark.asyncio
async def test_maybe_react_rate_limited():
    """Test that reactions are rate limited."""
    # Create mocked services
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])  # No usage history
    
    emoji_index = AsyncMock()
    emoji_index.suggest_with_meta_for_text = AsyncMock(return_value=[])  # Force fallback emojis
    
    # Create reaction engine with custom rate limiter for testing
    from prism.services.rate_limit import RateLimitConfig
    config = RateLimitConfig(channel_cooldown_sec=10)  # Short cooldown for testing
    rate_limiter = RateLimiter(config)
    reaction_engine = ReactionEngine(db, emoji_index, rate_limiter, ReactionEngineConfig())
    
    # Mock OpenRouter client - return first fallback emoji
    orc = AsyncMock()
    orc.chat_completion = AsyncMock(return_value=(
        '{"emoji": "👍", "score": 0.8, "reason": "Positive"}',
        {}
    ))
    
    # Mock message
    message = MagicMock()
    message.author.bot = False
    message.webhook_id = None
    message.guild = MagicMock()
    message.guild.id = 12345
    message.guild.emojis = []
    message.channel = MagicMock()
    message.channel.id = 67890
    message.author.id = 11111
    message.content = "test message that is long enough"
    message.id = 99999
    message.add_reaction = AsyncMock()
    
    # First call should work
    result1 = await reaction_engine.maybe_react(orc, message)
    assert result1 == 1
    
    # Second call to same channel should be rate limited
    message.id = 99998  # Different message
    message.content = "another test message long enough"
    message.add_reaction = AsyncMock()
    result2 = await reaction_engine.maybe_react(orc, message)
    assert result2 == 0


@pytest.mark.asyncio
async def test_maybe_react_ignores_bots(reaction_engine):
    """Test that bot messages are ignored."""
    orc = AsyncMock()
    
    message = MagicMock()
    message.author.bot = True
    message.content = "bot message"
    
    result = await reaction_engine.maybe_react(orc, message)
    assert result == 0


@pytest.mark.asyncio
async def test_maybe_react_ignores_short_messages(reaction_engine):
    """Test that very short messages are ignored."""
    orc = AsyncMock()
    
    message = MagicMock()
    message.author.bot = False
    message.webhook_id = None
    message.guild = MagicMock()
    message.content = "hi"
    
    result = await reaction_engine.maybe_react(orc, message)
    assert result == 0


@pytest.mark.asyncio
async def test_maybe_react_low_score_rejected(reaction_engine):
    """Test that low confidence scores are rejected."""
    orc = AsyncMock()
    # Return low score (below 0.6 threshold)
    orc.chat_completion = AsyncMock(return_value=(
        '{"emoji": "👍", "score": 0.3, "reason": "Not very relevant"}',
        {}
    ))
    
    message = MagicMock()
    message.author.bot = False
    message.webhook_id = None
    message.guild = MagicMock()
    message.guild.id = 12345
    message.guild.emojis = []
    message.channel = MagicMock()
    message.channel.id = 67890
    message.author.id = 11111
    message.content = "neutral statement"
    message.id = 99999
    
    result = await reaction_engine.maybe_react(orc, message)
    assert result == 0


@pytest.mark.asyncio
async def test_maybe_react_invalid_emoji_rejected(reaction_engine):
    """Test that emojis not in candidates are rejected."""
    orc = AsyncMock()
    # Return emoji that's not in the candidates list
    orc.chat_completion = AsyncMock(return_value=(
        '{"emoji": "🦄", "score": 0.9, "reason": "Made up"}',
        {}
    ))
    
    message = MagicMock()
    message.author.bot = False
    message.webhook_id = None
    message.guild = MagicMock()
    message.guild.id = 12345
    message.guild.emojis = []
    message.channel = MagicMock()
    message.channel.id = 67890
    message.author.id = 11111
    message.content = "test message"
    message.id = 99999
    
    result = await reaction_engine.maybe_react(orc, message)
    assert result == 0
