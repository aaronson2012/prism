from __future__ import annotations

import logging

import discord
from discord.commands import SlashCommandGroup, option


log = logging.getLogger(__name__)


class LengthCog(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    length = SlashCommandGroup("length", "Response length settings")

    @length.command(name="set", description="Set AI response length for this guild")
    @option("length", str, description="Response length preference", required=True, choices=["concise", "balanced", "detailed"])
    async def length_set(self, ctx: discord.ApplicationContext, length: str):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await self.bot.prism_settings.set_response_length(ctx.guild.id, length)
        await ctx.respond(f"Response length set to '{length}' for this guild.")

    @length.command(name="view", description="View current AI response length setting")
    async def length_view(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        current_length = await self.bot.prism_settings.resolve_response_length(ctx.guild.id)
        await ctx.respond(f"Current response length: {current_length}")


def setup(bot: discord.Bot):
    """Setup the LengthCog and optionally scope commands to specific guilds."""
    gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
    if gids:
        try:
            LengthCog.length.guild_ids = gids  # type: ignore[attr-defined]
            for sc in getattr(LengthCog.length, "subcommands", []) or []:
                try:
                    setattr(sc, "guild_ids", gids)
                except AttributeError:
                    # Some subcommand types may not support guild_ids
                    pass
            log.info("length commands scoped to guilds: %s", ",".join(str(g) for g in gids))
        except Exception:
            log.warning("Failed to scope length commands to guilds", exc_info=True)
    bot.add_cog(LengthCog(bot))
