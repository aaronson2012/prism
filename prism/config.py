from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    discord_token: str
    openrouter_api_key: str
    default_model: str = "google/gemini-2.5-flash"
    fallback_model: str = "google/gemini-2.5-flash-lite"
    openrouter_site_url: str | None = None
    openrouter_app_name: str | None = None
    db_path: str = "data/prism.db"
    log_level: str = "INFO"
    intents_message_content: bool = True
    # Feature toggles
    emoji_talk_enabled: bool = True
    # Fast command sync to specific guilds (comma-separated IDs)
    command_guild_ids: list[int] | None = None


def load_config() -> Config:
    load_dotenv(override=False)

    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN is required in environment or .env")
    if not openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in environment or .env")

    # Parse optional COMMAND_GUILD_IDS as comma-separated list of ints
    raw_guilds = os.getenv("COMMAND_GUILD_IDS", "").strip()
    guild_ids: list[int] | None = None
    if raw_guilds:
        guild_ids = []
        for part in raw_guilds.replace(";", ",").split(","):
            p = part.strip()
            if not p:
                continue
            try:
                guild_ids.append(int(p))
            except Exception:
                # ignore malformed entries
                pass

    return Config(
        discord_token=discord_token,
        openrouter_api_key=openrouter_api_key,
        default_model=os.getenv("DEFAULT_MODEL", "google/gemini-2.5-flash").strip() or "google/gemini-2.5-flash",
        fallback_model=os.getenv("FALLBACK_MODEL", "google/gemini-2.5-flash-lite").strip() or "google/gemini-2.5-flash-lite",
        openrouter_site_url=os.getenv("OPENROUTER_SITE_URL") or None,
        openrouter_app_name=os.getenv("OPENROUTER_APP_NAME") or None,
        db_path=os.getenv("PRISM_DB_PATH", "data/prism.db"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        intents_message_content=os.getenv("INTENTS_MESSAGE_CONTENT", "true").lower() in {"1", "true", "yes", "on"},
        emoji_talk_enabled=os.getenv("EMOJI_TALK_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
        command_guild_ids=guild_ids,
    )
