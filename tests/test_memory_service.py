"""Tests for memory service."""
import pytest
from prism.services.memory import MemoryService, Message, estimate_tokens


def test_estimate_tokens():
    """Test token estimation heuristic."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("test") == 1
    assert estimate_tokens("this is a test") >= 3
    assert estimate_tokens("a" * 100) == 25  # 100/4 = 25


@pytest.mark.asyncio
async def test_memory_add_message(db_with_schema):
    """Test adding messages to memory."""
    service = MemoryService(db_with_schema)
    
    msg = Message(
        guild_id=123,
        channel_id=456,
        user_id=789,
        role="user",
        content="Hello, world!"
    )
    
    await service.add(msg)
    
    # Verify it was stored
    rows = await db_with_schema.fetchall(
        "SELECT role, content, guild_id, channel_id, user_id FROM messages"
    )
    
    assert len(rows) == 1
    assert rows[0][0] == "user"
    assert rows[0][1] == "Hello, world!"
    assert rows[0][2] == "123"
    assert rows[0][3] == "456"
    assert rows[0][4] == "789"


@pytest.mark.asyncio
async def test_memory_get_recent_window(db_with_schema):
    """Test retrieving recent message window."""
    service = MemoryService(db_with_schema)
    
    # Add multiple messages
    for i in range(5):
        await service.add(Message(
            guild_id=100,
            channel_id=200,
            user_id=300,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}"
        ))
    
    # Get recent window
    messages = await service.get_recent_window(100, 200, max_messages=3)
    
    # Should return last 3 messages in chronological order
    assert len(messages) == 3
    assert messages[0]["content"] == "Message 2"
    assert messages[1]["content"] == "Message 3"
    assert messages[2]["content"] == "Message 4"


@pytest.mark.asyncio
async def test_memory_get_recent_window_empty(db_with_schema):
    """Test retrieving window from empty channel."""
    service = MemoryService(db_with_schema)
    
    messages = await service.get_recent_window(999, 888)
    
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_memory_clear_channel(db_with_schema):
    """Test clearing channel memory."""
    service = MemoryService(db_with_schema)
    
    # Add messages to two different channels
    await service.add(Message(100, 200, 300, "user", "Channel 200"))
    await service.add(Message(100, 201, 300, "user", "Channel 201"))
    
    # Clear one channel
    await service.clear_channel(100, 200)
    
    # Verify only channel 200 was cleared
    ch200 = await service.get_recent_window(100, 200)
    ch201 = await service.get_recent_window(100, 201)
    
    assert len(ch200) == 0
    assert len(ch201) == 1


@pytest.mark.asyncio
async def test_memory_respects_max_messages(db_with_schema):
    """Test that max_messages parameter is respected."""
    service = MemoryService(db_with_schema)
    
    # Add 150 messages
    for i in range(150):
        await service.add(Message(1, 2, 3, "user", f"Msg {i}"))
    
    # Request max 100
    messages = await service.get_recent_window(1, 2, max_messages=100)
    
    assert len(messages) == 100
    # Should be the most recent 100
    assert messages[0]["content"] == "Msg 50"
    assert messages[-1]["content"] == "Msg 149"


@pytest.mark.asyncio
async def test_memory_prune_old_messages(db_with_schema):
    """Test pruning of old messages."""
    service = MemoryService(db_with_schema)
    
    # Add some messages
    await service.add(Message(1, 2, 3, "user", "Recent message"))
    
    # Manually insert an old message
    await db_with_schema.execute(
        "INSERT INTO messages (guild_id, channel_id, user_id, role, content, ts) "
        "VALUES (?, ?, ?, ?, ?, datetime('now', '-60 days'))",
        ("1", "2", "3", "user", "Old message")
    )
    
    # Prune messages older than 30 days
    deleted = await service.prune_old_messages(days=30)
    
    # Should have deleted 1 message
    assert deleted == 1
    
    # Recent message should still exist
    messages = await service.get_recent_window(1, 2)
    assert len(messages) == 1
    assert messages[0]["content"] == "Recent message"


@pytest.mark.asyncio
async def test_memory_prune_no_old_messages(db_with_schema):
    """Test pruning when no old messages exist."""
    service = MemoryService(db_with_schema)
    
    # Add only recent messages
    await service.add(Message(1, 2, 3, "user", "Message 1"))
    await service.add(Message(1, 2, 3, "user", "Message 2"))
    
    # Prune - should delete nothing
    deleted = await service.prune_old_messages(days=30)
    
    assert deleted == 0
    
    # All messages should still exist
    messages = await service.get_recent_window(1, 2)
    assert len(messages) == 2

