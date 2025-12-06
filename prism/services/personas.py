from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
import re
from typing import Any

from pydantic import BaseModel, Field

from .db import Database


log = logging.getLogger(__name__)


class PersonaModel(BaseModel):
    name: str
    display_name: str | None = None
    description: str = Field(default="")
    system_prompt: str
    style: str | None = None
    model: str | None = None
    temperature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


@dataclass
class PersonaRecord:
    name: str
    source: str  # "builtin" | "user"
    data: PersonaModel
    path: str | None = None  # filesystem path, if applicable


class PersonasService:
    def __init__(self, db: Database, defaults_dir: str) -> None:
        # DB retained in signature for compatibility; no longer used for personas
        self.db = db
        # All personas live directly under this directory (TOML only)
        self.defaults_dir = defaults_dir
        self._builtins: dict[str, PersonaRecord] = {}

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
                except ImportError:  # pragma: no cover - very unlikely on 3.11
                    log.warning("tomllib not available, skipping TOML personas")
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
                sections: list[str] = []
                for key in ("personality_traits", "communication_style", "behavior_patterns", "core_principles", "style", "constraints", "system_prompt"):
                    sec = tdata.get(key)
                    if isinstance(sec, dict) and isinstance(sec.get("content"), str):
                        sections.append(sec["content"].strip())
                sys_prompt = "\n\n".join([s for s in sections if s]).strip()
                if not name or not sys_prompt:
                    continue
                slug = self._slug(name)
                display = disp or self._title_from_slug(slug)
                # Read optional model and temperature from TOML
                model_name = tdata.get("model")
                if model_name is not None:
                    model_name = str(model_name).strip() or None
                temperature = tdata.get("temperature")
                if temperature is not None:
                    try:
                        temperature = float(temperature)
                    except (ValueError, TypeError):
                        temperature = None
                style = tdata.get("style")
                if style is not None:
                    style = str(style).strip() or None
                model = PersonaModel(
                    name=slug,
                    display_name=display,
                    description=desc,
                    system_prompt=sys_prompt,
                    model=model_name,
                    temperature=temperature,
                    style=style,
                )
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

    async def list(self) -> list[PersonaRecord]:
        # Return all personas known from filesystem
        return [self._builtins[k] for k in sorted(self._builtins.keys())]

    async def get(self, name: str) -> PersonaRecord | None:
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
        # Validate path safety to prevent directory traversal
        self._validate_path_safe(path)
        self._write_toml_persona(path, model)
        await self.load_builtins()

    async def update(self, name: str, updates: dict[str, Any]) -> None:
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
        # Validate path safety to prevent directory traversal
        self._validate_path_safe(dest_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        self._write_toml_persona(dest_path, model)
        await self.load_builtins()

    async def delete(self, name: str) -> None:
        rec = await self.get(name)
        if not rec:
            raise ValueError(f"Persona '{name}' not found")
        try:
            if rec.path and os.path.isfile(rec.path):
                # Validate path safety even for existing paths
                self._validate_path_safe(rec.path)
                os.remove(rec.path)
            else:
                # Attempt to remove a persona file by kebab name
                path = os.path.join(self.defaults_dir, f"{self._slug(name)}.toml")
                # Validate path safety to prevent directory traversal
                self._validate_path_safe(path)
                if os.path.isfile(path):
                    os.remove(path)
        except (OSError, ValueError) as e:
            # OSError covers file not found, permission errors, etc.
            # ValueError covers path validation errors
            raise ValueError(f"Failed to delete persona file: {e}") from e
        await self.load_builtins()

    # ---------------------- Helpers ----------------------
    @staticmethod
    def _slug(name: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
        s = re.sub(r"-+", "-", s).strip("-")
        return s.lower() or "persona"

    def _validate_path_safe(self, path: str) -> None:
        """Validate that a file path is safe and within the defaults directory."""
        # Resolve absolute paths
        abs_path = os.path.abspath(path)
        abs_defaults_dir = os.path.abspath(self.defaults_dir)
        
        # Ensure the path is within defaults_dir
        try:
            # Use os.path.commonpath to check if path is within defaults_dir
            common_path = os.path.commonpath([abs_path, abs_defaults_dir])
            if common_path != abs_defaults_dir:
                raise ValueError(f"Path traversal detected: {path}")
        except ValueError as e:
            # If commonpath raises ValueError, paths are on different drives (Windows)
            # or there's an issue - reject for safety
            if "path traversal" in str(e).lower():
                raise
            raise ValueError(f"Invalid path: {path}") from e
        
        # Additional check: ensure no path separators in filename
        if os.path.sep in os.path.basename(path) or (os.path.altsep and os.path.altsep in os.path.basename(path)):
            raise ValueError(f"Invalid filename: {os.path.basename(path)}")
        
        # Ensure filename doesn't start with . or contain dangerous sequences
        basename = os.path.basename(path)
        if basename.startswith('.') or basename.startswith('..'):
            raise ValueError(f"Invalid filename: {basename}")

    @staticmethod
    def _title_from_slug(slug: str) -> str:
        parts = re.split(r"[-_\s]+", (slug or "").strip())
        return " ".join(w.capitalize() for w in parts if w)

    def _write_toml_persona(self, path: str, model: PersonaModel) -> None:
        # Minimal TOML writer that our loader can read back. We store the system prompt
        # under a [system_prompt] table with a single 'content' field.
        def esc(s: str) -> str:
            """Escape special characters for TOML double-quoted strings."""
            # Must escape backslash first, then other escapes
            result = s.replace("\\", "\\\\")
            result = result.replace("\"", "\\\"")
            result = result.replace("\n", "\\n")
            result = result.replace("\r", "\\r")
            result = result.replace("\t", "\\t")
            # Escape control characters (0x00-0x1F) except common ones already handled
            result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', lambda m: f"\\u{ord(m.group(0)):04x}", result)
            return result
        
        def esc_triple_quoted(s: str) -> str:
            """Escape content for TOML triple-quoted strings."""
            # Triple-quoted strings need to escape triple quotes
            # Also escape backslashes at end of lines to avoid interpretation issues
            result = s.replace("\\", "\\\\")
            # Escape triple quotes by inserting a newline or using escaping
            # TOML spec: if triple quote appears in triple-quoted string, escape at least one quote
            result = result.replace("\"\"\"", "\"\"\\\"")
            return result
        
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
        # Preserve newlines in triple-quoted string, but escape triple quotes
        body.append(esc_triple_quoted((model.system_prompt or "").replace("\r\n", "\n")))
        body.append("\"\"\"")
        txt = "\n".join(body) + "\n"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
        except (OSError, IOError) as e:
            # OSError covers permission errors, disk full, etc.
            # IOError is for Python < 3.3 compatibility (aliased to OSError in 3.3+)
            log.error("Failed to write persona file %s: %s", path, e)
            raise ValueError(f"Failed to write persona file: {e}") from e

    async def ai_draft_and_create(self, orc, name: str | None, outline: str) -> str:
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
