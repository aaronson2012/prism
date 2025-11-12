from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .db import Database
from .emoji_index import EmojiIndexService
from .rate_limit import RateLimiter, RateLimitConfig


log = logging.getLogger(__name__)


_ONLY_PUNCT_WS_RE = re.compile(r"^[\W_\s]+$")

# Fallback Unicode emojis for when no custom emojis are available or keyword matching fails
_FALLBACK_UNICODE_EMOJIS = [
    ("👍", "thumbs_up", "positive, approval, good, like, agree"),
    ("❤️", "heart", "love, like, care, emotion"),
    ("😊", "smiling_face", "happy, smile, joy, positive"),
    ("🎉", "party_popper", "celebration, party, congratulations, achievement"),
    ("😂", "laughing", "funny, lol, humor, laugh"),
    ("🔥", "fire", "hot, cool, awesome, amazing"),
    ("💯", "hundred", "perfect, excellent, great, full score"),
    ("👏", "clapping", "applause, well done, bravo, congratulations"),
    ("😍", "heart_eyes", "love, adore, wonderful, beautiful"),
    ("🤔", "thinking", "hmm, consider, think, wonder"),
    ("😢", "sad", "sad, cry, sorry, sympathy"),
    ("👀", "eyes", "look, see, watching, interested"),
]


@dataclass
class ReactionEngineConfig:
    min_score: float = 0.6
    max_reactions_per_message: int = 1


@dataclass
class ReactionDecision:
    emoji: str
    score: float
    reason: str


class ReactionEngine:
    def __init__(
        self,
        db: Database,
        emoji_index: EmojiIndexService,
        rate_limiter: Optional[RateLimiter] = None,
        cfg: Optional[ReactionEngineConfig] = None,
    ) -> None:
        self.db = db
        self.emoji_index = emoji_index
        self.rate = rate_limiter or RateLimiter(RateLimitConfig())
        self.cfg = cfg or ReactionEngineConfig()

    async def maybe_react(self, orc: Any, message: Any) -> int:
        """Decide whether to add an emoji reaction to a message. Returns number added (0/1)."""
        try:
            if getattr(message.author, "bot", False) or getattr(message, "webhook_id", None):
                return 0
            if not message.guild:
                return 0
            content = (message.content or "").strip()
            if not content or len(content) < 6 or _ONLY_PUNCT_WS_RE.match(content):
                return 0
            if not self.rate.allow(message.guild.id, message.channel.id, message.author.id):
                return 0

            # Build candidate list with metadata (mix of custom + unicode)
            try:
                cmeta = await self.emoji_index.suggest_with_meta_for_text(message.guild.id, content, style=None, limit=6)
            except Exception as e:  # noqa: BLE001
                log.debug("emoji candidates failed: %s", e)
                cmeta = []
            # Fallback: direct from guild if index empty
            if not cmeta:
                try:
                    for e in list(getattr(message.guild, "emojis", []) or [])[:6]:
                        tok = f"<{'a' if getattr(e, 'animated', False) else ''}:{e.name}:{e.id}>"
                        cmeta.append({"token": tok, "name": e.name, "description": ""})
                except Exception:
                    pass
            # Final fallback: use common Unicode emojis if still no candidates
            if not cmeta:
                log.debug("Using fallback Unicode emojis for reaction candidates")
                for emoji_char, name, desc in _FALLBACK_UNICODE_EMOJIS:
                    cmeta.append({"token": emoji_char, "name": name, "description": desc})
            if not cmeta:
                log.warning("No emoji candidates available for reaction (guild=%s, channel=%s)", message.guild.id, message.channel.id)
                return 0
            
            log.debug("Reaction candidates (%d): %s", len(cmeta), [m.get("token") for m in cmeta[:8]])

            # Usage weights from recent reaction history (per channel)
            usage = await self._get_usage_weights(message.guild.id, message.channel.id)

            decision = await self._score_with_llm(orc, content, cmeta, usage)
            if not decision:
                log.info("LLM returned no decision for reaction (guild=%s, channel=%s, msg_id=%s)", message.guild.id, message.channel.id, message.id)
                return 0
            
            log.info("LLM reaction decision: emoji=%s, score=%.2f, reason=%s (guild=%s, channel=%s, msg_id=%s)", 
                     decision.emoji, decision.score, decision.reason[:50], message.guild.id, message.channel.id, message.id)
            
            if not decision.emoji:
                log.info("Decision has no emoji (guild=%s, channel=%s, msg_id=%s)", message.guild.id, message.channel.id, message.id)
                return 0
            
            if decision.score < self.cfg.min_score:
                log.info("Decision score %.2f below threshold %.2f (guild=%s, channel=%s, msg_id=%s)", 
                         decision.score, self.cfg.min_score, message.guild.id, message.channel.id, message.id)
                return 0

            added = await self._add_reaction_token(message, decision.emoji)
            if added:
                self.rate.mark(message.guild.id, message.channel.id, message.author.id)
                await self._log(message.guild.id, message.channel.id, message.id, decision.emoji, decision.score, decision.reason)
                log.info("Successfully added reaction %s to message (guild=%s, channel=%s, msg_id=%s)", 
                         decision.emoji, message.guild.id, message.channel.id, message.id)
                return 1
            else:
                log.warning("Failed to add reaction %s to message (guild=%s, channel=%s, msg_id=%s)", 
                            decision.emoji, message.guild.id, message.channel.id, message.id)
            return 0
        except Exception as e:  # noqa: BLE001
            log.debug("maybe_react failed: %s", e)
            return 0

    async def _score_with_llm(self, orc: Any, content: str, cmeta: List[Dict[str, Any]], usage: Dict[str, int]) -> Optional[ReactionDecision]:
        system = (
            "You decide if an emoji reaction is appropriate for a Discord message.\n"
            "You should be friendly and enthusiastic - add reactions when messages express emotions, achievements, or interesting content.\n"
            "Choose one emoji from the provided candidates that best matches the message sentiment.\n"
            "Prefer custom server emojis when available and relevant.\n"
            "Consider popularity hints to keep reactions feeling native to the channel.\n"
            "Output STRICT JSON only: {\"emoji\": string, \"score\": number, \"reason\": string}.\n"
            "- emoji: one of the candidate tokens (copy exactly)\n"
            "- score: 0.0–1.0 confidence (be generous: 0.7+ for good matches)\n"
            "- reason: brief explanation why this emoji fits\n"
            "Examples of when to react: positive statements, achievements, emotions, questions, interesting topics.\n"
            "You can choose not to react by setting score to 0.0 if the message is truly neutral or boring.\n"
        )
        # Build readable candidate lines with titles, type, and simple popularity
        lines: List[str] = []
        tokens: List[str] = []
        for m in cmeta:
            tok = str(m.get("token") or "")
            if not tok:
                continue
            tokens.append(tok)
            title = (str(m.get("name") or "emoji")).strip()
            is_custom = tok.startswith("<")
            pop = usage.get(tok, 0)
            desc = (str(m.get("description") or "").strip())
            if desc:
                desc = desc[:120]
            t = "custom" if is_custom else "unicode"
            line = f"- {tok} — {title} ({t}, pop {pop})"
            if desc:
                line += f": {desc}"
            lines.append(line)

        user = (
            "Message:\n" + content + "\n\nCandidates (pick zero or one; output the token exactly):\n" + "\n".join(lines) + "\n\n"
            "Return JSON only."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            text, _meta = await orc.chat_completion(messages)
        except Exception as e:  # noqa: BLE001
            log.debug("LLM reaction score failed: %s", e)
            return None
        raw = (text or "").strip()
        log.debug("LLM reaction response (raw): %s", raw[:200])
        data: Dict[str, Any] | None = None
        try:
            data = json.loads(raw)
        except Exception:
            # try to extract object JSON
            try:
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(raw[start : end + 1])
            except Exception:
                data = None
        if not isinstance(data, dict):
            log.debug("LLM reaction response not valid JSON dict: %s", type(data))
            return None
        emoji = str(data.get("emoji") or "").strip()
        reason = str(data.get("reason") or "").strip()
        try:
            score = float(data.get("score") or 0.0)
        except Exception:
            score = 0.0
        log.debug("LLM reaction parsed: emoji=%s, score=%.2f, reason=%s", emoji, score, reason[:50])
        if not emoji or emoji not in tokens:
            if emoji:
                log.debug("LLM returned emoji not in candidates: %s (candidates: %s)", emoji, tokens[:5])
            return None
        return ReactionDecision(emoji=emoji, score=score, reason=reason)

    async def _get_usage_weights(self, guild_id: int, channel_id: int) -> Dict[str, int]:
        """Return a simple popularity map token->count from recent reaction logs for the channel."""
        try:
            rows = await self.db.fetchall(
                "SELECT emoji, COUNT(*) as c FROM reaction_log WHERE guild_id = ? AND channel_id = ? AND ts >= datetime('now','-14 days') GROUP BY emoji ORDER BY c DESC LIMIT 200",
                (str(guild_id), str(channel_id)),
            )
            return {str(r[0]): int(r[1]) for r in rows if r[0] is not None}
        except Exception as e:  # noqa: BLE001
            log.debug("usage weights fetch failed: %s", e)
            return {}

    async def _add_reaction_token(self, message: Any, token: str) -> bool:
        """
        Add a reaction given a token from candidates. Tokens may be Unicode (single char) or
        custom Discord emoji in the form <:name:id> or <a:name:id>.
        """
        try:
            # Unicode emoji: assume direct string works
            if token and not token.startswith("<"):
                await message.add_reaction(token)
                return True

            # Custom emoji: parse name/id
            m = re.match(r"^<a?:([^:>]+):(\d+)>$", token)
            if not m:
                return False
            _ = m.group(1)  # name not used
            eid = int(m.group(2))
            # Lazy import util for lookup
            from discord.utils import get  # type: ignore

            emoji_obj = get(getattr(message.guild, "emojis", []) or [], id=eid)
            if emoji_obj is None:
                # Try fetch for good measure
                try:
                    emoji_obj = await message.guild.fetch_emoji(eid)
                except Exception:  # noqa: BLE001
                    emoji_obj = None
            if emoji_obj is None:
                return False
            await message.add_reaction(emoji_obj)
            return True
        except Exception as e:  # noqa: BLE001
            log.debug("add_reaction failed for %r: %s", token, e)
            return False

    async def _log(self, guild_id: int, channel_id: int, message_id: int, emoji: str, score: float, reason: str) -> None:
        try:
            await self.db.execute(
                "INSERT INTO reaction_log (guild_id, channel_id, message_id, emoji, score, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (str(guild_id), str(channel_id), str(message_id), emoji, float(score), reason[:400]),
            )
        except Exception as e:  # noqa: BLE001
            log.debug("failed to log reaction: %s", e)
