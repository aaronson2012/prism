from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class RateLimitConfig:
    channel_cooldown_sec: float = 120.0
    user_cooldown_sec: float = 60.0


class RateLimiter:
    """
    Simple in-memory rate limiter with per-channel and per-user cooldowns.
    Intended for a single running bot process.
    """

    def __init__(self, cfg: RateLimitConfig | None = None) -> None:
        self.cfg = cfg or RateLimitConfig()
        self._last_channel: Dict[str, float] = {}
        self._last_user: Dict[str, float] = {}

    def allow(self, guild_id: int, channel_id: int, user_id: int) -> bool:
        now = time.monotonic()
        ch_key = f"{guild_id}:{channel_id}"
        u_key = f"{guild_id}:{user_id}"

        # Check channel cooldown
        last_ch = self._last_channel.get(ch_key, 0.0)
        if now - last_ch < self.cfg.channel_cooldown_sec:
            return False

        # Check user cooldown
        last_u = self._last_user.get(u_key, 0.0)
        if now - last_u < self.cfg.user_cooldown_sec:
            return False

        return True

    def mark(self, guild_id: int, channel_id: int, user_id: int) -> None:
        now = time.monotonic()
        ch_key = f"{guild_id}:{channel_id}"
        u_key = f"{guild_id}:{user_id}"
        self._last_channel[ch_key] = now
        self._last_user[u_key] = now
