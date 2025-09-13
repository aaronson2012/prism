from __future__ import annotations

import asyncio
import logging
from typing import List
import os

from .config import load_config
from .logging import setup_logging
from .services.openrouter_client import OpenRouterClient, OpenRouterConfig
from .services.db import Database
from .services.settings import SettingsService
from .services.personas import PersonasService
from .services.memory import MemoryService, Message as MemMessage
from .services.user_learning import UserLearningService, LearningConfig
from .services.facts_backfill import FactsBackfillService
from .services.emoji_index import EmojiIndexService
from .services.reaction_engine import ReactionEngine, ReactionEngineConfig
from .services.rate_limit import RateLimiter, RateLimitConfig


log = logging.getLogger(__name__)


def build_bot(cfg):
    # Lazy import to avoid import-time failures on unsupported Python versions
    import discord  # type: ignore

    intents = discord.Intents.default()
    intents.message_content = cfg.intents_message_content
    bot = discord.Bot(intents=intents)
    return bot


def _load_base_guidelines_text() -> str:
    # Load base guidelines from personas directory if present
    try:
        import tomllib  # Python 3.11+
    except Exception:
        tomllib = None  # type: ignore
    extra_house_rules = (
        "- Avoid tagging users with @. Use names without pings.\n"
        "- Keep replies to a single message unless asked to expand."
    )
    try:
        base_path = os.path.join(os.path.dirname(__file__), "../personas/_base_guidelines.toml")
        if os.path.isfile(base_path) and tomllib:
            with open(base_path, "rb") as f:
                data = tomllib.load(f)
            content = str((data or {}).get("base_guidelines", {}).get("content") or "").strip()
            if content:
                return content + "\n" + extra_house_rules
    except Exception as e:  # noqa: BLE001
        log.debug("failed to load base guidelines: %s", e)
    # Fallback
    return (
        "You are Prism, a helpful, concise Discord AI assistant.\n"
        + extra_house_rules
    )


def register_commands(bot, orc: OpenRouterClient, cfg) -> None:
    # Lazy import of discord for decorator objects
    import discord  # type: ignore

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (%s)", bot.user, bot.user and bot.user.id)
        log.info("Message content intent: %s", getattr(bot.intents, "message_content", False))
        # Log guilds joined and configured command guilds
        try:
            gids = getattr(bot.prism_cfg, "command_guild_ids", None)  # type: ignore[attr-defined]
            if gids:
                log.info("Configured command guild IDs: %s", ",".join(str(g) for g in gids))
            joined = [(getattr(g, "name", "?"), getattr(g, "id", "?")) for g in getattr(bot, "guilds", []) or []]
            for name, gid in joined:
                in_cfg = gids and int(gid) in gids if isinstance(gid, int) else False
                log.info("Guild joined: %s (%s)%s", name, gid, " [configured]" if in_cfg else "")
        except Exception as e:  # noqa: BLE001
            log.debug("guild logging failed: %s", e)

        def _log_command_tree(prefix: str) -> None:
            try:
                cmds = getattr(bot, "application_commands", []) or []
                log.debug("%s: %d top-level commands", prefix, len(cmds))
                for c in cmds:
                    try:
                        cname = getattr(c, "name", "?")
                        ctype = c.__class__.__name__
                        cgids = getattr(c, "guild_ids", None)
                        log.debug("CMD %s (%s) guild_ids=%s", cname, ctype, cgids)
                        subs = getattr(c, "subcommands", []) or []
                        for sc in subs:
                            sname = getattr(sc, "name", "?")
                            stype = sc.__class__.__name__
                            sgids = getattr(sc, "guild_ids", None)
                            log.debug("  SUB %s (%s) guild_ids=%s", sname, stype, sgids)
                            ssubs = getattr(sc, "subcommands", []) or []
                            for s2 in ssubs:
                                s2name = getattr(s2, "name", "?")
                                s2type = s2.__class__.__name__
                                s2gids = getattr(s2, "guild_ids", None)
                                log.debug("    SUB2 %s (%s) guild_ids=%s", s2name, s2type, s2gids)
                    except Exception:
                        pass
            except Exception as _e:
                log.debug("command tree logging failed: %s", _e)
        # Fast-sync slash commands to specific guilds if configured
        try:
            _log_command_tree("Before sync")
            gids = getattr(bot.prism_cfg, "command_guild_ids", None)  # type: ignore[attr-defined]
            if gids:
                await bot.sync_commands(guild_ids=gids, force=True, method='auto')  # type: ignore[arg-type]
                try:
                    count = len(getattr(bot, "application_commands", []) or [])
                except Exception:
                    count = 0
                log.info("Synced %d commands to guilds: %s", count, ",".join(str(g) for g in gids))
                _log_command_tree("After sync")
        except Exception as e:  # noqa: BLE001
            # Log full traceback so errors are visible in errors.log
            log.exception("Guild command sync failed: %s", e)
        # Kick off emoji indexing for all guilds
        try:
            results = await bot.prism_emoji.index_all_guilds(bot)  # type: ignore[attr-defined]
            total = sum(results.values())
            log.info("Indexed custom emojis for %d guilds, %d entries", len(results), total)
            # Generate short descriptions for a few missing per guild (best-effort)
            for g in getattr(bot, "guilds", []) or []:
                try:
                    updated = await bot.prism_emoji.ensure_descriptions(orc, g.id, limit=50)  # type: ignore[attr-defined]
                    if updated:
                        log.info("Updated %d emoji descriptions for guild %s", updated, g.id)
                except Exception as e:  # noqa: BLE001
                    log.debug("ensure_descriptions failed for guild %s: %s", getattr(g, "id", "?"), e)
        except Exception as e:  # noqa: BLE001
            log.debug("Emoji indexing at ready failed: %s", e)

    @bot.event
    async def on_connect():
        log.info("Connected to Discord gateway")

    @bot.event
    async def on_disconnect():
        log.warning("Disconnected from Discord gateway")

    @bot.event
    async def on_resumed():
        log.info("Session resumed")

    @bot.event
    async def on_guild_emojis_update(guild, before, after):  # type: ignore[no-redef]
        # Refresh this guild's emoji index on changes
        try:
            n = await bot.prism_emoji.index_guild(guild)  # type: ignore[attr-defined]
            log.info("Emoji update: rescanned guild %s (%d entries)", getattr(guild, "id", "?"), n)
            # Try to fill a few missing descriptions
            _ = await bot.prism_emoji.ensure_descriptions(orc, guild.id, limit=50)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            log.debug("on_guild_emojis_update failed: %s", e)

    @bot.event
    async def on_message(message: "discord.Message"):
        # Monitor all human messages; reply only to mentions in guild text channels
        if message.author.bot or getattr(message, "webhook_id", None):
            return
        if message.guild is None:
            return
        if not bot.user:
            return
        # Persist short-term memory for all user messages
        try:
            await bot.prism_memory.add(
                MemMessage(
                    guild_id=message.guild.id,
                    channel_id=message.channel.id,
                    user_id=message.author.id,
                    role="user",
                    content=message.content or "",
                )
            )
        except Exception as e:  # noqa: BLE001
            log.debug("Failed to persist message memory: %s", e)
        # Learn user facts from all user messages (toggleable)
        if bot.prism_cfg.learning_enabled:  # type: ignore[attr-defined]
            try:
                await bot.prism_learning.learn_from_message(orc, message.guild.id, message.author.id, message.content or "")
            except Exception as e:  # noqa: BLE001
                log.debug("Learning failed: %s", e)

        # Maybe add an emoji reaction (AI-gated, rate-limited) without blocking
        if bot.prism_cfg.emoji_reactions_enabled:  # type: ignore[attr-defined]
            try:
                asyncio.create_task(bot.prism_react.maybe_react(orc, message))  # type: ignore[attr-defined]
            except Exception as e:  # noqa: BLE001
                log.debug("schedule maybe_react failed: %s", e)

        mentioned = False
        if bot.user in message.mentions:
            mentioned = True
        else:
            # Fallback: explicit mention string forms
            mid = bot.user.id
            if message.content and (f"<@{mid}>" in message.content or f"<@!{mid}>" in message.content):
                mentioned = True
        if not mentioned:
            return

        # Ensure we have permission to read the content
        if not getattr(bot.intents, "message_content", False):
            log.warning("Received mention but message_content intent is disabled; cannot read content")
            return

        # Strip the bot mention from the prompt
        content = message.content or ""
        content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
        if not content:
            content = "Hello!"
        log.info(
            "Mention detected in #%s by %s: %s",
            getattr(message.channel, 'name', message.channel.id),
            message.author.id,
            content[:120],
        )

        # Resolve persona and build messages with channel history + participant facts
        # Use per-channel lock to avoid interleaved generations
        chan_key = str(message.channel.id)
        lock = bot.prism_channel_locks.setdefault(chan_key, asyncio.Lock())  # type: ignore[attr-defined]
        async with lock:
            async def _generate_and_reply() -> None:
                persona_name = await bot.prism_settings.resolve_persona_name(message.guild.id, message.channel.id, message.author.id)
                persona = await bot.prism_personas.get(persona_name)
                if not persona:
                    persona = await bot.prism_personas.get("default")
                base_rules = _load_base_guidelines_text()
                facts_section = await build_facts_section(bot, message)
                system_prompt = base_rules + "\n\n" + (persona.data.system_prompt if persona else "")
                if facts_section:
                    system_prompt += "\n\nFacts about participants:\n" + facts_section
                # Emoji talk: provide compact candidates and style preference
                if cfg.emoji_talk_enabled:  # type: ignore[attr-defined]
                    try:
                        style = (persona.data.emoji_style if persona else None) or "balanced"
                        # If user asks for emojis, allow more candidates
                        lowered = content.lower()
                        is_emoji_request = any(w in lowered for w in ["emoji", "emojis", "custom emoji", "custom emojis"])
                        cand_limit = 8 if is_emoji_request else 6
                        cmeta = await bot.prism_emoji.suggest_with_meta_for_text(message.guild.id, content, style, limit=cand_limit)  # type: ignore[attr-defined]
                        # If indexing hasn't populated yet, fall back to guild.emojis directly
                        if not cmeta:
                            try:
                                fallback = []
                                for e in list(getattr(message.guild, "emojis", []) or [])[:cand_limit]:
                                    tok = f"<{'a' if getattr(e, 'animated', False) else ''}:{e.name}:{e.id}>"
                                    fallback.append({"token": tok, "name": e.name, "description": ""})
                                cmeta = fallback
                                if fallback:
                                    log.debug("Emoji fallback candidates from guild: %s", " ".join([m['token'] for m in fallback]))
                            except Exception:
                                pass
                        if cmeta:
                            # Avoid repeating the same custom tokens in this channel recently
                            recent_custom: set[str] = set()
                            try:
                                rows = await bot.prism_db.fetchall(
                                    "SELECT content FROM messages WHERE guild_id = ? AND channel_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 30",
                                    (str(message.guild.id), str(message.channel.id)),
                                )
                                import re as _re  # local import to avoid top-level dep
                                _tok_re = _re.compile(r"<a?:[^:>]+:\d+>")
                                for r in rows:
                                    content_row = str(r[0] or "")
                                    for m in _tok_re.findall(content_row):
                                        recent_custom.add(m)
                            except Exception as _e:
                                log.debug("recent custom tokens scan failed: %s", _e)
                            # Prefer to surface custom tokens first in casual cases
                            custom_meta = [m for m in cmeta if str(m.get("token", "")).startswith("<")]
                            # Rotation: push recently used customs to the end
                            def _recent_key(m):
                                tok = str(m.get("token") or "")
                                return 1 if tok in recent_custom else 0
                            custom_meta.sort(key=_recent_key)
                            uni_meta = [m for m in cmeta if not str(m.get("token", "")).startswith("<")]
                            if not is_emoji_request:
                                show = custom_meta[:cand_limit]
                                if len(show) < cand_limit:
                                    show += uni_meta[: cand_limit - len(show)]
                            else:
                                show = cmeta[:cand_limit]
                            cands = [m.get("token", "") for m in show if m.get("token")]
                            try:
                                log.debug(
                                    "Emoji candidates (custom=%d, unicode=%d): %s",
                                    len([1 for m in show if str(m.get('token','')).startswith('<')]),
                                    len([1 for m in show if not str(m.get('token','')).startswith('<')]),
                                    " ".join(cands),
                                )
                            except Exception:
                                pass
                            system_prompt += "\n\nEmoji style preference: " + str(style)
                            system_prompt += "\nEmoji candidates: " + " ".join(cands)
                            # Provide titles so the model knows what each token represents
                            titles = "; ".join(f"{m['token']} = {m.get('name') or 'emoji'}" for m in show)
                            if titles:
                                system_prompt += "\nEmoji titles: " + titles
                            # Provide clear usage rules so the model uses provided custom emojis
                            rules = (
                                "Emoji usage: Prefer the provided candidates; when reasonable, prefer custom server emojis over plain Unicode. For custom Discord emojis, "
                                "emit the literal token forms like <:name:id> (static) or <a:name:id> (animated); "
                                "they will render in Discord. Avoid disclaimers about not generating images; just include the emojis. "
                                "Use emojis a little more than a human would to add fun — typically 1–3 inline per normal reply; "
                                "if the user explicitly asks for emojis, include a few more (3–6); and if they ask for custom emojis, "
                                "include some of the provided custom emoji tokens."
                            )
                            system_prompt += "\n" + rules
                            # Give a concrete example using server tokens to nudge correct formatting
                            try:
                                ex_tokens = [m["token"] for m in custom_meta[:2] if m.get("token")]
                                if ex_tokens:
                                    system_prompt += "\nExample usage: That works great " + " ".join(ex_tokens)
                            except Exception:
                                pass
                            # When user explicitly asks about emojis, include short details for a few top candidates
                            if is_emoji_request:
                                details = []
                                for m in show[: min(4, len(show))]:
                                    name = m.get("name") or "emoji"
                                    desc = (m.get("description") or "").strip()
                                    if desc:
                                        details.append(f"- {name}: {desc}")
                                if details:
                                    system_prompt += "\nEmoji details:\n" + "\n".join(details)
                    except Exception as e:  # noqa: BLE001
                        log.debug("emoji suggestions failed: %s", e)

                history = await bot.prism_memory.get_recent_window(message.guild.id, message.channel.id)
                messages = [{"role": "system", "content": system_prompt}] + history + [
                    {"role": "user", "content": content}
                ]

                try:
                    chosen_model = persona.data.model or cfg.default_model if persona else cfg.default_model
                    text, _meta = await orc.chat_completion(messages, model=chosen_model)
                    reply = text.strip() if text else "(no content)"
                    # Fallback sprinkle: if emoji-talk enabled and no custom emoji used, add one top custom candidate
                    if cfg.emoji_talk_enabled:  # type: ignore[attr-defined]
                        no_emoji_requested = any(w in content.lower() for w in ["no emoji", "no emojis", "without emoji", "without emojis"])
                        if not no_emoji_requested and reply and ("<:" not in reply and "<a:" not in reply):
                            try:
                                custom_tokens = [m.get("token") for m in (locals().get("cmeta") or []) if str(m.get("token", "")).startswith("<")]
                            except Exception:
                                custom_tokens = []
                            if custom_tokens:
                                addtok = " " + custom_tokens[0]
                                if len(reply) + len(addtok) <= 1900:
                                    # Insert after first sentence-ending punctuation for a natural feel
                                    import re as _re2
                                    m = _re2.search(r"([.!?])\s", reply)
                                    if m:
                                        idx = m.end()
                                        reply = reply[:idx] + addtok + reply[idx:]
                                    else:
                                        reply = reply + addtok
                    await message.reply(reply, mention_author=False)
                    # Persist assistant reply to memory
                    await bot.prism_memory.add(MemMessage(
                        guild_id=message.guild.id,
                        channel_id=message.channel.id,
                        user_id=None,
                        role="assistant",
                        content=reply,
                    ))
                except Exception as e:  # noqa: BLE001
                    log.exception("Mention handling failed: %s", e)

            # Show typing while generating
            try:
                async with message.channel.typing():
                    await _generate_and_reply()
            except Exception:
                await _generate_and_reply()

    # No /ping command per current requirements

    # No /chat command: mention-only replies per current requirements


async def amain() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    log.info("Starting Prism bot")
    # Ensure asyncio task exceptions are logged to our handlers as well as stderr
    try:
        loop = asyncio.get_running_loop()
        def _loop_exception_handler(loop, context):  # type: ignore[no-redef]
            try:
                logger = logging.getLogger("asyncio")
                exc = context.get("exception")
                msg = context.get("message") or ""
                src = context.get("task") or context.get("future") or context.get("handle") or "loop"
                if exc is not None:
                    logger.error("Unhandled asyncio exception in %s: %s", src, msg, exc_info=exc)
                else:
                    logger.error("Unhandled asyncio error in %s: %s", src, msg)
            finally:
                try:
                    loop.default_exception_handler(context)
                except Exception:
                    pass
        loop.set_exception_handler(_loop_exception_handler)
    except Exception:
        pass

    bot = build_bot(cfg)
    db = await Database.init(cfg.db_path)
    orc = OpenRouterClient(
        OpenRouterConfig(
            api_key=cfg.openrouter_api_key,
            default_model=cfg.default_model,
            fallback_model=cfg.fallback_model,
            site_url=cfg.openrouter_site_url,
            app_name=cfg.openrouter_app_name,
        )
    )
    # Attach services to bot
    bot.prism_cfg = cfg  # type: ignore[attr-defined]
    bot.prism_db = db  # type: ignore[attr-defined]
    bot.prism_settings = SettingsService(db)  # type: ignore[attr-defined]
    bot.prism_personas = PersonasService(db, defaults_dir=os.path.join(os.path.dirname(__file__), "../personas"))  # type: ignore[attr-defined]
    await bot.prism_personas.load_builtins()  # type: ignore[attr-defined]
    bot.prism_memory = MemoryService(db)  # type: ignore[attr-defined]
    bot.prism_learning = UserLearningService(db, LearningConfig())  # type: ignore[attr-defined]
    bot.prism_emoji = EmojiIndexService(db)  # type: ignore[attr-defined]
    bot.prism_orc = orc  # type: ignore[attr-defined]
    bot.prism_backfill = FactsBackfillService(db, bot.prism_learning, backfill_model=cfg.backfill_model)  # type: ignore[attr-defined]
    # Apply backfill performance config
    try:
        bfcfg = bot.prism_backfill.cfg  # type: ignore[attr-defined]
        bfcfg.batch_size = max(1, int(getattr(cfg, 'backfill_batch_size', bfcfg.batch_size)))
        bfcfg.sleep_between_batches = float(getattr(cfg, 'backfill_sleep_between_batches', bfcfg.sleep_between_batches))
        bfcfg.channel_concurrency = max(1, int(getattr(cfg, 'backfill_channel_concurrency', bfcfg.channel_concurrency)))
        bfcfg.message_concurrency = max(1, int(getattr(cfg, 'backfill_message_concurrency', bfcfg.message_concurrency)))
    except Exception:
        pass
    # Emoji reactions engine (AI-gated)
    bot.prism_react = ReactionEngine(  # type: ignore[attr-defined]
        db=db,
        emoji_index=bot.prism_emoji,  # type: ignore[arg-type]
        rate_limiter=RateLimiter(RateLimitConfig()),
        cfg=ReactionEngineConfig(),
    )
    # Per-channel locks to avoid interleaved generations
    bot.prism_channel_locks = {}  # type: ignore[attr-defined]

    register_commands(bot, orc, cfg)
    # Load cogs
    from .cogs.personas import setup as setup_personas
    from .cogs.memory import setup as setup_memory
    from .cogs.facts import setup as setup_facts

    setup_personas(bot)
    setup_memory(bot)
    setup_facts(bot)

    try:
        log.info("Logging in to Discord...")
        await bot.start(cfg.discord_token)
    except KeyboardInterrupt:  # graceful Ctrl-C
        log.info("Received Ctrl-C, shutting down gracefully...")
        try:
            await bot.close()
        except Exception:  # noqa: BLE001
            pass
    except asyncio.CancelledError:
        log.info("Cancelled, shutting down gracefully...")
        try:
            await bot.close()
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        log.exception("Bot failed to start: %s", e)
        raise
    finally:
        # Close external resources regardless of exit path
        try:
            await orc.aclose()
        finally:
            await db.close()


async def build_facts_section(bot, message):
    # Collect distinct recent human participants from channel history
    try:
        rows = await bot.prism_db.fetchall(
            "SELECT DISTINCT user_id FROM messages WHERE guild_id = ? AND channel_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT ?",
            (str(message.guild.id), str(message.channel.id), bot.prism_learning.cfg.participant_window_messages),
        )
    except Exception as e:  # noqa: BLE001
        log.debug("Failed to fetch participants: %s", e)
        rows = []
    user_ids: List[int] = []
    seen = set()
    for r in rows:
        uid_str = r[0]
        if not uid_str:
            continue
        try:
            uid = int(uid_str)
        except Exception:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        user_ids.append(uid)
    # Ensure the author is first
    if message.author.id in seen:
        user_ids.remove(message.author.id)
    user_ids.insert(0, message.author.id)
    # Build lines
    lines: List[str] = []
    # Only include confirmed or very high-confidence items, formatted as key: value
    hi_conf = getattr(bot.prism_learning.cfg, "confirm_confidence", 0.85)
    hi_conf = 0.9 if hi_conf < 0.9 else hi_conf
    for uid in user_ids:
        member = message.guild.get_member(uid)
        name = member.display_name if member else f"User {uid}"
        facts = await bot.prism_learning.get_top_facts(message.guild.id, uid, bot.prism_learning.cfg.facts_per_user)
        if not facts:
            continue
        items: List[str] = []
        for f in facts:
            status = str(f.get("status") or "candidate")
            conf = float(f.get("confidence") or 0.0)
            if status != "confirmed" and conf < hi_conf:
                continue
            k = str(f.get("key") or "?")
            v = str(f.get("value") or "").strip()
            if not v:
                continue
            items.append(f"{k}: {v}")
        if not items:
            continue
        values = "; ".join(items)
        lines.append(f"- {name}: {values}")
    return "\n".join(lines)


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        # Redundant guard in case Ctrl-C propagates past amain(); keep output clean
        print("Interrupted — exiting cleanly.")


if __name__ == "__main__":
    main()
