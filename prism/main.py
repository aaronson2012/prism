from __future__ import annotations

import asyncio
import logging
import re
import os
import socket

from .config import load_config
from .logging import setup_logging
from .services.openrouter_client import OpenRouterClient, OpenRouterConfig
from .services.db import Database
from .services.settings import SettingsService
from .services.personas import PersonasService
from .services.memory import MemoryService, Message as MemMessage
from .services.emoji_index import EmojiIndexService
from .services.emoji_enforcer import fallback_add_custom_emoji, enforce_emoji_distribution
from .services.channel_locks import ChannelLockManager
from .services.git_sync import GitSyncService, load_git_sync_config
from .services.user_preferences import UserPreferencesService


log = logging.getLogger(__name__)


DISCORD_MESSAGE_LIMIT = 2000
_CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:[^:>]+:\d+>")

# Startup retry configuration
_STARTUP_MAX_RETRIES = 5
_STARTUP_INITIAL_DELAY = 5.0  # seconds
_STARTUP_MAX_DELAY = 60.0  # seconds

# Response length guidance text mapping for system prompt injection
RESPONSE_LENGTH_GUIDANCE = {
    "concise": "Keep responses brief and direct; aim for 1-2 sentences when possible.",
    "balanced": "Provide complete answers but avoid over-explaining; use standard response length.",
    "detailed": "Give thorough, comprehensive responses with full context and explanations.",
}

# Hard token limits for response length enforcement via API
RESPONSE_LENGTH_MAX_TOKENS = {
    "concise": 150,
    "balanced": 500,
    "detailed": None,  # No limit for detailed responses
}

# Chat history configuration for context window
CHAT_HISTORY_MAX_MESSAGES = 20  # Maximum number of recent messages to include as context
CHAT_HISTORY_MAX_CHARS_PER_MESSAGE = 500  # Truncate individual history messages to this length
CHAT_HISTORY_MAX_TOTAL_CHARS = 8000  # Maximum total characters for all history content

# Emoji density guidance text mapping for system prompt injection
EMOJI_DENSITY_GUIDANCE = {
    "none": "Do not use any emojis.",
    "minimal": "Use emojis sparingly, only 1-2 per message.",
    "normal": "Use emojis naturally.",
    "lots": "Be generous with emojis, include many throughout.",
}


def _clip_reply_to_limit(text: str) -> tuple[str, bool]:
    """Ensure replies respect Discord's 2000-character limit by silently truncating if needed."""
    if not text:
        return text, False

    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return text, False

    # Truncate to the limit
    truncated = text[:DISCORD_MESSAGE_LIMIT].rstrip()

    # Avoid leaving partial custom emoji tokens hanging at the end.
    partial_idx = truncated.rfind("<")
    if partial_idx != -1 and ">" not in truncated[partial_idx:]:
        truncated = truncated[:partial_idx].rstrip()

    # Close unfinished fenced code blocks if possible without exceeding the limit.
    if truncated and truncated.count("```") % 2 == 1:
        closing = "\n```"
        if len(truncated) + len(closing) <= DISCORD_MESSAGE_LIMIT:
            truncated += closing
        else:
            # Cannot fit closing marker, remove the opening code block instead
            last_tick = truncated.rfind("```")
            if last_tick != -1:
                truncated = truncated[:last_tick].rstrip()

    # Final safety check: ensure we never exceed the limit and handle empty result
    if len(truncated) > DISCORD_MESSAGE_LIMIT:
        truncated = truncated[:DISCORD_MESSAGE_LIMIT].rstrip()

    # If truncation resulted in empty string, return a minimal message
    if not truncated:
        truncated = "(message truncated)"

    return truncated, True


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
        "- Match the user's tone; keep responses single-message unless asked to expand.\n"
        "- Use clear, plain language; briefly define jargon when needed.\n"
        "- State key assumptions and ask a clarifying question only when essential.\n"
        "- Avoid tagging users with @; refer to names without pings.\n"
        "- Respect user preferences and server norms.\n"
        "- Do not request or store secrets; avoid speculating about private data.\n"
        "- Stay within the conversation context; don't claim capabilities you cannot perform here.\n"
        "- If unsure, say so briefly and propose a sensible next step.\n"
        "- Keep all responses under 2000 characters to fit within Discord's message limit.\n\n"
        "Context and focus guidelines:\n"
        "- Your PRIMARY TASK is to respond ONLY to the user's current message below.\n"
        "- Previous conversation history is shown in the system prompt for reference context only.\n"
        "- DO NOT respond to, address, or continue topics from the conversation history unless the current message explicitly asks about them.\n"
        "- Treat the current message as a fresh, standalone request unless it clearly references the history.\n"
        "- If the current message seems unrelated to history, that's expected - respond only to what's being asked now.\n\n"
        "Global emoji guidelines (conversation-wide):\n"
        "- Be emoji-eager: include at least one emoji per sentence unless the user explicitly asks for no emojis.\n"
        "- Prefer custom server emojis when available; otherwise use appropriate Unicode emojis.\n"
        "- When using custom Discord emojis, emit their literal tokens: <:name:id> for static, <a:name:id> for animated.\n"
        "- If the user asks for 'no emoji'/'without emoji', comply and do not add any.\n"
        "- Don't add disclaimers about not generating images--just include the emojis inline.\n"
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
                    except Exception as _ce:
                        log.debug("Error logging command %s: %s", getattr(c, 'name', '?'), _ce)
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
                except Exception as _e:
                    log.debug("Failed to get command count: %s", _e)
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
                # Initialize cmeta early so it's available for emoji enforcement later
                cmeta: list[dict] = []

                # Resolve persona: check user preference first, then fall back to guild default
                user_persona = await bot.prism_user_prefs.resolve_preferred_persona(message.author.id)  # type: ignore[attr-defined]
                if user_persona is not None:
                    persona_name = user_persona
                else:
                    persona_name = await bot.prism_settings.resolve_persona_name(message.guild.id, message.channel.id, message.author.id)
                persona = await bot.prism_personas.get(persona_name)
                if not persona:
                    persona = await bot.prism_personas.get("default")

                # Resolve response length preference from user preferences
                response_length = await bot.prism_user_prefs.resolve_response_length(message.author.id)  # type: ignore[attr-defined]
                length_guidance = RESPONSE_LENGTH_GUIDANCE.get(response_length, RESPONSE_LENGTH_GUIDANCE["balanced"])
                max_tokens = RESPONSE_LENGTH_MAX_TOKENS.get(response_length)

                # Resolve emoji density preference from user preferences
                emoji_density = await bot.prism_user_prefs.resolve_emoji_density(message.author.id)  # type: ignore[attr-defined]
                density_guidance = EMOJI_DENSITY_GUIDANCE.get(emoji_density, EMOJI_DENSITY_GUIDANCE["normal"])

                base_rules = _load_base_guidelines_text()
                persona_prompt = persona.data.system_prompt if persona else ""

                # Build system prompt: base_rules + length_guidance + density_guidance + persona_prompt
                system_prompt = base_rules + "\n\n" + length_guidance + "\n\n" + density_guidance + "\n\n" + persona_prompt

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
                            except Exception as _e:
                                log.debug("Emoji fallback from guild.emojis failed: %s", _e)
                        if cmeta:
                            # Avoid repeating the same custom tokens in this channel recently
                            recent_custom: set[str] = set()
                            try:
                                rows = await bot.prism_db.fetchall(
                                    "SELECT content FROM messages WHERE guild_id = ? AND channel_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 30",
                                    (str(message.guild.id), str(message.channel.id)),
                                )
                                # Use module-level compiled regex pattern for efficiency
                                for r in rows:
                                    content_row = str(r[0] or "")
                                    for m in _CUSTOM_EMOJI_PATTERN.findall(content_row):
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
                            except Exception as _e:
                                log.debug("Emoji candidate logging failed: %s", _e)
                            system_prompt += "\nEmoji candidates: " + " ".join(cands)
                            # Provide titles so the model knows what each token represents
                            titles = "; ".join(f"{m['token']} = {m.get('name') or 'emoji'}" for m in show)
                            if titles:
                                system_prompt += "\nEmoji titles: " + titles
                            # Brief hint: candidates are available; custom tokens render as-is in Discord
                            system_prompt += (
                                "\nYou may use these emoji candidates directly. For custom Discord emojis, emit the token forms '<:name:id>' or '<a:name:id>' -- they will render in Discord."
                            )
                            # Give a concrete example using server tokens to nudge correct formatting
                            try:
                                ex_tokens = [m["token"] for m in custom_meta[:2] if m.get("token")]
                                if ex_tokens:
                                    system_prompt += "\nExample usage: That works great " + " ".join(ex_tokens)
                            except Exception as _e:
                                log.debug("Example emoji tokens generation failed: %s", _e)
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

                # Load chat history and format it as context in system prompt instead of separate messages
                # This prevents the AI from treating old messages as equally important to the current request
                history = await bot.prism_memory.get_recent_window(message.guild.id, message.channel.id, CHAT_HISTORY_MAX_MESSAGES)
                
                if history:
                    # Format history as a text block for context
                    history_lines = []
                    total_chars = 0
                    
                    for idx, msg in enumerate(history):
                        role = msg.get("role")
                        message_content = msg.get("content")
                        
                        # Log if message structure is unexpected with full context
                        if role is None or message_content is None:
                            content_preview = None
                            if message_content is not None:
                                content_str = str(message_content)
                                max_len = 200
                                content_preview = (content_str[:max_len] + "…") if len(content_str) > max_len else content_str
                            log.debug(
                                "Unexpected message structure in history (guild=%s, channel=%s, index=%d): role=%s, content_preview=%s",
                                message.guild.id,
                                message.channel.id,
                                idx,
                                role,
                                content_preview,
                            )
                            continue
                        
                        if role == "user":
                            prefix = "User: "
                        elif role == "assistant":
                            prefix = "Assistant: "
                        else:
                            # Skip system messages and other roles - they shouldn't be in user-facing history
                            log.debug(
                                "Skipping message with unhandled role in history (guild=%s, channel=%s, index=%d): %s",
                                message.guild.id,
                                message.channel.id,
                                idx,
                                role,
                            )
                            continue
                        
                        # Sanitize content to prevent breaking the history framing structure
                        # Replace potential delimiters and problematic patterns
                        sanitized_content = str(message_content)
                        # Escape triple dashes that could be confused with our delimiter
                        sanitized_content = sanitized_content.replace("---", "–––")
                        # Escape role prefixes that could confuse parsing
                        sanitized_content = sanitized_content.replace("\nUser: ", "\nUser - ")
                        sanitized_content = sanitized_content.replace("\nAssistant: ", "\nAssistant - ")
                        
                        # Truncate individual messages to avoid consuming too much context
                        if len(sanitized_content) > CHAT_HISTORY_MAX_CHARS_PER_MESSAGE:
                            sanitized_content = sanitized_content[:CHAT_HISTORY_MAX_CHARS_PER_MESSAGE] + "…"
                        
                        formatted_line = prefix + sanitized_content
                        
                        # Check if adding this message would exceed total character limit
                        if total_chars + len(formatted_line) > CHAT_HISTORY_MAX_TOTAL_CHARS:
                            log.debug(
                                "Truncating history at message %d (guild=%s, channel=%s): would exceed max total chars (%d)",
                                idx,
                                message.guild.id,
                                message.channel.id,
                                CHAT_HISTORY_MAX_TOTAL_CHARS,
                            )
                            break
                        
                        history_lines.append(formatted_line)
                        total_chars += len(formatted_line)
                    
                    if history_lines:
                        history_context = "\n".join(history_lines)
                        # Add history as context in system prompt with clear framing
                        system_prompt += (
                            f"\n\nRecent conversation history (for context only - do NOT respond to these old messages):\n"
                            f"---\n{history_context}\n---\n"
                            f"End of conversation history. The user's CURRENT request follows below."
                        )
                
                # Build messages array with only system prompt and current user message
                # This structurally enforces that the current message is the primary task
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ]

                try:
                    chosen_model = persona.data.model or cfg.default_model if persona else cfg.default_model
                    text, _meta = await orc.chat_completion(messages, model=chosen_model, max_tokens=max_tokens)
                    reply = text.strip() if text else "(no content)"
                    # Emoji enforcement: ensure at least one emoji per sentence when enabled,
                    # spread them out, and avoid duplicate emoji tokens in a single message.
                    # Skip emoji enforcement entirely when user density is "none"
                    if cfg.emoji_talk_enabled and emoji_density != "none":  # type: ignore[attr-defined]
                        no_emoji_requested = any(w in content.lower() for w in ["no emoji", "no emojis", "without emoji", "without emojis"])
                        if not no_emoji_requested and reply:
                            custom_tokens = [m.get("token") for m in cmeta if str(m.get("token", "")).startswith("<")]
                            unicode_tokens = [m.get("token") for m in cmeta if m.get("token") and not str(m.get("token")).startswith("<")]

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
            except Exception as _e:
                log.debug("Typing indicator failed, generating reply without it: %s", _e)
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
    bot.prism_user_prefs = UserPreferencesService(db)  # type: ignore[attr-defined]

    # Initialize git sync for personas if configured
    personas_dir = os.path.join(os.path.dirname(__file__), "../personas")
    git_sync_config = load_git_sync_config()
    git_sync: GitSyncService | None = None
    if git_sync_config.enabled:
        git_sync = GitSyncService(git_sync_config, personas_dir)
        if await git_sync.initialize():
            log.info("Git sync for personas initialized")
        else:
            log.warning("Git sync initialization failed, continuing without sync")
            git_sync = None

    bot.prism_personas = PersonasService(db, defaults_dir=personas_dir, git_sync=git_sync)  # type: ignore[attr-defined]
    await bot.prism_personas.load_builtins()  # type: ignore[attr-defined]
    bot.prism_memory = MemoryService(db)  # type: ignore[attr-defined]
    bot.prism_emoji = EmojiIndexService(db)  # type: ignore[attr-defined]
    bot.prism_orc = orc  # type: ignore[attr-defined]
    # Per-channel locks to avoid interleaved generations (with automatic cleanup)
    bot.prism_channel_locks = ChannelLockManager(cleanup_threshold_sec=3600.0)  # type: ignore[attr-defined]
    # Active duels storage (keyed by channel_id)
    bot.prism_active_duels = {}  # type: ignore[attr-defined]

    register_commands(bot, orc, cfg)
    # Load cogs
    from .cogs.personas import setup as setup_personas
    from .cogs.memory import setup as setup_memory
    from .cogs.preferences import setup as setup_preferences
    from .cogs.duel import setup as setup_duel

    setup_personas(bot)
    setup_memory(bot)
    setup_preferences(bot)
    setup_duel(bot)

    # Install signal handlers for graceful shutdown (including SIGTERM)
    shutdown_requested = False
    try:
        import signal
        loop = asyncio.get_running_loop()
        def _graceful_signal(sig_name: str) -> None:
            nonlocal shutdown_requested
            if shutdown_requested:
                return  # Prevent double-handling
            shutdown_requested = True
            try:
                log.info("Received %s, requesting graceful shutdown...", sig_name)
                # Request bot close - the finally block will handle the rest
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

    # Startup with retry logic for transient network errors
    retry_count = 0
    delay = _STARTUP_INITIAL_DELAY
    try:
        while True:
            try:
                log.info("Logging in to Discord...")
                await bot.start(cfg.discord_token)
                break  # Clean exit (bot.close() was called)
            except KeyboardInterrupt:  # graceful Ctrl-C
                log.info("Received Ctrl-C, shutting down gracefully...")
                # Don't close here - let the finally block handle it
                break
            except asyncio.CancelledError:
                log.info("Cancelled, shutting down gracefully...")
                # Don't close here - let the finally block handle it
                break
            except (socket.gaierror, OSError) as e:
                # Network/DNS errors - retry with backoff
                retry_count += 1
                if retry_count > _STARTUP_MAX_RETRIES:
                    log.error("Bot failed to start after %d retries: %s", _STARTUP_MAX_RETRIES, e)
                    raise
                log.warning("Network error during startup (attempt %d/%d): %s. Retrying in %.1f seconds...",
                           retry_count, _STARTUP_MAX_RETRIES, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, _STARTUP_MAX_DELAY)  # Exponential backoff with cap
            except Exception as e:  # noqa: BLE001
                # Check if it's a wrapped network error (aiohttp wraps socket errors)
                if "Temporary failure in name resolution" in str(e) or "getaddrinfo failed" in str(e):
                    retry_count += 1
                    if retry_count > _STARTUP_MAX_RETRIES:
                        log.error("Bot failed to start after %d retries: %s", _STARTUP_MAX_RETRIES, e)
                        raise
                    log.warning("Network error during startup (attempt %d/%d): %s. Retrying in %.1f seconds...",
                               retry_count, _STARTUP_MAX_RETRIES, e, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _STARTUP_MAX_DELAY)
                else:
                    log.exception("Bot failed to start: %s", e)
                    raise
    finally:
        # Close external resources regardless of exit path
        try:
            if not bot.is_closed():
                await bot.close()
            # Give aiohttp time to finish cleanup tasks to avoid "Unclosed client session" warnings
            # This needs to happen even if bot was already closed to let background tasks complete
            await asyncio.sleep(0.5)
        except Exception:  # noqa: BLE001
            pass
        try:
            await orc.aclose()
        finally:
            await db.close()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        # Redundant guard in case Ctrl-C propagates past amain(); keep output clean
        print("Interrupted -- exiting cleanly.")


if __name__ == "__main__":
    main()
