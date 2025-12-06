from __future__ import annotations

import copy
import json
import logging
from typing import Any

from .db import Database


log = logging.getLogger(__name__)


DEFAULT_SETTINGS: dict[str, Any] = {
    "default_persona": "default",
}


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, guild_id: int) -> dict[str, Any]:
        # Use INSERT OR IGNORE to atomically create default settings if they don't exist
        # This prevents race conditions when multiple requests check simultaneously
        await self.db.execute(
            "INSERT OR IGNORE INTO settings (guild_id, data_json) VALUES (?, ?)",
            (str(guild_id), json.dumps(DEFAULT_SETTINGS)),
        )
        
        # Now fetch (guaranteed to exist)
        row = await self.db.fetchone("SELECT data_json FROM settings WHERE guild_id = ?", (str(guild_id),))
        if not row:
            # Should never happen after INSERT OR IGNORE, but handle defensively
            log.warning("Settings row missing after INSERT OR IGNORE for guild %s", guild_id)
            return DEFAULT_SETTINGS.copy()
        
        try:
            data = json.loads(row[0])
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.warning("Failed to parse settings JSON for guild %s: %s", guild_id, e)
            data = DEFAULT_SETTINGS.copy()
        
        # Ensure keys exist with proper deep copy for mutable defaults
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
        return data

    async def set(self, guild_id: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        await self.db.execute(
            "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)\n"
            "ON CONFLICT(guild_id) DO UPDATE SET data_json = excluded.data_json, updated_at = CURRENT_TIMESTAMP",
            (str(guild_id), payload),
        )

    async def set_persona(self, guild_id: int, scope: str, target_id: int | None, persona_name: str) -> None:
        # Scope simplified: always set guild-wide persona
        data = await self.get(guild_id)
        data["default_persona"] = persona_name
        await self.set(guild_id, data)

    async def resolve_persona_name(self, guild_id: int, channel_id: int, user_id: int) -> str:
        # All personas are guild-wide; ignore channel/user.
        data = await self.get(guild_id)
        return data.get("default_persona", DEFAULT_SETTINGS["default_persona"])  # type: ignore[return-value]

    async def reset_persona_to_default(self, persona_name: str) -> int:
        """Reset all guilds using the specified persona back to 'default'.

        Returns the number of guilds that were reset.
        """
        # Find all guilds using this persona
        rows = await self.db.fetchall("SELECT guild_id, data_json FROM settings")
        reset_count = 0
        for row in rows:
            try:
                data = json.loads(row[1])
                if data.get("default_persona", "").lower() == persona_name.lower():
                    data["default_persona"] = "default"
                    await self.set(int(row[0]), data)
                    reset_count += 1
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return reset_count
