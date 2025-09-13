from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .db import Database

log = logging.getLogger(__name__)


_URL_RE = re.compile(r"https?://\S+", re.I)
_EMOJI_OR_WS_RE = re.compile(r"^[\s\W_]+$")
_GREETING_RE = re.compile(r"^(gm+|gn+|good\s+(morning|evening|night)|hello|hey|hi)\b", re.I)
_TIMEBOUND_RE = re.compile(r"\b(now|today|tonight|this\s+(morning|afternoon|evening)|just|right\s+now|currently)\b", re.I)
_NUMERICISH_RE = re.compile(r"^[\W_\d]+$")


ALLOWED_KEYS = [
    "likes",
    "dislikes",
    "interests",
    "hobbies",
    "skills",
    "role",
    "life_stage",
    "languages",
    "timezone",
    "pronouns",
    "communication_style",
    "tone_preferences",
    "values",
    "affiliations",
    "nicknames",
]


@dataclass
class LearningConfig:
    confidence_threshold: float = 0.75
    facts_per_user: int = 10
    participant_window_messages: int = 50
    confirm_confidence: float = 0.85
    confirm_support: int = 2
    # Soft concision control: penalize confidence for overly long values
    soft_max_value_words: int = 7
    value_length_penalty_per_word: float = 0.03  # subtract per word over the soft max
    # Hard cap: drop values exceeding this many words
    hard_max_value_words: int = 15


class UserLearningService:
    def __init__(self, db: Database, cfg: Optional[LearningConfig] = None) -> None:
        self.db = db
        self.cfg = cfg or LearningConfig()

    # ---------------------- Public API ----------------------
    async def learn_from_message(
        self,
        orc,
        guild_id: int,
        user_id: int,
        content: str,
        message_id: Optional[int] = None,
        model: Optional[str] = None,
    ) -> int:
        if not content or self._gate_message(content):
            return 0

        try:
            result = await self._extract_with_llm(orc, content, model)
        except Exception as e:  # noqa: BLE001
            log.warning("Fact extraction failed: %s", e)
            return 0

        if not isinstance(result, dict):
            return 0
        if result.get("sarcastic") is True:
            return 0
        items = result.get("facts") or []
        if not isinstance(items, list):
            return 0

        n = 0
        for f in items:
            key = str(f.get("key", "")).strip().lower()[:64]
            val = str(f.get("value", "")).strip()[:400]
            src = str(f.get("source") or "").strip().lower() or "implicit"
            try:
                conf = float(f.get("confidence", 0.0))
            except Exception:
                conf = 0.0
            if not key or not val:
                continue
            if key not in ALLOWED_KEYS:
                continue
            if self._fails_value_checks(val):
                continue
            # Hard cap on value verbosity: auto-drop if too many words
            try:
                wc = self._word_count(val)
            except Exception:
                wc = 0
            if wc > max(1, int(self.cfg.hard_max_value_words)):
                log.debug(
                    "value exceeds hard word cap: key=%s words=%d cap=%d", key, wc, self.cfg.hard_max_value_words
                )
                continue
            # Soft post-filter: apply confidence penalty for verbose values to enforce concision
            conf_before = conf
            conf = self._apply_value_length_penalty(conf, val)
            if conf < conf_before:
                log.debug(
                    "value length penalty applied: key=%s words=%d conf: %.2f -> %.2f",
                    key,
                    self._word_count(val),
                    conf_before,
                    conf,
                )
            if conf < self.cfg.confidence_threshold:
                continue
            try:
                await self._upsert_fact(guild_id, user_id, key, val, conf, src, message_id, content)
                n += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Upsert fact failed for %s/%s (%s=%s): %s", guild_id, user_id, key, val, e)
        return n

    async def get_top_facts(self, guild_id: int, user_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        lim = limit or self.cfg.facts_per_user
        rows = await self.db.fetchall(
            "SELECT key, value, confidence, status, support_count, last_seen FROM user_facts "
            "WHERE guild_id = ? AND user_id = ? ORDER BY (status = 'confirmed') DESC, confidence DESC, last_seen DESC LIMIT ?",
            (str(guild_id), str(user_id), int(lim)),
        )
        return [
            {
                "key": row[0],
                "value": row[1],
                "confidence": float(row[2]) if row[2] is not None else 0.0,
                "status": str(row[3] or "candidate"),
                "support": int(row[4] or 1),
            }
            for row in rows
        ]

    async def clear_facts(self, guild_id: int, user_id: int, key: Optional[str] = None) -> None:
        if key:
            await self.db.execute(
                "DELETE FROM user_facts WHERE guild_id = ? AND user_id = ? AND LOWER(key) = LOWER(?)",
                (str(guild_id), str(user_id), key),
            )
        else:
            await self.db.execute(
                "DELETE FROM user_facts WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )

    # ---------------------- Internals ----------------------
    @staticmethod
    def _normalize_value(value: str) -> str:
        v = value.strip().lower()
        # Simple normalizations
        repl = {
            "js": "javascript",
            "doggos": "dogs",
            "doggo": "dogs",
        }
        return repl.get(v, v)

    @staticmethod
    def _gate_message(text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        if len(t) < 12 and not re.search(r"\bI\b|\bI'm\b|\bI am\b|\bI like\b|\bmy\b", t, re.I):
            return True
        if _EMOJI_OR_WS_RE.match(t):
            return True
        if _URL_RE.search(t) and len(t) < 60:
            return True
        if _GREETING_RE.search(t):
            return True
        return False

    @staticmethod
    def _fails_value_checks(value: str) -> bool:
        v = (value or "").strip()
        if not v:
            return True
        if _NUMERICISH_RE.match(v):
            return True
        if _TIMEBOUND_RE.search(v):
            return True
        return False

    @staticmethod
    def _word_count(value: str) -> int:
        # Count alphanumeric-ish word tokens
        return len(re.findall(r"[A-Za-z0-9']+", value))

    def _apply_value_length_penalty(self, confidence: float, value: str) -> float:
        try:
            words = self._word_count(value)
        except Exception:
            return confidence
        max_words = max(1, int(self.cfg.soft_max_value_words))
        if words <= max_words:
            return confidence
        extra = words - max_words
        penalty = max(0.0, float(self.cfg.value_length_penalty_per_word)) * float(extra)
        # Cap the penalty to avoid over-penalizing
        penalty = min(0.35, penalty)
        new_conf = max(0.0, float(confidence) - penalty)
        return new_conf

    async def _upsert_fact(
        self,
        guild_id: int,
        user_id: int,
        key: str,
        value: str,
        confidence: float,
        source: str,
        message_id: Optional[int],
        evidence_text: Optional[str],
    ) -> None:
        norm = self._normalize_value(value)
        row = await self.db.fetchone(
            "SELECT id, confidence, support_count, status FROM user_facts WHERE guild_id = ? AND user_id = ? AND LOWER(key) = LOWER(?) AND LOWER(IFNULL(normalized_value, value)) = LOWER(?) LIMIT 1",
            (str(guild_id), str(user_id), key, norm or value.lower()),
        )
        # Determine new status
        confirm = (source == "explicit" and confidence >= self.cfg.confirm_confidence)
        support = 1
        if row:
            support = int(row[2] or 1) + 1
            new_conf = max(confidence, float(row[1]) if row[1] is not None else 0.0)
            # small incremental boost on repeat evidence
            new_conf = min(0.98, new_conf + 0.05)
            if support >= self.cfg.confirm_support or new_conf >= self.cfg.confirm_confidence:
                confirm = True
            new_status = "confirmed" if confirm else str(row[3] or "candidate")
            await self.db.execute(
                "UPDATE user_facts SET confidence = ?, support_count = ?, status = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?",
                (new_conf, support, new_status, int(row[0])),
            )
        else:
            status = "confirmed" if confirm else "candidate"
            await self.db.execute(
                "INSERT INTO user_facts (guild_id, user_id, key, value, normalized_value, confidence, status, support_count, source, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(guild_id),
                    str(user_id),
                    key,
                    value,
                    norm,
                    float(confidence),
                    status,
                    1,
                    source,
                    (evidence_text or None),
                ),
            )

    async def _extract_with_llm(self, orc, content: str, model: Optional[str] = None) -> Dict[str, Any]:
        allowed = ", ".join(ALLOWED_KEYS)
        system = (
            "You extract durable, generalizable self-facts from a single chat message and detect sarcasm.\n"
            "Return STRICT JSON only with keys: sarcastic (bool), facts (array of items).\n"
            "Selection principles:\n"
            "- Capture identity-level attributes and stable preferences that remain useful across contexts and over time.\n"
            "- Focus on broad patterns and categories that are platform-agnostic and context-independent.\n"
            "- When content is narrow or situational, abstract to a concise, high-level description only if meaning is preserved; otherwise, omit it.\n"
            "- Use only first-person self-facts about the author.\n"
            "- Exclude greetings, intentions, requests, time-bound states, PII, and secrets.\n"
            f"- Allowed keys only: {allowed}.\n"
            "Value style:\n"
            "- Values are canonical and concise (aim for 1–5 words) and, when reasonable, at the category level rather than product/feature specifics.\n"
            "- For explicit self-statements, set source='explicit'; otherwise set source='implicit'.\n"
            "Key semantics:\n"
            "- Use 'affiliations' for stable memberships in named organizations, communities, or roles.\n"
            "Sarcasm handling:\n"
            "- If the message is sarcastic or joking about the content, set sarcastic=true and return an empty facts array.\n"
            "Item schema: {key, value, confidence, source}. confidence in [0.0,1.0]."
        )
        user = (
            "Message:\n" + content.strip() + "\n\n"
            "Return JSON only."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        text, _meta = await orc.chat_completion(messages, model=model)
        raw = (text or "").strip()
        # Parse JSON object with fallback
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(raw[start : end + 1])
                if isinstance(data, dict):
                    return data
        except Exception as e:  # noqa: BLE001
            log.debug("JSON extraction fallback failed: %s; raw=%r", e, raw[:200])
        return {"sarcastic": False, "facts": []}
