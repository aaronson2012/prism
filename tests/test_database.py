"""Tests for database service."""
import pytest
from prism.services.db import Database


@pytest.mark.asyncio
async def test_database_init(temp_db):
    """Test database initialization."""
    db = await Database.init(temp_db)
    assert db.path == temp_db
    assert db.conn is not None
    await db.close()


@pytest.mark.asyncio
async def test_database_execute_and_fetch(db_with_schema):
    """Test basic execute and fetch operations."""
    # Insert a test record
    await db_with_schema.execute(
        "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)",
        ("12345", '{"test": true}')
    )
    
    # Fetch it back
    row = await db_with_schema.fetchone(
        "SELECT guild_id, data_json FROM settings WHERE guild_id = ?",
        ("12345",)
    )
    
    assert row is not None
    assert row[0] == "12345"
    assert '{"test": true}' in row[1]


@pytest.mark.asyncio
async def test_database_fetchall(db_with_schema):
    """Test fetchall operation."""
    # Insert multiple records
    await db_with_schema.execute(
        "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)",
        ("111", '{"a": 1}')
    )
    await db_with_schema.execute(
        "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)",
        ("222", '{"b": 2}')
    )
    
    # Fetch all
    rows = await db_with_schema.fetchall("SELECT guild_id FROM settings ORDER BY guild_id")
    
    assert len(rows) == 2
    assert rows[0][0] == "111"
    assert rows[1][0] == "222"


@pytest.mark.asyncio
async def test_database_schema_tables_exist(db_with_schema):
    """Test that schema creates all expected tables."""
    tables = await db_with_schema.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    
    table_names = [row[0] for row in tables]
    
    assert "settings" in table_names
    assert "messages" in table_names
    assert "emoji_index" in table_names

