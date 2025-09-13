from __future__ import annotations

import logging
from typing import Optional

import discord
from discord.commands import SlashCommandGroup, option


log = logging.getLogger(__name__)


class FactsCog(discord.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot

    facts = SlashCommandGroup("facts", "User facts commands")
    backfill = facts.create_subgroup("backfill", "Backfill facts from guild history")

    @facts.command(name="view", description="View learned facts for a user")
    @option("user", discord.Member, description="User to view", required=False, default=None)
    @option("limit", int, description="Max facts to show", required=False, default=10, min_value=1)
    async def facts_view(self, ctx: discord.ApplicationContext, user: Optional[discord.Member] = None, limit: int = 10):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        target = user or ctx.author
        facts = await self.bot.prism_learning.get_top_facts(ctx.guild.id, target.id, limit)
        if not facts:
            await ctx.respond(f"No facts stored for {target.display_name}.")
            return
        lines = [f"Facts for {target.display_name}:"]
        for f in facts:
            key = f.get('key') or '?'
            val = f.get('value') or ''
            conf = float(f.get('confidence') or 0.0)
            support = int(f.get('support') or 1)
            lines.append(f"- {key}: {val} (conf {conf:.2f}, support {support})")
        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1897] + "..."
        await ctx.respond(text)

    @facts.command(name="clear", description="Clear learned facts for a user")
    @option("user", discord.Member, description="User to clear", required=True)
    @option("key", str, description="Specific key to clear", required=False, default=None)
    async def facts_clear(self, ctx: discord.ApplicationContext, user: discord.Member, key: Optional[str] = None):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        await self.bot.prism_learning.clear_facts(ctx.guild.id, user.id, key)
        who = user.display_name
        what = f" key '{key}'" if key else " all"
        await ctx.respond(f"Cleared{what} facts for {who}.")

    # ---------------- Backfill controls ----------------
    @backfill.command(name="start", description="Start backfilling facts across all channels (slow, background)")
    async def backfill_start(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        try:
            await self.bot.prism_backfill.start_guild(self.bot, self.bot.prism_orc, ctx.guild.id)  # type: ignore[attr-defined]
            await ctx.respond("Guild-wide backfill started (runs in background).")
        except Exception as e:  # noqa: BLE001
            await ctx.respond(f"Failed to start backfill: {e}")

    @backfill.command(name="status", description="Show guild-wide backfill status")
    async def backfill_status(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        st = await self.bot.prism_backfill.get_guild_status(self.bot, ctx.guild.id)  # type: ignore[attr-defined]
        msg = (
            f"Backfill status: {st.get('status')} — "
            f"channels {st.get('channels_completed', 0)}/{st.get('channels_total', 0)} completed, "
            f"{st.get('channels_running', 0)} running, {st.get('channels_pending', 0)} pending — "
            f"processed {st.get('processed_total', 0)} messages."
        )
        await ctx.respond(msg)

    @backfill.command(name="stop", description="Stop guild-wide backfill")
    async def backfill_stop(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        if not ctx.guild:
            await ctx.respond("This command must be used in a guild.")
            return
        await ctx.defer(ephemeral=False)
        try:
            await self.bot.prism_backfill.stop_guild(ctx.guild.id)  # type: ignore[attr-defined]
            await ctx.respond("Guild-wide backfill stop requested.")
        except Exception as e:  # noqa: BLE001
            await ctx.respond(f"Failed to stop backfill: {e}")


def setup(bot: discord.Bot):
    # If fast guild sync is configured, scope this group's commands to those guilds
    try:
        gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
        if gids:
            def _apply_gids(group):
                try:
                    group.guild_ids = gids  # type: ignore[attr-defined]
                    for sc in getattr(group, "subcommands", []) or []:
                        # sc may be a SlashCommand or SlashCommandGroup
                        try:
                            setattr(sc, "guild_ids", gids)
                            # recurse if subgroup
                            for s2 in getattr(sc, "subcommands", []) or []:
                                setattr(s2, "guild_ids", gids)
                        except Exception:
                            pass
                except Exception:
                    pass
            _apply_gids(FactsCog.facts)
            _apply_gids(FactsCog.backfill)
            try:
                log.info("facts commands scoped to guilds: %s", ",".join(str(g) for g in gids))
            except Exception:
                pass
    except Exception:
        pass
    bot.add_cog(FactsCog(bot))
