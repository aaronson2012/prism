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
        budget_tokens: int = 0,
        max_messages: int = 100,
    ) -> List[Dict[str, str]]:
        """
        Return the last N messages for the channel, oldest-first.
        The budget_tokens parameter is ignored; we always return up to max_messages (default 100).
        """
        rows = await self.db.fetchall(
            "SELECT role, content FROM messages WHERE guild_id = ? AND channel_id = ? ORDER BY id DESC LIMIT ?",
            (str(guild_id), str(channel_id), max_messages),
        )
        messages = [{"role": row[0], "content": row[1]} for row in rows]
        messages.reverse()  # chronological order
        return messages

    async def clear_channel(self, guild_id: int, channel_id: int) -> None:
        await self.db.execute(
            "DELETE FROM messages WHERE guild_id = ? AND channel_id = ?",
            (str(guild_id), str(channel_id)),
        )
    
    async def prune_old_messages(self, days: int = 30) -> int:
        """Delete messages older than the specified number of days.
        
        Args:
            days: Delete messages older than this many days. Default is 30.
            
        Returns:
            Number of messages deleted
        """
        # Calculate cutoff time once to ensure consistency between COUNT and DELETE
        cutoff_row = await self.db.fetchone(
            "SELECT datetime('now', ? || ' days')",
            (f"-{days}",)
        )
        if not cutoff_row or not cutoff_row[0]:
            return 0
        
        cutoff_time = cutoff_row[0]
        
        # Count messages to be deleted using the same cutoff time
        count_row = await self.db.fetchone(
            "SELECT COUNT(*) FROM messages WHERE ts < ?",
            (cutoff_time,)
        )
        count_to_delete = int(count_row[0]) if count_row else 0
        
        if count_to_delete > 0:
            # Delete old messages using the same cutoff time
            await self.db.execute(
                "DELETE FROM messages WHERE ts < ?",
                (cutoff_time,),
            )
        
        return count_to_delete