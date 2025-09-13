from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from .db import Database


def estimate_tokens(text: str) -> int:
    """Very rough heuristic: ~4 chars per token."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


@dataclass
class Message:
    guild_id: Optional[int]
    channel_id: Optional[int]
    user_id: Optional[int]
    role: str  # system|user|assistant
    content: str
    token_estimate: Optional[int] = None


class MemoryService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(self, msg: Message) -> None:
        tokens = msg.token_estimate if msg.token_estimate is not None else estimate_tokens(msg.content)
        await self.db.execute(
            "INSERT INTO messages (guild_id, channel_id, user_id, role, content, token_estimate) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(msg.guild_id) if msg.guild_id is not None else None,
                str(msg.channel_id) if msg.channel_id is not None else None,
                str(msg.user_id) if msg.user_id is not None else None,
                msg.role,
                msg.content,
                int(tokens),
            ),
        )

    async def get_recent_window(
        self,
        guild_id: int,
        channel_id: int,
        budget_tokens: int = 1200,
        max_messages: int = 40,
    ) -> List[Dict[str, str]]:
        """
        Returns a list of dicts with keys role/content for the recent context window,
        trimmed by a simple token budget. Oldest messages are dropped first.
        """
        rows = await self.db.fetchall(
            "SELECT role, content, IFNULL(token_estimate, 0) as t FROM messages "
            "WHERE guild_id = ? AND channel_id = ? ORDER BY id DESC LIMIT ?",
            (str(guild_id), str(channel_id), max_messages),
        )
        messages = [
            {"role": row[0], "content": row[1], "t": int(row[2]) if row[2] is not None else estimate_tokens(row[1])}
            for row in rows
        ]
        messages.reverse()  # chronological order

        total = 0
        window: List[Dict[str, str]] = []
        # Accumulate from newest backwards up to budget
        for m in reversed(messages):
            t = int(m.get("t") or estimate_tokens(m["content"]))
            if total + t > budget_tokens:
                continue
            total += t
            window.append({"role": m["role"], "content": m["content"]})
        window.reverse()
        return window

    async def clear_channel(self, guild_id: int, channel_id: int) -> None:
        await self.db.execute(
            "DELETE FROM messages WHERE guild_id = ? AND channel_id = ?",
            (str(guild_id), str(channel_id)),
        )
