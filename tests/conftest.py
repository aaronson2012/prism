"""Pytest configuration and shared fixtures."""
import os
import tempfile
from typing import AsyncGenerator

import pytest


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
            # Ignore errors during cleanup (e.g., file already deleted)
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

