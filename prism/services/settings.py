from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from .db import Database


log = logging.getLogger(__name__)


DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_persona": "default",
}


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, guild_id: int) -> Dict[str, Any]:
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
        
        # Ensure keys exist
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v if not isinstance(v, dict) else v.copy())
        return data

    async def set(self, guild_id: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data)
        await self.db.execute(
            "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)\n"
            "ON CONFLICT(guild_id) DO UPDATE SET data_json = excluded.data_json, updated_at = CURRENT_TIMESTAMP",
            (str(guild_id), payload),
        )

    async def set_persona(self, guild_id: int, scope: str, target_id: Optional[int], persona_name: str) -> None:
        # Scope simplified: always set guild-wide persona
        data = await self.get(guild_id)
        data["default_persona"] = persona_name
        await self.set(guild_id, data)

    async def resolve_persona_name(self, guild_id: int, channel_id: int, user_id: int) -> str:
        # All personas are guild-wide; ignore channel/user.
        data = await self.get(guild_id)
        return data.get("default_persona", DEFAULT_SETTINGS["default_persona"])  # type: ignore[return-value]
