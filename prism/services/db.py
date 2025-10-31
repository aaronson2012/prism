from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import aiosqlite


@dataclass
class Database:
    path: str
    conn: aiosqlite.Connection

    @classmethod
    async def init(cls, path: str) -> "Database":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
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
        with open(schema_path, "r", encoding="utf-8") as f:
            await conn.executescript(f.read())
        await conn.commit()
        return cls(path=path, conn=conn)

    async def close(self) -> None:
        await self.conn.close()

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        # Execute a statement and commit unless we're inside an explicit transaction.
        await self.conn.execute(sql, tuple(params))
        # Check if we're in a transaction using aiosqlite's proper method
        # If in_transaction attribute doesn't exist or we're not in a transaction, commit
        try:
            # aiosqlite provides in_transaction attribute, but it may not be available in all versions
            in_tx = self.conn.in_transaction  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback: check autocommit mode (if autocommit is False, we're in a transaction)
            try:
                # In newer aiosqlite, we can check autocommit
                in_tx = not getattr(self.conn, '_autocommit', True)
            except Exception:
                # If we can't determine, assume we're not in a transaction and commit
                # SQLite handles this gracefully - commits are idempotent when not in a transaction
                in_tx = False
        
        if not in_tx:
            await self.conn.commit()

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(params)) as cur:
            row = await cur.fetchone()
            return row

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
            return rows
