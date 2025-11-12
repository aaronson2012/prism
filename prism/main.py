from __future__ import annotations

import asyncio
import logging
from typing import Tuple
import os

from .config import load_config
from .logging import setup_logging
from .services.openrouter_client import OpenRouterClient, OpenRouterConfig
from .services.db import Database
from .services.settings import SettingsService
from .services.personas import PersonasService
from .services.memory import MemoryService, Message as MemMessage
from .services.emoji_index import EmojiIndexService
from .services.reaction_engine import ReactionEngine, ReactionEngineConfig
from .services.rate_limit import RateLimiter, RateLimitConfig
from .services.emoji_enforcer import fallback_add_custom_emoji, enforce_emoji_distribution
from .services.channel_locks import ChannelLockManager


log = logging.getLogger(__name__)


DISCORD_MESSAGE_LIMIT = 2000
_TRUNCATION_NOTICE = "\n(Reply truncated to fit Discord's 2000 character limit.)"


def _clip_reply_to_limit(text: str) -> Tuple[str, bool]:
    """Ensure replies respect Discord's 2000-character limit with a friendly notice."""
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return text, False

    suffix = _TRUNCATION_NOTICE
    limit = max(0, DISCORD_MESSAGE_LIMIT - len(suffix))
    truncated = text[:limit].rstrip()

    # Avoid leaving partial custom emoji tokens hanging at the end.
    partial_idx = truncated.rfind("<")
    if partial_idx != -1 and ">" not in truncated[partial_idx:]:
        truncated = truncated[:partial_idx].rstrip()

    # Close unfinished fenced code blocks if possible without exceeding the limit.
    if truncated.count("```") % 2 == 1:
        closing = "\n```"
        if len(truncated) + len(closing) <= limit:
            truncated += closing
        else:
            last_tick = truncated.rfind("```")
            if last_tick != -1:
                truncated = truncated[:last_tick].rstrip()

    result = truncated
    if not result:
        # Degenerate case: the suffix must fit alone.
        return suffix[-DISCORD_MESSAGE_LIMIT:], True

    # Ensure the final message stays within the hard cap after adjustments.
    while len(result) + len(suffix) > DISCORD_MESSAGE_LIMIT and result:
        result = result[:-1]
    result = result.rstrip()

    return result + suffix, True


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
                # Base guidelines already include global rules; avoid duplicating extras
                return content
    except Exception as e:  # noqa: BLE001
        log.debug("failed to load base guidelines: %s", e)
    # Fallback: minimal but includes global emoji rules
    fallback = (
        "Core interaction principles:\n"
        "- Be helpful, concise, and friendly.\n"
        "- Answer directly; avoid meandering filler.\n"
        "- Match the user's tone; keep responses single‑message unless asked to expand.\n"
        "- Use clear, plain language; briefly define jargon when needed.\n"
        "- State key assumptions and ask a clarifying question only when essential.\n"
        "- Avoid tagging users with @; refer to names without pings.\n"
        "- Respect user preferences and server norms.\n"
        "- Do not request or store secrets; avoid speculating about private data.\n"
        "- Stay within the conversation context; don't claim capabilities you cannot perform here.\n"
        "- If unsure, say so briefly and propose a sensible next step.\n\n"
        "Global emoji guidelines (conversation‑wide):\n"
        "- Be emoji‑eager: include at least one emoji per sentence unless the user explicitly asks for no emojis.\n"
        "- Prefer custom server emojis when available; otherwise use appropriate Unicode emojis.\n"
        "- When using custom Discord emojis, emit their literal tokens: <:name:id> for static, <a:name:id> for animated.\n"
        "- If the user asks for ‘no emoji’/‘without emoji’, comply and do not add any.\n"
        "- Don’t add disclaimers about not generating images—just include the emojis inline.\n"
        "- Keep emoji usage natural and readable; avoid overwhelming the text.\n"
        "- Spread emojis across the message; avoid clumping multiple together.\n"
        "- Do not use the same emoji more than once in a single message.\n"
        "- Avoid placing emojis back-to-back; weave them into the text near relevant phrases.\n"
    )
    return fallback + "\n" + extra_house_rules


def register_commands(bot, orc: OpenRouterClient, cfg) -> None:
    # Lazy import of discord for decorator objects
    import discord  # type: ignore

    async def _periodic_message_pruning():
        """Background task to prune old messages from database."""
        await bot.wait_until_ready()
        while not bot.is_closed():
            try:
                # Prune messages older than 30 days
                deleted = await bot.prism_memory.prune_old_messages(days=30)  # type: ignore[attr-defined]
                if deleted > 0:
                    log.info("Pruned %d old messages from database", deleted)
                # Wait 24 hours between pruning runs
                await asyncio.sleep(86400)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("Message pruning failed: %s", e, exc_info=True)

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (%s)", bot.user, bot.user and bot.user.id)
        log.info("Message content intent: %s", getattr(bot.intents, "message_content", False))
        
        # Start periodic message pruning task
        try:
            bot.loop.create_task(_periodic_message_pruning())
            log.info("Started periodic message pruning task")
        except Exception as e:
            log.warning("Failed to start message pruning task: %s", e)
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

        # Resolve persona and build messages with channel history
        # Use per-channel lock to avoid interleaved generations
        lock = bot.prism_channel_locks.get_lock(message.channel.id)  # type: ignore[attr-defined]
        async with lock:
            async def _generate_and_reply() -> None:
                persona_name = await bot.prism_settings.resolve_persona_name(message.guild.id, message.channel.id, message.author.id)
                persona = await bot.prism_personas.get(persona_name)
                if not persona:
                    persona = await bot.prism_personas.get("default")
                base_rules = _load_base_guidelines_text()
                system_prompt = base_rules + "\n\n" + (persona.data.system_prompt if persona else "")
                # Emoji talk: provide compact candidates and style preference
                if cfg.emoji_talk_enabled:  # type: ignore[attr-defined]
                    try:
                        # No per-mode styles; use global guidelines and provide candidates
                        style = None
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
                            system_prompt += "\nEmoji candidates: " + " ".join(cands)
                            # Provide titles so the model knows what each token represents
                            titles = "; ".join(f"{m['token']} = {m.get('name') or 'emoji'}" for m in show)
                            if titles:
                                system_prompt += "\nEmoji titles: " + titles
                            # Brief hint: candidates are available; custom tokens render as-is in Discord
                            system_prompt += (
                                "\nYou may use these emoji candidates directly. For custom Discord emojis, emit the token forms '<:name:id>' or '<a:name:id>' — they will render in Discord."
                            )
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
                    # Emoji enforcement: ensure at least one emoji per sentence when enabled,
                    # spread them out, and avoid duplicate emoji tokens in a single message.
                    if cfg.emoji_talk_enabled:  # type: ignore[attr-defined]
                        no_emoji_requested = any(w in content.lower() for w in ["no emoji", "no emojis", "without emoji", "without emojis"])
                        if not no_emoji_requested and reply:
                            try:
                                custom_tokens = [m.get("token") for m in (locals().get("cmeta") or []) if str(m.get("token", "")).startswith("<")]
                            except Exception:
                                custom_tokens = []
                            try:
                                unicode_tokens = [m.get("token") for m in (locals().get("cmeta") or []) if m.get("token") and not str(m.get("token")).startswith("<")]
                            except Exception:
                                unicode_tokens = []
                            
                            # If model forgot custom emojis, add at least one
                            if custom_tokens and ("<:" not in reply and "<a:" not in reply):
                                reply = fallback_add_custom_emoji(reply, custom_tokens)
                            
                            # Apply full emoji enforcement pipeline
                            reply = enforce_emoji_distribution(reply, custom_tokens, unicode_tokens)
                    original_length = len(reply)
                    reply, was_truncated = _clip_reply_to_limit(reply)
                    if was_truncated:
                        log.warning(
                            "Reply truncated for Discord limit (guild=%s channel=%s msg=%s len=%d->%d)",
                            getattr(message.guild, "id", "?"),
                            getattr(message.channel, "id", "?"),
                            getattr(message, "id", "?"),
                            original_length,
                            len(reply),
                        )

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
    # Initialize logging and console tee ASAP so early errors are captured
    try:
        setup_logging('INFO')
    except Exception:
        # Fall back silently; we'll try again after config
        pass
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
    bot.prism_emoji = EmojiIndexService(db)  # type: ignore[attr-defined]
    bot.prism_orc = orc  # type: ignore[attr-defined]
    # Emoji reactions engine (AI-gated)
    bot.prism_react = ReactionEngine(  # type: ignore[attr-defined]
        db=db,
        emoji_index=bot.prism_emoji,  # type: ignore[arg-type]
        rate_limiter=RateLimiter(RateLimitConfig()),
        cfg=ReactionEngineConfig(),
    )
    # Per-channel locks to avoid interleaved generations (with automatic cleanup)
    bot.prism_channel_locks = ChannelLockManager(cleanup_threshold_sec=3600.0)  # type: ignore[attr-defined]

    register_commands(bot, orc, cfg)
    # Load cogs
    from .cogs.personas import setup as setup_personas
    from .cogs.memory import setup as setup_memory

    setup_personas(bot)
    setup_memory(bot)

    # Install signal handlers for graceful shutdown (including SIGTERM)
    try:
        import signal
        loop = asyncio.get_running_loop()
        def _graceful_signal(sig_name: str) -> None:
            try:
                log.info("Received %s, requesting graceful shutdown...", sig_name)
                # Request bot close
                loop.create_task(bot.close())
            except Exception:
                pass
        for _sig, _name in ((signal.SIGINT, "SIGINT"), (signal.SIGTERM, "SIGTERM")):
            try:
                loop.add_signal_handler(_sig, _graceful_signal, _name)
            except Exception:
                # Not available on some platforms (e.g., Windows)
                pass
    except Exception:
        pass

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
            if not bot.is_closed():
                await bot.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await orc.aclose()
        finally:
            await db.close()


async def build_facts_section(bot, message):
    # Learning mechanism removed; no per-user facts are included.
    return ""


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        # Redundant guard in case Ctrl-C propagates past amain(); keep output clean
        print("Interrupted — exiting cleanly.")


if __name__ == "__main__":
    main()
