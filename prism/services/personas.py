from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .db import Database


log = logging.getLogger(__name__)


class PersonaModel(BaseModel):
    name: str
    display_name: Optional[str] = None
    description: str = Field(default="")
    system_prompt: str
    style: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


@dataclass
class PersonaRecord:
    name: str
    source: str  # "builtin" | "user"
    data: PersonaModel
    path: Optional[str] = None  # filesystem path, if applicable


class PersonasService:
    def __init__(self, db: Database, defaults_dir: str) -> None:
        # DB retained in signature for compatibility; no longer used for personas
        self.db = db
        # All personas live directly under this directory (TOML only)
        self.defaults_dir = defaults_dir
        self._builtins: Dict[str, PersonaRecord] = {}

    async def load_builtins(self) -> None:
        self._builtins.clear()
        if not os.path.isdir(self.defaults_dir):
            log.warning("Personas defaults dir not found: %s", self.defaults_dir)
        # Walk only the top-level personas directory (flat TOML files)
        root = self.defaults_dir
        if not os.path.isdir(root):
            return
        for fname in sorted(os.listdir(root)):
            try:
                path = os.path.join(root, fname)
                if not os.path.isfile(path):
                    continue
                if not fname.endswith(".toml"):
                    continue
                # Use stdlib tomllib on Python 3.11+
                try:
                    import tomllib  # type: ignore
                except Exception:  # pragma: no cover - very unlikely on 3.11
                    tomllib = None  # type: ignore
                if not tomllib:
                    continue
                with open(path, "rb") as f:
                    tdata = tomllib.load(f)
                # Skip base files that are not personas
                if not isinstance(tdata, dict) or "name" not in tdata:
                    continue
                name = str(tdata.get("name") or "").strip()
                desc = str(tdata.get("description") or "").strip()
                disp = str(tdata.get("display_name") or "").strip()
                sections: List[str] = []
                for key in ("personality_traits", "communication_style", "behavior_patterns", "core_principles", "style", "constraints", "system_prompt"):
                    sec = tdata.get(key)
                    if isinstance(sec, dict) and isinstance(sec.get("content"), str):
                        sections.append(sec["content"].strip())
                sys_prompt = "\n\n".join([s for s in sections if s]).strip()
                if not name or not sys_prompt:
                    continue
                slug = self._slug(name)
                display = disp or self._title_from_slug(slug)
                model = PersonaModel(name=slug, display_name=display, description=desc, system_prompt=sys_prompt)
                rec = PersonaRecord(name=model.name.lower(), source="builtin", data=model, path=path)
                self._builtins[rec.name] = rec
                # Auto-migrate: if file lacks display_name, persist it
                try:
                    if not disp:
                        self._write_toml_persona(path, model)
                except Exception as _e:
                    log.debug("display_name migration skipped for %s: %s", path, _e)
            except Exception as e:  # noqa: BLE001
                log.error("Failed loading persona %s: %s", path, e)

    async def list(self) -> List[PersonaRecord]:
        # Return all personas known from filesystem
        return [self._builtins[k] for k in sorted(self._builtins.keys())]

    async def get(self, name: str) -> Optional[PersonaRecord]:
        key = name.lower()
        return self._builtins.get(key)

    async def create(self, model: PersonaModel) -> None:
        # Enforce kebab-case canonical name
        model.name = self._slug(model.name)
        # Validate uniqueness across filesystem
        if (await self.get(model.name)) is not None:
            raise ValueError(f"Persona '{model.name}' already exists")
        os.makedirs(self.defaults_dir, exist_ok=True)
        path = os.path.join(self.defaults_dir, f"{self._slug(model.name)}.toml")
        self._write_toml_persona(path, model)
        await self.load_builtins()

    async def update(self, name: str, updates: Dict[str, Any]) -> None:
        rec = await self.get(name)
        if not rec:
            raise ValueError(f"Persona '{name}' not found")
        data = rec.data.to_dict()
        data.update({k: v for k, v in updates.items() if v is not None})
        # Maintain canonical name
        data["name"] = rec.data.name
        model = PersonaModel(**data)
        # Update in-place when possible; if path missing, write to personas dir
        dest_path = rec.path or os.path.join(self.defaults_dir, f"{self._slug(rec.data.name)}.toml")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        self._write_toml_persona(dest_path, model)
        await self.load_builtins()

    async def delete(self, name: str) -> None:
        rec = await self.get(name)
        if not rec:
            raise ValueError(f"Persona '{name}' not found")
        try:
            if rec.path and os.path.isfile(rec.path):
                os.remove(rec.path)
            else:
                # Attempt to remove a persona file by kebab name
                path = os.path.join(self.defaults_dir, f"{self._slug(name)}.toml")
                if os.path.isfile(path):
                    os.remove(path)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Failed to delete persona file: {e}")
        await self.load_builtins()

    # ---------------------- Helpers ----------------------
    @staticmethod
    def _slug(name: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
        s = re.sub(r"-+", "-", s).strip("-")
        return s.lower() or "persona"

    @staticmethod
    def _title_from_slug(slug: str) -> str:
        parts = re.split(r"[-_\s]+", (slug or "").strip())
        return " ".join(w.capitalize() for w in parts if w)

    def _write_toml_persona(self, path: str, model: PersonaModel) -> None:
        # Minimal TOML writer that our loader can read back. We store the system prompt
        # under a [system_prompt] table with a single 'content' field.
        def esc(s: str) -> str:
            return s.replace("\\", "\\\\").replace("\"", "\\\"")
        body = []
        body.append(f"name = \"{esc(model.name)}\"")
        if (model.display_name or "").strip():
            body.append(f"display_name = \"{esc(str(model.display_name))}\"")
        body.append(f"description = \"{esc(model.description or '')}\"")
        if model.model is not None:
            body.append(f"model = \"{esc(str(model.model))}\"")
        if model.temperature is not None:
            body.append(f"temperature = {model.temperature}")
        if model.style is not None:
            body.append(f"style = \"{esc(str(model.style))}\"")
        body.append("")
        body.append("[system_prompt]")
        body.append("content = \"\"\"")
        # Preserve newlines; close with triple quotes
        body.append((model.system_prompt or "").replace("\r\n", "\n"))
        body.append("\"\"\"")
        txt = "\n".join(body) + "\n"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"Failed to write persona file: {e}")

    async def ai_draft_and_create(self, orc, name: Optional[str], outline: str) -> str:
        """Draft a persona with the LLM and create it on disk.

        If name is None/empty, the LLM must propose a concise Title Case name.
        Returns the final created persona name.
        """
        want_name = name and name.strip()
        sys = (
            "You design persona system prompts and names for an AI assistant.\n"
            "Return STRICT JSON with keys: name (string), description (short), system_prompt (string).\n"
            "System_prompt should contain 2–3 sections with bullet points: Personality traits; Communication style; Behavior patterns.\n"
            "Keep it concise and broadly applicable. Do not include base guidelines; those are applied separately.\n"
            "Name style: 1–3 words, Title Case, descriptive, no quotes."
        )
        if want_name:
            user = (
                f"Persona name: {want_name}\n"
                f"Outline:\n\n{outline.strip()}\n\n"
                "Return JSON only. Use the provided name as-is."
            )
        else:
            user = (
                f"Outline:\n\n{outline.strip()}\n\n"
                "Return JSON only. Propose a good name."
            )
        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ]
        text, _meta = await orc.chat_completion(messages)
        raw = (text or "").strip()
        data = None
        try:
            data = json.loads(raw)
        except Exception:
            try:
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(raw[start : end + 1])
            except Exception:
                data = None
        if not isinstance(data, dict):
            raise ValueError("AI did not return valid JSON")
        original_name = (name or str(data.get("name") or "")).strip()
        proposed_name = self._slug(original_name)
        if not proposed_name:
            # Fallback name from outline
            proposed_name = self._slug((outline.split("\n", 1)[0].strip() or "custom-persona")[:48])
        final_name = await self._ensure_unique_name(proposed_name)
        description = str(data.get("description") or "").strip() or "Custom persona"
        system_prompt = str(data.get("system_prompt") or "").strip()
        if not system_prompt:
            raise ValueError("AI did not include a system_prompt")
        display_name = original_name.strip() or self._title_from_slug(final_name)
        await self.create(
            PersonaModel(
                name=final_name,
                display_name=display_name,
                description=description,
                system_prompt=system_prompt,
            )
        )
        return final_name

    async def _ensure_unique_name(self, name: str) -> str:
        base = self._slug(name)
        if not await self.get(base):
            return base
        # Try appending numeric suffixes
        for i in range(2, 100):
            candidate = f"{base}-{i}"
            if not await self.get(candidate):
                return candidate
        # Give up and return original; will fail on create
        return base
