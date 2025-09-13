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
        # Ask the LLM via service and persist to filesystem
        try:
            created_name = await self.bot.prism_personas.ai_draft_and_create(self.bot.prism_orc, name, outline)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
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
        except Exception as e:  # noqa: BLE001
            await ctx.respond(f"Failed to edit persona: {e}")
            return
        friendly = (await self.bot.prism_personas.get(name)).data.display_name if await self.bot.prism_personas.get(name) else None  # type: ignore[attr-defined]
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
    try:
        gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
        if gids:
            try:
                PersonaCog.persona.guild_ids = gids  # type: ignore[attr-defined]
                for sc in getattr(PersonaCog.persona, "subcommands", []) or []:
                    try:
                        setattr(sc, "guild_ids", gids)
                    except Exception:
                        pass
                try:
                    log.info("persona commands scoped to guilds: %s", ",".join(str(g) for g in gids))
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass
    bot.add_cog(PersonaCog(bot))
