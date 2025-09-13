from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .db import Database


DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_persona": "default",
    # Overrides retained in stored JSON for backward compatibility; ignored.
    "channel_overrides": {},
    "user_overrides": {},
}


class SettingsService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, guild_id: int) -> Dict[str, Any]:
        row = await self.db.fetchone("SELECT data_json FROM settings WHERE guild_id = ?", (str(guild_id),))
        if not row:
            await self.set(guild_id, DEFAULT_SETTINGS.copy())
            return DEFAULT_SETTINGS.copy()
        try:
            data = json.loads(row[0])
        except Exception:
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
