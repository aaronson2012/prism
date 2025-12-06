from __future__ import annotations

import copy
import json
import logging
from typing import Any

from .db import Database


log = logging.getLogger(__name__)


DEFAULT_USER_PREFERENCES: dict[str, Any] = {
    "response_length": "balanced",
    "emoji_density": "normal",
    "preferred_persona": None,
}

# Reuse from settings.py for consistency
VALID_RESPONSE_LENGTHS = ("concise", "balanced", "detailed")
VALID_EMOJI_DENSITIES = ("none", "minimal", "normal", "lots")


class UserPreferencesService:
    """Service for managing user-level preferences.

    Preferences persist across sessions and guilds, allowing individual users
    to personalize how the AI responds to them.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, user_id: int) -> dict[str, Any]:
        """Get user preferences, creating defaults if not exists.

        Uses INSERT OR IGNORE to atomically create default preferences if they
        don't exist. This prevents race conditions when multiple requests check
        simultaneously.

        Args:
            user_id: Discord user snowflake ID

        Returns:
            User preferences dictionary with all keys populated
        """
        # Use INSERT OR IGNORE to atomically create default preferences if they don't exist
        # This prevents race conditions when multiple requests check simultaneously
        await self.db.execute(
            "INSERT OR IGNORE INTO user_preferences (user_id, data_json) VALUES (?, ?)",
            (str(user_id), json.dumps(DEFAULT_USER_PREFERENCES)),
        )

        # Now fetch (guaranteed to exist)
        row = await self.db.fetchone(
            "SELECT data_json FROM user_preferences WHERE user_id = ?", (str(user_id),)
        )
        if not row:
            # Should never happen after INSERT OR IGNORE, but handle defensively
            log.warning(
                "User preferences row missing after INSERT OR IGNORE for user %s",
                user_id,
            )
            return DEFAULT_USER_PREFERENCES.copy()

        try:
            data = json.loads(row[0])
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.warning("Failed to parse user preferences JSON for user %s: %s", user_id, e)
            data = DEFAULT_USER_PREFERENCES.copy()

        # Ensure keys exist with proper deep copy for mutable defaults
        for k, v in DEFAULT_USER_PREFERENCES.items():
            if k not in data:
                data[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
        return data

    async def set(self, user_id: int, data: dict[str, Any]) -> None:
        """Set user preferences, creating or updating as needed.

        Uses ON CONFLICT DO UPDATE (upsert) to handle both new and existing users.

        Args:
            user_id: Discord user snowflake ID
            data: Preferences dictionary to store
        """
        payload = json.dumps(data)
        await self.db.execute(
            "INSERT INTO user_preferences (user_id, data_json) VALUES (?, ?)\n"
            "ON CONFLICT(user_id) DO UPDATE SET data_json = excluded.data_json, updated_at = CURRENT_TIMESTAMP",
            (str(user_id), payload),
        )

    async def set_response_length(self, user_id: int, length: str) -> None:
        """Set the response length preference for a user.

        Args:
            user_id: Discord user snowflake ID
            length: One of "concise", "balanced", or "detailed"

        Raises:
            ValueError: If length is not a valid option
        """
        if length not in VALID_RESPONSE_LENGTHS:
            raise ValueError(
                f"Invalid response length '{length}'. Must be one of: {', '.join(VALID_RESPONSE_LENGTHS)}"
            )
        data = await self.get(user_id)
        data["response_length"] = length
        await self.set(user_id, data)

    async def set_emoji_density(self, user_id: int, density: str) -> None:
        """Set the emoji density preference for a user.

        Args:
            user_id: Discord user snowflake ID
            density: One of "none", "minimal", "normal", or "lots"

        Raises:
            ValueError: If density is not a valid option
        """
        if density not in VALID_EMOJI_DENSITIES:
            raise ValueError(
                f"Invalid emoji density '{density}'. Must be one of: {', '.join(VALID_EMOJI_DENSITIES)}"
            )
        data = await self.get(user_id)
        data["emoji_density"] = density
        await self.set(user_id, data)

    async def set_preferred_persona(self, user_id: int, persona_name: str | None) -> None:
        """Set the preferred persona for a user.

        Args:
            user_id: Discord user snowflake ID
            persona_name: Name of the persona, or None to clear preference
        """
        data = await self.get(user_id)
        data["preferred_persona"] = persona_name
        await self.set(user_id, data)

    async def resolve_response_length(self, user_id: int) -> str:
        """Resolve the response length preference for a user.

        Args:
            user_id: Discord user snowflake ID

        Returns:
            The stored response length or "balanced" as default
        """
        data = await self.get(user_id)
        return data.get("response_length", DEFAULT_USER_PREFERENCES["response_length"])  # type: ignore[return-value]

    async def resolve_emoji_density(self, user_id: int) -> str:
        """Resolve the emoji density preference for a user.

        Args:
            user_id: Discord user snowflake ID

        Returns:
            The stored emoji density or "normal" as default
        """
        data = await self.get(user_id)
        return data.get("emoji_density", DEFAULT_USER_PREFERENCES["emoji_density"])  # type: ignore[return-value]

    async def resolve_preferred_persona(self, user_id: int) -> str | None:
        """Resolve the preferred persona for a user.

        Args:
            user_id: Discord user snowflake ID

        Returns:
            The stored persona name or None if not set
        """
        data = await self.get(user_id)
        return data.get("preferred_persona", DEFAULT_USER_PREFERENCES["preferred_persona"])

    async def reset(self, user_id: int) -> None:
        """Reset user preferences back to defaults.

        Deletes the user's row from the user_preferences table.

        Args:
            user_id: Discord user snowflake ID
        """
        await self.db.execute(
            "DELETE FROM user_preferences WHERE user_id = ?",
            (str(user_id),),
        )
