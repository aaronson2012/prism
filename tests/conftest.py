"""Pytest configuration and shared fixtures."""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import aiosqlite


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default event loop policy for all tests."""
    return asyncio.get_event_loop_policy()


@pytest.fixture(scope="function")
def event_loop(event_loop_policy):
    """Create a new event loop for each test."""
    loop = event_loop_policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_db() -> AsyncGenerator[str, None]:
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        yield db_path
    finally:
        # Cleanup
        try:
            if os.path.exists(db_path):
                os.unlink(db_path)
        except Exception:
            pass


@pytest.fixture
async def db_with_schema(temp_db: str):
    """Create a database with the schema applied."""
    from prism.services.db import Database
    
    db = await Database.init(temp_db)
    try:
        yield db
    finally:
        await db.close()

