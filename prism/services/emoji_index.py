from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .db import Database


log = logging.getLogger(__name__)


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class CustomEmoji:
    guild_id: int
    emoji_id: int
    name: str
    animated: bool
    description: Optional[str]


class EmojiIndexService:
    """
    Indexes custom emojis per guild (DB) and provides lightweight Unicode emoji suggestions
    using the `emoji` library in-memory data. Generates descriptive blurbs (2–3 sentences)
    for custom emojis via the LLM and stores them for future prompts.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._unicode_index: Optional[List[Tuple[str, str, List[str]]]] = None

    # ------------------------- Public API -------------------------
    async def index_guild(self, guild: "Any") -> int:
        """Scan and upsert the guild's custom emojis. Returns count processed."""
        try:
            emojis = list(getattr(guild, "emojis", []) or [])
        except Exception as e:  # noqa: BLE001
            log.debug("Failed to read guild.emojis for %s: %s", getattr(guild, "id", "?"), e)
            return 0
        n = 0
        for e in emojis:
            try:
                await self._upsert_custom(
                    guild_id=guild.id,
                    emoji_id=e.id,
                    name=e.name or f"emoji_{e.id}",
                    animated=bool(getattr(e, "animated", False)),
                )
                n += 1
            except Exception as ex:  # noqa: BLE001
                log.debug("Failed upsert custom emoji %s:%s: %s", guild.id, getattr(e, "id", "?"), ex)
        return n

    async def index_all_guilds(self, bot: "Any") -> Dict[int, int]:
        """Index all guilds the bot is in. Returns map guild_id->count."""
        results: Dict[int, int] = {}
        for g in getattr(bot, "guilds", []) or []:
            try:
                results[g.id] = await self.index_guild(g)
            except Exception as e:  # noqa: BLE001
                log.debug("Index guild failed for %s: %s", g.id, e)
        return results

    async def ensure_descriptions(self, orc: "Any", guild_id: int, limit: int = 50) -> int:
        """Generate descriptive (2–3 sentences) descriptions for custom emojis missing one. Returns count updated."""
        rows = await self.db.fetchall(
            "SELECT id, emoji_id, name, animated FROM emoji_index "
            "WHERE guild_id = ? AND is_custom = 1 AND (description IS NULL OR TRIM(description) = '') "
            "ORDER BY id DESC LIMIT ?",
            (str(guild_id), int(limit)),
        )
        if not rows:
            return 0

        items = [
            {"id": int(r[0]), "emoji_id": str(r[1] or ""), "name": str(r[2] or ""), "animated": bool(r[3] or 0)}
            for r in rows
        ]
        desc_map = await self._describe_custom_batch(orc, items)
        n = 0
        for row in items:
            desc = (desc_map.get(row["name"]) or desc_map.get(row["emoji_id"]) or "").strip()
            if not desc:
                continue
            try:
                await self.db.execute(
                    "UPDATE emoji_index SET description = ?, last_scanned_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (desc, int(row["id"])),
                )
                n += 1
            except Exception as e:  # noqa: BLE001
                log.debug("Failed to update emoji description id=%s: %s", row["id"], e)
        return n

    async def suggest_for_text(
        self, guild_id: int, text: str, style: Optional[str] = None, limit: int = 6
    ) -> List[str]:
        """
        Backwards-compatible wrapper that returns only emoji tokens.
        """
        meta = await self.suggest_with_meta_for_text(guild_id, text, style=style, limit=limit)
        return [m["token"] for m in meta]

    async def suggest_with_meta_for_text(
        self, guild_id: int, text: str, style: Optional[str] = None, limit: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Suggest emoji candidates with metadata for prompts (mix of custom and unicode).
        Returns a list of dicts: {token, name, description}.
        """
        text_tokens = _tokenize(text)

        # Custom emoji candidates from DB
        custom = await self._fetch_custom(guild_id)
        custom_scored: List[Tuple[float, Dict[str, Any]]] = []
        for ce in custom:
            score = _score_keywords(text_tokens, [ce.name] + _tokenize(ce.description or ""))
            # Global bias toward custom (no modes)
            score += 0.10
            # Ensure we keep a few custom options even without direct keyword match
            if score <= 0:
                score = 0.01
            token = f"<{'a' if ce.animated else ''}:{ce.name}:{ce.emoji_id}>" if ce.name else f":{ce.emoji_id}:"
            custom_scored.append((score, {"token": token, "name": ce.name, "description": ce.description or ""}))
        custom_scored.sort(key=lambda x: x[0], reverse=True)

        # Unicode candidates from in-memory index
        uni_scored: List[Tuple[float, Dict[str, Any]]] = []
        for char, name, kws in self._get_unicode_index():
            score = _score_keywords(text_tokens, [name] + kws)
            if score <= 0:
                continue
            uni_scored.append((score, {"token": char, "name": name or "Unicode emoji", "description": ""}))
        uni_scored.sort(key=lambda x: x[0], reverse=True)

        merged: List[Dict[str, Any]] = []
        # Prefer a custom-heavy mix by default (~2/3 custom when available)
        custom_quota = max(1, min(len(custom_scored), (2 * limit + 2) // 3))
        for score, item in custom_scored[: custom_quota]:
            if all(item["token"] != m["token"] for m in merged):
                merged.append(item)
        # Then fill with unicode
        for score, item in uni_scored:
            if len(merged) >= limit:
                break
            if all(item["token"] != m["token"] for m in merged):
                merged.append(item)
        # If user explicitly asked about emojis but nothing matched, include some custom anyway
        if len(merged) < limit and any(t in {"emoji", "emojis", "custom", "customs"} for t in text_tokens):
            for ce in custom:
                tok = f"<{'a' if ce.animated else ''}:{ce.name}:{ce.emoji_id}>"
                if all(tok != m["token"] for m in merged):
                    merged.append({"token": tok, "name": ce.name, "description": ce.description or ""})
                if len(merged) >= limit:
                    break
        return merged[:limit]

    # ------------------------- Internals -------------------------
    async def _upsert_custom(self, guild_id: int, emoji_id: int, name: str, animated: bool) -> None:
        # Check if exists
        row = await self.db.fetchone(
            "SELECT id FROM emoji_index WHERE guild_id = ? AND is_custom = 1 AND emoji_id = ? LIMIT 1",
            (str(guild_id), str(emoji_id)),
        )
        if row:
            await self.db.execute(
                "UPDATE emoji_index SET name = ?, animated = ?, last_scanned_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, 1 if animated else 0, int(row[0])),
            )
        else:
            await self.db.execute(
                "INSERT INTO emoji_index (guild_id, emoji_id, name, is_custom, animated, keywords_json, aliases_json) "
                "VALUES (?, ?, ?, 1, ?, '[]', '[]')",
                (str(guild_id), str(emoji_id), name, 1 if animated else 0),
            )

    async def _fetch_custom(self, guild_id: int) -> List[CustomEmoji]:
        rows = await self.db.fetchall(
            "SELECT emoji_id, name, animated, description FROM emoji_index WHERE guild_id = ? AND is_custom = 1",
            (str(guild_id),),
        )
        out: List[CustomEmoji] = []
        for r in rows:
            try:
                out.append(
                    CustomEmoji(
                        guild_id=guild_id,
                        emoji_id=int(r[0]) if r[0] is not None else 0,
                        name=str(r[1] or ""),
                        animated=bool(r[2] or 0),
                        description=(r[3] or None),
                    )
                )
            except Exception:
                continue
        return out

    async def _describe_custom_batch(self, orc: "Any", items: List[Dict[str, Any]]) -> Dict[str, str]:
        """Call LLM to generate descriptive blurbs (2–3 sentences) for custom emojis based on name.
        Returns mapping by name to description.
        """
        if not items:
            return {}
        # Keep prompt small
        limited = items[:10]
        names = [i["name"] for i in limited]
        system = (
            "You generate descriptive blurbs for custom Discord emojis based on their names only.\n"
            "Return STRICT JSON object mapping each name to its description. No extra text.\n"
            "Each description should be 2–3 sentences (about 25–60 words total) describing likely meaning, tone, and typical usage contexts.\n"
            "Keep it neutral and helpful."
        )
        user = "Names: " + ", ".join(names)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            text, _meta = await orc.chat_completion(messages)
        except Exception as e:  # noqa: BLE001
            log.debug("LLM description fetch failed: %s", e)
            return {}
        raw = (text or "").strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                # Ensure only requested names; cap length to avoid prompt bloat
                return {k: str(v)[:600] for k, v in data.items() if k in names}
        except Exception:
            # Try to extract JSON object
            try:
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(raw[start : end + 1])
                    if isinstance(data, dict):
                        return {k: str(v)[:600] for k, v in data.items() if k in names}
            except Exception:
                pass
        return {}

    def _get_unicode_index(self) -> List[Tuple[str, str, List[str]]]:
        if self._unicode_index is not None:
            return self._unicode_index
        try:
            # Lazy import to reduce import-time overhead
            import emoji  # type: ignore

            data = getattr(emoji, "EMOJI_DATA", None)
            if data is None:
                # Older/newer versions may nest under unicode_codes
                try:
                    from emoji.unicode_codes import EMOJI_DATA as data2  # type: ignore
                except Exception:  # noqa: BLE001
                    data2 = None
                data = data2
            index: List[Tuple[str, str, List[str]]] = []
            if isinstance(data, dict):
                for ch, meta in data.items():
                    # name
                    name = str(meta.get("en") or meta.get("name") or meta.get("CLDR Short Name") or "").strip()
                    aliases = meta.get("aliases") or meta.get("alias") or meta.get("short_names") or []
                    if isinstance(aliases, dict):
                        aliases = list(aliases.values())
                    if isinstance(aliases, str):
                        aliases = [aliases]
                    keywords = meta.get("keywords") or []
                    if isinstance(keywords, dict):
                        keywords = list(keywords.values())
                    if not isinstance(keywords, list):
                        try:
                            keywords = list(keywords)
                        except Exception:
                            keywords = []
                    toks = _tokenize(" ".join([name] + [str(a) for a in aliases] + [str(k) for k in keywords]))
                    if not name and not toks:
                        continue
                    index.append((ch, name or "", toks))
            # Keep a lean index by removing skin-tone variants where possible
            self._unicode_index = index
        except Exception as e:  # noqa: BLE001
            log.debug("Failed to build unicode emoji index: %s", e)
            self._unicode_index = []
        return self._unicode_index


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _WORD_RE.findall(text) if t]


def _score_keywords(query_tokens: List[str], target_tokens: List[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0
    qt = set(query_tokens)
    tt = set([t.lower() for t in target_tokens if t])
    inter = qt.intersection(tt)
    if not inter:
        # fuzzy partial: substr match
        score = 0.0
        for q in qt:
            for t in tt:
                if len(q) >= 4 and q in t:
                    score += 0.2
        return score
    return min(1.0, len(inter) / (len(qt) ** 0.5))
