from __future__ import annotations

import logging
import re

import discord
from discord.commands import SlashCommandGroup, option
from discord.utils import basic_autocomplete



log = logging.getLogger(__name__)


class PersonaCog(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    persona = SlashCommandGroup("persona", "Persona management commands")

    # Dynamic autocomplete for persona names
    @staticmethod
    async def _persona_name_autocomplete(ctx: discord.AutocompleteContext):  # type: ignore[override]
        try:
            personas = await ctx.bot.prism_personas.list()  # type: ignore[attr-defined]
            query = (ctx.value or "").lower()
            choices: list[discord.OptionChoice] = []
            for p in personas:
                slug = p.data.name
                label = (p.data.display_name or "").strip()
                if not label:
                    parts = re.split(r"[-_\s]+", (slug or "").strip())
                    label = " ".join(w.capitalize() for w in parts if w)
                if query and query not in label.lower():
                    continue
                # Show description in label when space allows
                desc = (p.data.description or "").strip()
                if desc:
                    display = f"{label} — {desc[:70]}" if len(desc) > 70 else f"{label} — {desc}"
                else:
                    display = label
                choices.append(discord.OptionChoice(name=display, value=slug))
            return choices[:25]
        except Exception:
            return []

    @persona.command(name="info", description="Show persona details")
    @option("name", str, description="Persona name", required=True, autocomplete=basic_autocomplete(_persona_name_autocomplete))
    async def persona_info(self, ctx: discord.ApplicationContext, name: str):  # type: ignore[override]
        await ctx.defer(ephemeral=False)
        rec = await self.bot.prism_personas.get(name)
        if not rec:
            await ctx.respond(f"Persona '{name}' not found.")
            return
        data = rec.data
        # Present a friendly display name (display_name or Title Case from slug)
        friendly = (data.display_name or "").strip()
        if not friendly:
            parts = re.split(r"[-_\s]+", (data.name or "").strip())
            friendly = " ".join(w.capitalize() for w in parts if w)
        desc = data.description or "(no description)"
        model = data.model or self.bot.prism_cfg.default_model
        temp = data.temperature if data.temperature is not None else "default"
        await ctx.respond(
            f"Name: {friendly}\nStyle: {data.style or 'default'}\nModel: {model}\nTemperature: {temp}\nDescription: {desc}"
        )

    @persona.command(name="set", description="Set the active persona for this guild")
    @option("name", str, description="Persona name", required=True, autocomplete=basic_autocomplete(_persona_name_autocomplete))
    async def persona_set(self, ctx: discord.ApplicationContext, name: str):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return

        # Reload personas so we have the latest set persona in cache.
        await self.bot.prism_personas.load_builtins()
        
        rec = await self.bot.prism_personas.get(name)
        if not rec:
            await ctx.respond(f"Persona '{name}' not found.")
            return
        await self.bot.prism_settings.set_persona(ctx.guild.id, "guild", None, rec.data.name)
        # Friendly confirmation name
        friendly = (rec.data.display_name or "").strip()
        if not friendly:
            parts = re.split(r"[-_\s]+", (rec.data.name or "").strip())
            friendly = " ".join(w.capitalize() for w in parts if w)
        await ctx.respond(f"Persona set to '{friendly}' for this guild.")

    @persona.command(name="create", description="Create a new persona (AI-assisted)")
    # Discord requires required options to be listed before optional ones
    @option("outline", str, description="Describe the personality in a few words/sentences", required=True)
    @option("name", str, description="Name (optional)", required=False, default=None)
    async def persona_create(
        self,
        ctx: discord.ApplicationContext,  # type: ignore[override]
        outline: str,
        name: str | None = None,
    ):
        await ctx.defer(ephemeral=False)
        # Validate input
        if not outline or not outline.strip():
            await ctx.respond("Outline cannot be empty.")
            return
        if len(outline) > 2000:
            await ctx.respond("Outline is too long (max 2000 characters).")
            return
        if name and len(name) > 100:
            await ctx.respond("Persona name is too long (max 100 characters).")
            return
        # Ask the LLM via service and persist to filesystem
        try:
            created_name = await self.bot.prism_personas.ai_draft_and_create(self.bot.prism_orc, name, outline)  # type: ignore[attr-defined]
        except ValueError as e:
            await ctx.respond(f"Failed to create persona: {e}")
            return
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected error creating persona")
            await ctx.respond(f"Failed to create persona: {e}")
            return
        # Present friendly name
        # We don't reload here; derive from slug
        parts = re.split(r"[-_\s]+", (created_name or "").strip())
        friendly = " ".join(w.capitalize() for w in parts if w)
        await ctx.respond(f"Persona '{friendly}' created from outline.")

    @persona.command(name="edit", description="Edit a persona (filesystem)")
    @option("name", str, description="Persona name", required=True)
    @option("display_name", str, description="Friendly display name", required=False, default=None)
    @option("system_prompt", str, description="New system prompt", required=False, default=None)
    @option("description", str, description="New description", required=False, default=None)
    @option("model", str, description="Model override", required=False, default=None)
    @option("temperature", float, description="Temperature", required=False, default=None)
    @option("style", str, description="Style tag", required=False, default=None)
    async def persona_edit(
        self,
        ctx: discord.ApplicationContext,  # type: ignore[override]
        name: str,
        display_name: str | None = None,
        system_prompt: str | None = None,
        description: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        style: str | None = None,
    ):
        await ctx.defer(ephemeral=False)
        # Validate input
        if display_name and len(display_name) > 200:
            await ctx.respond("Display name is too long (max 200 characters).")
            return
        if system_prompt and len(system_prompt) > 10000:
            await ctx.respond("System prompt is too long (max 10000 characters).")
            return
        if description and len(description) > 500:
            await ctx.respond("Description is too long (max 500 characters).")
            return
        if model and len(model) > 200:
            await ctx.respond("Model name is too long (max 200 characters).")
            return
        if temperature is not None and (temperature < 0 or temperature > 2):
            await ctx.respond("Temperature must be between 0 and 2.")
            return
        if style and len(style) > 100:
            await ctx.respond("Style tag is too long (max 100 characters).")
            return
        try:
            updates = {
                "display_name": display_name,
                "system_prompt": system_prompt,
                "description": description,
                "model": model,
                "temperature": temperature,
                "style": style,
            }
            updates = {k: v for k, v in updates.items() if v is not None}
            if not updates:
                await ctx.respond("No changes provided.")
                return
            await self.bot.prism_personas.update(name, updates)
        except ValueError as e:
            await ctx.respond(f"Failed to edit persona: {e}")
            return
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected error editing persona")
            await ctx.respond(f"Failed to edit persona: {e}")
            return
        rec = await self.bot.prism_personas.get(name)
        friendly = None
        if rec is not None:
            friendly = (rec.data.display_name or "").strip()
        if not friendly:
            parts = re.split(r"[-_\s]+", (name or "").strip())
            friendly = " ".join(w.capitalize() for w in parts if w)
        await ctx.respond(f"Persona '{friendly}' updated.")

    @persona.command(name="delete", description="Delete a persona (filesystem)")
    @option("name", str, description="Persona name", required=True)
    async def persona_delete(self, ctx: discord.ApplicationContext, name: str):  # type: ignore[override]
        await ctx.defer(ephemeral=False)
        try:
            await self.bot.prism_personas.delete(name)
        except Exception as e:  # noqa: BLE001
            await ctx.respond(f"Failed to delete persona: {e}")
            return
        parts = re.split(r"[-_\s]+", (name or "").strip())
        friendly = " ".join(w.capitalize() for w in parts if w)
        await ctx.respond(f"Persona '{friendly}' deleted.")


def setup(bot: discord.Bot):
    """Setup the PersonaCog and optionally scope commands to specific guilds."""
    gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
    if gids:
        try:
            PersonaCog.persona.guild_ids = gids  # type: ignore[attr-defined]
            for sc in getattr(PersonaCog.persona, "subcommands", []) or []:
                try:
                    setattr(sc, "guild_ids", gids)
                except AttributeError:
                    # Some subcommand types may not support guild_ids
                    pass
            log.info("persona commands scoped to guilds: %s", ",".join(str(g) for g in gids))
        except Exception:
            log.warning("Failed to scope persona commands to guilds", exc_info=True)
    bot.add_cog(PersonaCog(bot))
