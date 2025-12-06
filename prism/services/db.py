from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable

import aiosqlite


log = logging.getLogger(__name__)

# Retry configuration for database lock handling
_DB_RETRY_ATTEMPTS = 3
_DB_RETRY_DELAY = 0.1  # seconds


@dataclass
class Database:
    path: str
    conn: aiosqlite.Connection

    @classmethod
    async def init(cls, path: str) -> "Database":
        # Create parent directory if needed (skip for in-memory databases)
        if path != ":memory:":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        conn = await aiosqlite.connect(path)
        conn.row_factory = aiosqlite.Row
        # Apply schema
        schema_path = os.path.join(os.path.dirname(__file__), "../storage/schema.sql")
        schema_path = os.path.normpath(schema_path)
        # Recommended PRAGMAs for better write performance with WAL
        async with conn.execute("PRAGMA foreign_keys = ON;"):
            pass
        try:
            # With WAL mode, NORMAL is a good balance of durability/perf
            await conn.execute("PRAGMA synchronous = NORMAL;")
            # Keep temp structures in memory to avoid disk I/O
            await conn.execute("PRAGMA temp_store = MEMORY;")
        except Exception:
            # Ignore if unavailable
            pass
        # Read and apply schema
        if not os.path.isfile(schema_path):
            log.error("Schema file not found: %s", schema_path)
            raise FileNotFoundError(f"Database schema not found: {schema_path}")
        with open(schema_path, "r", encoding="utf-8") as f:
            await conn.executescript(f.read())
        await conn.commit()
        
        # Initialize migrations system
        try:
            from ..storage.migrations import init_schema_version, apply_migrations
            await init_schema_version(conn)
            await apply_migrations(conn)
        except Exception as e:
            log.warning("Migration system initialization failed: %s", e)
        
        return cls(path=path, conn=conn)

    async def close(self) -> None:
        await self.conn.close()

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        """Execute a statement and commit with retry on database lock."""
        last_error: Exception | None = None
        for attempt in range(_DB_RETRY_ATTEMPTS):
            try:
                await self.conn.execute(sql, tuple(params))
                await self.conn.commit()
                return
            except aiosqlite.OperationalError as e:
                if "locked" in str(e).lower() and attempt < _DB_RETRY_ATTEMPTS - 1:
                    last_error = e
                    await asyncio.sleep(_DB_RETRY_DELAY * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        """Fetch one row with retry on database lock."""
        last_error: Exception | None = None
        for attempt in range(_DB_RETRY_ATTEMPTS):
            try:
                async with self.conn.execute(sql, tuple(params)) as cur:
                    row = await cur.fetchone()
                    return row
            except aiosqlite.OperationalError as e:
                if "locked" in str(e).lower() and attempt < _DB_RETRY_ATTEMPTS - 1:
                    last_error = e
                    await asyncio.sleep(_DB_RETRY_DELAY * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
        return None

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        """Fetch all rows with retry on database lock."""
        last_error: Exception | None = None
        for attempt in range(_DB_RETRY_ATTEMPTS):
            try:
                async with self.conn.execute(sql, tuple(params)) as cur:
                    rows = await cur.fetchall()
                    return rows
            except aiosqlite.OperationalError as e:
                if "locked" in str(e).lower() and attempt < _DB_RETRY_ATTEMPTS - 1:
                    last_error = e
                    await asyncio.sleep(_DB_RETRY_DELAY * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
        return []
