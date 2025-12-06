from __future__ import annotations

import logging
import re

import discord
from discord.commands import SlashCommandGroup, option
from discord.utils import basic_autocomplete

from ..services.user_preferences import VALID_EMOJI_DENSITIES, VALID_RESPONSE_LENGTHS


log = logging.getLogger(__name__)


# Valid preference names
VALID_PREFERENCE_NAMES = ["response_length", "emoji_density", "preferred_persona"]


# Static autocomplete for preference names
async def _preference_name_autocomplete(ctx: discord.AutocompleteContext):  # type: ignore[override]
    """Return valid preference names for autocomplete."""
    query = (ctx.value or "").lower()
    choices = []
    for name in VALID_PREFERENCE_NAMES:
        if query and query not in name.lower():
            continue
        choices.append(name)
    return choices


# Dynamic autocomplete for preference values based on selected preference
async def _preference_value_autocomplete(ctx: discord.AutocompleteContext):  # type: ignore[override]
    """Return valid values for the selected preference type."""
    preference = ctx.options.get("preference", "")
    query = (ctx.value or "").lower()

    if preference == "response_length":
        options = list(VALID_RESPONSE_LENGTHS)
    elif preference == "emoji_density":
        options = list(VALID_EMOJI_DENSITIES)
    elif preference == "preferred_persona":
        # Reuse persona autocomplete pattern from personas.py
        try:
            personas = await ctx.bot.prism_personas.list()  # type: ignore[attr-defined]
            choices: list[discord.OptionChoice] = []
            # Add "none" option to clear preference
            if not query or "none" in query:
                choices.append(discord.OptionChoice(name="none (clear preference)", value="none"))
            for p in personas:
                slug = p.data.name
                label = (p.data.display_name or "").strip()
                if not label:
                    parts = re.split(r"[-_\s]+", (slug or "").strip())
                    label = " ".join(w.capitalize() for w in parts if w)
                if query and query not in label.lower() and query not in slug.lower():
                    continue
                # Show description in label when space allows
                desc = (p.data.description or "").strip()
                if desc:
                    display = f"{label} -- {desc[:70]}" if len(desc) > 70 else f"{label} -- {desc}"
                else:
                    display = label
                choices.append(discord.OptionChoice(name=display, value=slug))
            return choices[:25]
        except Exception:
            return ["none"]
    else:
        # Unknown preference, return empty
        return []

    # Filter options by query
    if query:
        options = [opt for opt in options if query in opt.lower()]
    return options


class PreferencesCog(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    preferences = SlashCommandGroup("preferences", "User preference settings")

    @preferences.command(name="view", description="View your current preference settings")
    async def preferences_view(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        """Display the user's current preferences."""
        prefs = await self.bot.prism_user_prefs.get(ctx.author.id)

        response_length = prefs.get("response_length", "balanced")
        emoji_density = prefs.get("emoji_density", "normal")
        preferred_persona = prefs.get("preferred_persona")

        # Format persona display
        if preferred_persona:
            # Try to get friendly name
            rec = await self.bot.prism_personas.get(preferred_persona)
            if rec:
                friendly = (rec.data.display_name or "").strip()
                if not friendly:
                    parts = re.split(r"[-_\s]+", (preferred_persona or "").strip())
                    friendly = " ".join(w.capitalize() for w in parts if w)
                persona_display = friendly
            else:
                persona_display = preferred_persona
        else:
            persona_display = "Not set (using guild default)"

        await ctx.respond(
            f"**Your Preferences**\n"
            f"Response Length: {response_length}\n"
            f"Emoji Density: {emoji_density}\n"
            f"Preferred Persona: {persona_display}"
        )

    @preferences.command(name="set", description="Set a preference value")
    @option(
        "preference",
        str,
        description="Which preference to set",
        required=True,
        autocomplete=basic_autocomplete(_preference_name_autocomplete),
    )
    @option(
        "value",
        str,
        description="Value for the preference",
        required=True,
        autocomplete=basic_autocomplete(_preference_value_autocomplete),
    )
    async def preferences_set(self, ctx: discord.ApplicationContext, preference: str, value: str):  # type: ignore[override]
        """Set a user preference value."""
        # Validate preference name
        if preference not in VALID_PREFERENCE_NAMES:
            await ctx.respond(
                f"Invalid preference '{preference}'. Valid options: {', '.join(VALID_PREFERENCE_NAMES)}"
            )
            return

        try:
            if preference == "response_length":
                await self.bot.prism_user_prefs.set_response_length(ctx.author.id, value)
                await ctx.respond(f"Response length set to '{value}'.")

            elif preference == "emoji_density":
                await self.bot.prism_user_prefs.set_emoji_density(ctx.author.id, value)
                await ctx.respond(f"Emoji density set to '{value}'.")

            elif preference == "preferred_persona":
                # Allow "none" or empty to clear preference
                if value.lower() == "none" or value == "":
                    await self.bot.prism_user_prefs.set_preferred_persona(ctx.author.id, None)
                    await ctx.respond("Preferred persona cleared. Using guild default.")
                else:
                    # Validate persona exists
                    rec = await self.bot.prism_personas.get(value)
                    if not rec:
                        await ctx.respond(f"Persona '{value}' not found.")
                        return

                    await self.bot.prism_user_prefs.set_preferred_persona(ctx.author.id, value)

                    # Get friendly name for confirmation
                    friendly = (rec.data.display_name or "").strip()
                    if not friendly:
                        parts = re.split(r"[-_\s]+", (value or "").strip())
                        friendly = " ".join(w.capitalize() for w in parts if w)
                    await ctx.respond(f"Preferred persona set to '{friendly}'.")

        except ValueError as e:
            await ctx.respond(f"Invalid value: {e}")

    @preferences.command(name="reset", description="Reset all preferences to defaults")
    async def preferences_reset(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        """Reset all user preferences to defaults."""
        await self.bot.prism_user_prefs.reset(ctx.author.id)
        await ctx.respond("Preferences reset to defaults.")


def setup(bot: discord.Bot):
    """Setup the PreferencesCog and optionally scope commands to specific guilds."""
    gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
    if gids:
        try:
            PreferencesCog.preferences.guild_ids = gids  # type: ignore[attr-defined]
            for sc in getattr(PreferencesCog.preferences, "subcommands", []) or []:
                try:
                    setattr(sc, "guild_ids", gids)
                except AttributeError:
                    # Some subcommand types may not support guild_ids
                    pass
            log.info("preferences commands scoped to guilds: %s", ",".join(str(g) for g in gids))
        except Exception:
            log.warning("Failed to scope preferences commands to guilds", exc_info=True)
    bot.add_cog(PreferencesCog(bot))
