from __future__ import annotations

import logging

import discord
from discord.commands import SlashCommandGroup, option


log = logging.getLogger(__name__)


class MemoryCog(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    memory = SlashCommandGroup("memory", "Short-term memory commands")

    @memory.command(name="view", description="View recent short-term memory for this channel")
    @option("limit", int, description="Max messages to show", required=False, default=10, min_value=1, max_value=100)
    async def memory_view(self, ctx: discord.ApplicationContext, limit: int = 10):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        # Fetch a window then trim to requested limit for display
        history = await self.bot.prism_memory.get_recent_window(ctx.guild.id, ctx.channel_id, budget_tokens=10_000, max_messages=200)
        # Show only last N
        to_show = history[-limit:] if limit and limit > 0 else history
        if not to_show:
            await ctx.respond("No memory stored for this channel yet.")
            return
        # Build a compact view under Discord 2000-char limit
        lines: list[str] = []
        for m in to_show:
            role = m.get("role", "?")
            content = (m.get("content", "") or "").strip()
            if len(content) > 180:
                content = content[:177] + "..."
            lines.append(f"- {role}: {content}")
        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1897] + "..."
        await ctx.respond(text)

    @memory.command(name="clear", description="Clear short-term memory for this channel")
    async def memory_clear(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        await self.bot.prism_memory.clear_channel(ctx.guild.id, ctx.channel_id)
        await ctx.respond("Cleared short-term memory for this channel.")


def setup(bot: discord.Bot):
    try:
        gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
        if gids:
            try:
                MemoryCog.memory.guild_ids = gids  # type: ignore[attr-defined]
                for sc in getattr(MemoryCog.memory, "subcommands", []) or []:
                    try:
                        setattr(sc, "guild_ids", gids)
                    except Exception:
                        pass
                try:
                    log.info("memory commands scoped to guilds: %s", ",".join(str(g) for g in gids))
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass
    bot.add_cog(MemoryCog(bot))
