"""Simple database migration system."""
from __future__ import annotations

import logging
from typing import List, Callable, Awaitable

import aiosqlite


log = logging.getLogger(__name__)


# Migration functions take a connection and perform schema changes
Migration = Callable[[aiosqlite.Connection], Awaitable[None]]


# Define migrations in order (v1, v2, v3, ...)
# v1 is the initial schema from schema.sql
MIGRATIONS: List[Migration] = [
    # v1: Initial schema (applied from schema.sql)
    # No migration function needed - handled by init
]


async def get_schema_version(conn: aiosqlite.Connection) -> int:
    """Get the current schema version from the database.
    
    Args:
        conn: Database connection
        
    Returns:
        Current schema version (0 if no version table exists)
    """
    try:
        async with conn.execute("SELECT version FROM schema_version LIMIT 1") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0
    except aiosqlite.OperationalError:
        # Table doesn't exist yet
        return 0


async def set_schema_version(conn: aiosqlite.Connection, version: int) -> None:
    """Set the schema version in the database.
    
    Args:
        conn: Database connection
        version: Version number to set
    """
    # Create version table if it doesn't exist
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Update or insert version
    await conn.execute("DELETE FROM schema_version")
    await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    await conn.commit()


async def apply_migrations(conn: aiosqlite.Connection, target_version: int | None = None) -> None:
    """Apply pending migrations to bring database up to date.
    
    Args:
        conn: Database connection
        target_version: Target version to migrate to (None = latest)
    """
    current = await get_schema_version(conn)
    
    if target_version is None:
        target_version = len(MIGRATIONS)
    
    if current >= target_version:
        log.debug("Database schema is up to date (v%d)", current)
        return
    
    log.info("Migrating database schema from v%d to v%d", current, target_version)
    
    for version in range(current + 1, target_version + 1):
        if version > len(MIGRATIONS):
            log.warning("No migration defined for version %d", version)
            break
        
        migration = MIGRATIONS[version - 1]
        log.info("Applying migration v%d...", version)
        
        try:
            await migration(conn)
            await set_schema_version(conn, version)
            log.info("Migration v%d applied successfully", version)
        except Exception as e:
            log.error("Migration v%d failed: %s", version, e, exc_info=True)
            raise


async def init_schema_version(conn: aiosqlite.Connection) -> None:
    """Initialize schema version tracking for existing database.
    
    Call this after applying initial schema from schema.sql.
    
    Args:
        conn: Database connection
    """
    current = await get_schema_version(conn)
    if current == 0:
        # Fresh database - set to v1 (initial schema)
        await set_schema_version(conn, 1)
        log.info("Initialized schema version to v1")

