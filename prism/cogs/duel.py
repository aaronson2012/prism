"""Duel cog for persona duels slash commands."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any

import discord
from discord.commands import SlashCommandGroup, option
from discord.utils import basic_autocomplete

from prism.models.duel import (
    DuelMode,
    DuelState,
    JUDGE_SYSTEM_PROMPT,
    calculate_typing_delay,
    format_judge_response,
)

log = logging.getLogger(__name__)

# Default Unicode emojis to use as fallback when no custom emojis are available
DEFAULT_UNICODE_EMOJIS = [
    "fire",
    "star",
    "sparkles",
    "zap",
    "boom",
    "bulb",
    "muscle",
    "brain",
    "eyes",
    "clap",
]

# Discord message character limit
DISCORD_MESSAGE_LIMIT = 2000

# Max tokens for duel responses (keeps them short and conversational)
DUEL_MAX_TOKENS = 250


def _clip_to_discord_limit(text: str, max_len: int = DISCORD_MESSAGE_LIMIT) -> str:
    """Truncate text to fit within Discord's message limit.

    Args:
        text: The text to truncate.
        max_len: Maximum length allowed.

    Returns:
        The truncated text, with ellipsis if truncated.
    """
    if len(text) <= max_len:
        return text

    # Leave room for ellipsis
    truncated = text[: max_len - 3].rstrip()

    # Avoid leaving partial custom emoji tokens
    partial_idx = truncated.rfind("<")
    if partial_idx != -1 and ">" not in truncated[partial_idx:]:
        truncated = truncated[:partial_idx].rstrip()

    return truncated + "..."


async def simulate_typing(channel: discord.abc.Messageable, message: str) -> None:
    """Simulate typing in a channel before sending a message.

    Shows the typing indicator for a duration proportional to the message length,
    providing visual feedback that a response is being prepared.

    Args:
        channel: The Discord channel to show typing indicator in.
        message: The message that will be sent (used to calculate delay).
    """
    delay = calculate_typing_delay(message)
    try:
        async with channel.typing():
            await asyncio.sleep(delay)
    except Exception as e:
        # If typing indicator fails, log and continue without it
        log.debug("Typing indicator failed, continuing without it: %s", e)


class DuelCog(discord.Cog):
    """Cog for managing persona duels."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    duel = SlashCommandGroup("duel", "Persona duel commands")

    # Dynamic autocomplete for persona names (reuses pattern from PersonaCog)
    @staticmethod
    async def _persona_name_autocomplete(ctx: discord.AutocompleteContext):  # type: ignore[override]
        """Autocomplete for persona names."""
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
                    display = f"{label} -- {desc[:70]}" if len(desc) > 70 else f"{label} -- {desc}"
                else:
                    display = label
                choices.append(discord.OptionChoice(name=display, value=slug))
            return choices[:25]
        except Exception:
            return []

    @duel.command(name="start", description="Start a duel between two personas")
    @option(
        "persona1",
        str,
        description="First persona",
        required=True,
        autocomplete=basic_autocomplete(_persona_name_autocomplete),
    )
    @option(
        "persona2",
        str,
        description="Second persona",
        required=True,
        autocomplete=basic_autocomplete(_persona_name_autocomplete),
    )
    @option("topic", str, description="The debate topic", required=True)
    @option(
        "mode",
        str,
        description="Duel mode",
        required=False,
        default="rounds",
        choices=["rounds", "time"],
    )
    @option(
        "duration",
        int,
        description="Number of rounds (1-10) or minutes (1-5) depending on mode",
        required=False,
        default=None,
    )
    async def duel_start(
        self,
        ctx: discord.ApplicationContext,  # type: ignore[override]
        persona1: str,
        persona2: str,
        topic: str,
        mode: str = "rounds",
        duration: int | None = None,
    ):
        """Start a duel between two personas on a given topic."""
        await ctx.defer(ephemeral=False)

        channel_id = ctx.channel.id

        # Check for active duel in channel
        if channel_id in self.bot.prism_active_duels:  # type: ignore[attr-defined]
            await ctx.respond("A duel is already active in this channel. Use `/duel stop` to cancel it first.")
            return

        # Validate personas are different
        if persona1 == persona2:
            await ctx.respond("You cannot start a duel between the same persona. Please select two different personas.")
            return

        # Validate both personas exist
        rec1 = await self.bot.prism_personas.get(persona1)  # type: ignore[attr-defined]
        rec2 = await self.bot.prism_personas.get(persona2)  # type: ignore[attr-defined]

        if rec1 is None:
            await ctx.respond(f"Persona '{persona1}' not found.")
            return
        if rec2 is None:
            await ctx.respond(f"Persona '{persona2}' not found.")
            return

        # Determine mode and duration
        duel_mode = DuelMode.ROUNDS if mode == "rounds" else DuelMode.TIME

        if duration is None:
            # Use defaults
            if duel_mode == DuelMode.ROUNDS:
                duration = DuelMode.default_rounds()
            else:
                duration = DuelMode.default_time() // 60  # Convert seconds to minutes for user input

        # Validate and convert duration
        if duel_mode == DuelMode.ROUNDS:
            if duration < 1 or duration > DuelMode.max_rounds():
                await ctx.respond(f"For rounds mode, duration must be between 1 and {DuelMode.max_rounds()} rounds.")
                return
            duration_value = duration
        else:
            # Time mode: duration is in minutes, convert to seconds
            max_minutes = DuelMode.max_time() // 60
            if duration < 1 or duration > max_minutes:
                await ctx.respond(f"For time mode, duration must be between 1 and {max_minutes} minutes.")
                return
            duration_value = duration * 60  # Convert to seconds

        # Create duel state
        duel_state = DuelState(
            channel_id=channel_id,
            persona1=persona1,
            persona2=persona2,
            topic=topic,
            mode=duel_mode,
            duration=duration_value,
        )

        # Store in active duels
        self.bot.prism_active_duels[channel_id] = duel_state  # type: ignore[attr-defined]

        # Get friendly display names
        p1_display = (rec1.data.display_name or "").strip()
        if not p1_display:
            parts = re.split(r"[-_\s]+", (persona1 or "").strip())
            p1_display = " ".join(w.capitalize() for w in parts if w)

        p2_display = (rec2.data.display_name or "").strip()
        if not p2_display:
            parts = re.split(r"[-_\s]+", (persona2 or "").strip())
            p2_display = " ".join(w.capitalize() for w in parts if w)

        # Build announcement message
        if duel_mode == DuelMode.ROUNDS:
            duration_text = f"{duration_value} rounds"
        else:
            minutes = duration_value // 60
            duration_text = f"{minutes} minute{'s' if minutes != 1 else ''}"

        announcement = (
            f"**DUEL STARTING!**\n\n"
            f"**{p1_display}** vs **{p2_display}**\n\n"
            f"**Topic:** {topic}\n"
            f"**Mode:** {mode.capitalize()} ({duration_text})\n\n"
            f"Let the debate begin!"
        )

        await ctx.respond(announcement)

        # Start the duel loop in the background
        asyncio.create_task(self._run_duel(ctx.channel, duel_state))

    @duel.command(name="stop", description="Stop the active duel in this channel")
    async def duel_stop(self, ctx: discord.ApplicationContext):  # type: ignore[override]
        """Stop the active duel in the current channel."""
        await ctx.defer(ephemeral=False)

        channel_id = ctx.channel.id

        # Check for active duel in channel
        if channel_id not in self.bot.prism_active_duels:  # type: ignore[attr-defined]
            await ctx.respond("There is no active duel in this channel.")
            return

        # Get duel state for message
        duel_state = self.bot.prism_active_duels[channel_id]  # type: ignore[attr-defined]

        # Remove duel from active duels (cleanup)
        del self.bot.prism_active_duels[channel_id]  # type: ignore[attr-defined]
        log.info(
            "Duel cancelled via /duel stop in channel %s: %s vs %s on '%s'",
            channel_id, duel_state.persona1, duel_state.persona2, duel_state.topic
        )

        # Post cancellation message
        await ctx.respond(
            f"**Duel Cancelled**\n\n"
            f"The duel between **{duel_state.persona1}** and **{duel_state.persona2}** "
            f"on the topic of \"{duel_state.topic}\" has been cancelled.\n"
            f"No judgment will be rendered."
        )

    def _cleanup_duel(self, duel_state: DuelState, reason: str = "completed") -> None:
        """Clean up duel state from active duels dictionary.

        This method safely removes the duel from active duels, handling the case
        where it may have already been removed (e.g., by /duel stop).

        Args:
            duel_state: The duel state to clean up.
            reason: Reason for cleanup (for logging).
        """
        channel_id = duel_state.channel_id
        if channel_id in self.bot.prism_active_duels:  # type: ignore[attr-defined]
            del self.bot.prism_active_duels[channel_id]  # type: ignore[attr-defined]
            log.info(
                "Duel cleanup (%s) in channel %s: %s vs %s on '%s'",
                reason, channel_id, duel_state.persona1, duel_state.persona2, duel_state.topic
            )

    async def _run_duel(self, channel: discord.abc.Messageable, duel_state: DuelState) -> None:
        """Run the duel loop based on mode.

        This method orchestrates the entire duel execution, including error handling
        and cleanup. It ensures the duel state is always cleaned up regardless of
        how the duel ends (completion, cancellation, or error).

        Args:
            channel: The Discord channel where the duel is taking place.
            duel_state: The current duel state.
        """
        try:
            if duel_state.mode == DuelMode.ROUNDS:
                await self._run_rounds_mode(channel, duel_state)
            else:
                await self._run_time_mode(channel, duel_state)

            # After duel completes, invoke the judge (if not cancelled)
            if duel_state.channel_id in self.bot.prism_active_duels:  # type: ignore[attr-defined]
                await self._invoke_judge(channel, duel_state)

        except discord.NotFound as e:
            # Channel or message was deleted
            log.warning(
                "Duel interrupted - channel/message not found (channel=%s): %s",
                duel_state.channel_id, e
            )
            self._cleanup_duel(duel_state, reason="channel_deleted")

        except discord.Forbidden as e:
            # Bot lost permissions
            log.warning(
                "Duel interrupted - permission denied (channel=%s): %s",
                duel_state.channel_id, e
            )
            self._cleanup_duel(duel_state, reason="permission_denied")
            # Try to notify, but don't fail if we can't
            try:
                await channel.send(
                    "**Duel Interrupted**\n\n"
                    "The duel has been cancelled due to missing permissions. "
                    "Please ensure the bot has permission to send messages and add reactions."
                )
            except Exception:
                pass

        except discord.HTTPException as e:
            # Generic Discord API error
            log.error(
                "Duel interrupted - Discord API error (channel=%s): %s",
                duel_state.channel_id, e, exc_info=True
            )
            self._cleanup_duel(duel_state, reason="discord_api_error")
            try:
                await channel.send(
                    "**Duel Interrupted**\n\n"
                    "The duel has been cancelled due to a Discord API error. "
                    "Please try again later."
                )
            except Exception:
                pass

        except asyncio.CancelledError:
            # Task was cancelled (e.g., bot shutdown)
            log.info(
                "Duel task cancelled (channel=%s): %s vs %s",
                duel_state.channel_id, duel_state.persona1, duel_state.persona2
            )
            self._cleanup_duel(duel_state, reason="task_cancelled")
            raise  # Re-raise to properly handle cancellation

        except Exception as e:
            # Catch-all for unexpected errors
            log.error(
                "Unexpected error during duel execution (channel=%s): %s",
                duel_state.channel_id, e, exc_info=True
            )
            try:
                await channel.send(
                    "**Duel Error**\n\n"
                    "An unexpected error occurred during the duel. The duel has been cancelled."
                )
            except Exception:
                pass

        finally:
            # Always ensure cleanup happens
            self._cleanup_duel(duel_state, reason="final_cleanup")

    async def _run_rounds_mode(self, channel: discord.abc.Messageable, duel_state: DuelState) -> None:
        """Execute the duel in rounds mode.

        Each round consists of persona1 speaking, then persona2 responding.

        Args:
            channel: The Discord channel where the duel is taking place.
            duel_state: The current duel state.
        """
        while not duel_state.is_complete():
            # Check if duel was cancelled
            if duel_state.channel_id not in self.bot.prism_active_duels:  # type: ignore[attr-defined]
                log.debug("Duel cancelled during rounds mode (channel=%s)", duel_state.channel_id)
                return

            current_round = duel_state.current_round
            total_rounds = duel_state.duration

            # Persona 1 speaks
            await self._persona_speak(
                channel,
                duel_state,
                duel_state.persona1,
                current_round,
                total_rounds,
            )

            # Check if duel was cancelled
            if duel_state.channel_id not in self.bot.prism_active_duels:  # type: ignore[attr-defined]
                log.debug("Duel cancelled after persona1 spoke (channel=%s)", duel_state.channel_id)
                return

            # Persona 2 responds
            await self._persona_speak(
                channel,
                duel_state,
                duel_state.persona2,
                current_round,
                total_rounds,
            )

            # Increment round
            duel_state.increment_round()

    async def _run_time_mode(self, channel: discord.abc.Messageable, duel_state: DuelState) -> None:
        """Execute the duel in time mode.

        Personas alternate messages until the time limit expires.
        The current speaker finishes their message after time expires.

        Args:
            channel: The Discord channel where the duel is taking place.
            duel_state: The current duel state.
        """
        # Alternate between personas
        personas = [duel_state.persona1, duel_state.persona2]
        turn_index = 0

        while True:
            # Check if duel was cancelled
            if duel_state.channel_id not in self.bot.prism_active_duels:  # type: ignore[attr-defined]
                log.debug("Duel cancelled during time mode (channel=%s)", duel_state.channel_id)
                return

            # Get remaining time
            remaining_time = duel_state.get_remaining_time()

            # Check if time has expired before starting a new turn
            if duel_state.is_complete():
                break

            # Current speaker
            current_persona = personas[turn_index % 2]

            # Let the persona speak (they can finish even if time expires during)
            await self._persona_speak(
                channel,
                duel_state,
                current_persona,
                remaining_seconds=remaining_time,
            )

            turn_index += 1

            # Check completion after the speaker finishes
            if duel_state.is_complete():
                break

    async def _persona_speak(
        self,
        channel: discord.abc.Messageable,
        duel_state: DuelState,
        persona_name: str,
        current_round: int | None = None,
        total_rounds: int | None = None,
        remaining_seconds: float | None = None,
    ) -> None:
        """Generate and send a persona's response.

        This method handles AI communication and Discord API calls with proper
        error handling for each operation.

        Args:
            channel: The Discord channel to send the message to.
            duel_state: The current duel state.
            persona_name: The name of the persona speaking.
            current_round: Current round number (for rounds mode).
            total_rounds: Total number of rounds (for rounds mode).
            remaining_seconds: Remaining time in seconds (for time mode).

        Raises:
            discord.NotFound: If channel or message was deleted.
            discord.Forbidden: If bot lacks permissions.
            discord.HTTPException: For other Discord API errors.
        """
        # Load persona
        persona_record = await self.bot.prism_personas.get(persona_name)  # type: ignore[attr-defined]
        if persona_record is None:
            log.error("Persona '%s' not found during duel (channel=%s)", persona_name, duel_state.channel_id)
            # Use a fallback response if persona was deleted mid-duel
            response_text = f"*{persona_name} has mysteriously vanished...*"
            display_name = persona_name.capitalize()
        else:
            # Build system prompt with strategic awareness
            system_prompt = self._build_system_prompt(
                persona_record.data.system_prompt,
                duel_state,
                current_round=current_round,
                total_rounds=total_rounds,
                remaining_seconds=remaining_seconds,
            )

            # Build messages list with conversation history
            messages = self._build_messages(system_prompt, duel_state, persona_name)

            # Get model and temperature from persona, if set
            model = persona_record.data.model
            temperature = persona_record.data.temperature

            # Call AI for response with error handling (limit tokens for brevity)
            try:
                response_text, _meta = await self.bot.prism_orc.chat_completion(  # type: ignore[attr-defined]
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=DUEL_MAX_TOKENS,
                )
            except Exception as e:
                log.error(
                    "AI call failed for persona '%s' (channel=%s): %s",
                    persona_name, duel_state.channel_id, e, exc_info=True
                )
                # Provide a fallback response so the duel can continue
                response_text = f"*{persona_name} is gathering their thoughts...*"

            # Get display name
            display_name = (persona_record.data.display_name or "").strip()
            if not display_name:
                parts = re.split(r"[-_\s]+", (persona_name or "").strip())
                display_name = " ".join(w.capitalize() for w in parts if w)

        # Simulate typing (non-critical, errors are handled internally)
        await simulate_typing(channel, response_text)

        # Send message - this may raise Discord exceptions that should propagate
        formatted_message = f"**{display_name}:** {response_text}"
        formatted_message = _clip_to_discord_limit(formatted_message)
        try:
            sent_message = await channel.send(formatted_message)
        except discord.NotFound:
            log.warning("Channel not found when sending duel message (channel=%s)", duel_state.channel_id)
            raise
        except discord.Forbidden:
            log.warning("Permission denied when sending duel message (channel=%s)", duel_state.channel_id)
            raise
        except discord.HTTPException as e:
            log.error("HTTP error when sending duel message (channel=%s): %s", duel_state.channel_id, e)
            raise

        # Store in conversation history
        duel_state.messages.append({
            "role": "assistant",
            "content": response_text,
            "persona": persona_name,
            "display_name": display_name,
        })

        # Add emoji reaction from the opposing persona (non-critical)
        await self._add_opposing_reaction(sent_message, response_text, duel_state, persona_name)

    async def _add_opposing_reaction(
        self,
        message: discord.Message,
        message_content: str,
        duel_state: DuelState,
        speaking_persona: str,
    ) -> None:
        """Add an emoji reaction from the opposing persona.

        The opposing persona reacts to the speaking persona's message with an emoji.
        Custom guild emojis are preferred when available.
        Used reactions are tracked to ensure variety within a duel.

        This is a non-critical operation - failures are logged but don't interrupt the duel.

        Args:
            message: The Discord message to add the reaction to.
            message_content: The content of the message (used for contextual emoji suggestions).
            duel_state: The current duel state.
            speaking_persona: The name of the persona who just spoke.
        """
        try:
            # Get guild_id for emoji suggestions
            guild_id = getattr(message.guild, "id", None) if hasattr(message, "guild") else None

            # Get emoji to use for reaction
            emoji_to_use = await self._get_reaction_emoji(
                guild_id=guild_id,
                message_content=message_content,
                duel_state=duel_state,
            )

            if emoji_to_use:
                # Add a human-like delay before reacting (4-12 seconds)
                await asyncio.sleep(random.uniform(4.0, 12.0))
                # Add the reaction
                await message.add_reaction(emoji_to_use)
                # Track the used reaction
                duel_state.used_reactions.add(emoji_to_use)
        except discord.NotFound:
            log.debug("Message not found when adding reaction (channel=%s)", duel_state.channel_id)
        except discord.Forbidden:
            log.debug("Permission denied when adding reaction (channel=%s)", duel_state.channel_id)
        except discord.HTTPException as e:
            log.debug("HTTP error when adding reaction (channel=%s): %s", duel_state.channel_id, e)
        except Exception as e:
            # Catch any other errors (e.g., emoji service errors)
            log.debug("Failed to add emoji reaction (channel=%s): %s", duel_state.channel_id, e)

    async def _get_reaction_emoji(
        self,
        guild_id: int | None,
        message_content: str,
        duel_state: DuelState,
    ) -> str | None:
        """Get an emoji to use for a reaction.

        Uses EmojiIndexService.suggest_for_text() for contextual suggestions.
        Filters out already-used emojis and falls back to Unicode if needed.

        Args:
            guild_id: The guild ID for custom emoji lookup, or None.
            message_content: The content of the message for contextual suggestions.
            duel_state: The current duel state (for tracking used reactions).

        Returns:
            An emoji string (custom format or Unicode), or None if no emoji available.
        """
        # Try to get contextual emoji suggestions from the emoji service
        emoji_suggestions: list[str] = []

        if guild_id is not None and hasattr(self.bot, "prism_emoji"):
            try:
                emoji_service = self.bot.prism_emoji  # type: ignore[attr-defined]
                emoji_suggestions = await emoji_service.suggest_for_text(
                    guild_id=guild_id,
                    text=message_content,
                    limit=10,
                )
            except Exception as e:
                log.debug("Failed to get emoji suggestions: %s", e)
                emoji_suggestions = []

        # Filter out already-used reactions
        available_emojis = [e for e in emoji_suggestions if e not in duel_state.used_reactions]

        # If we have available emojis from suggestions, use the first one
        if available_emojis:
            return available_emojis[0]

        # Fall back to default Unicode emojis
        available_unicode = [e for e in DEFAULT_UNICODE_EMOJIS if e not in duel_state.used_reactions]
        if available_unicode:
            return available_unicode[0]

        # If all emojis are exhausted, return None (no reaction)
        return None

    def _build_system_prompt(
        self,
        base_prompt: str,
        duel_state: DuelState,
        current_round: int | None = None,
        total_rounds: int | None = None,
        remaining_seconds: float | None = None,
    ) -> str:
        """Build the system prompt with strategic awareness injection.

        Args:
            base_prompt: The persona's base system prompt.
            duel_state: The current duel state.
            current_round: Current round number (for rounds mode).
            total_rounds: Total number of rounds (for rounds mode).
            remaining_seconds: Remaining time in seconds (for time mode).

        Returns:
            The complete system prompt with strategic awareness.
        """
        # Build duel context
        duel_context = (
            f"\n\nYou're in a quick-fire debate on: \"{duel_state.topic}\"\n"
            f"Keep responses SHORT (2-3 sentences). Be witty, not wordy. Stay in character."
        )

        # Add strategic awareness
        strategic_awareness = ""
        if duel_state.mode == DuelMode.ROUNDS and current_round is not None and total_rounds is not None:
            strategic_awareness = f"\n\nThis is round {current_round} of {total_rounds}. Pace your arguments accordingly."
        elif duel_state.mode == DuelMode.TIME and remaining_seconds is not None:
            # Round to nearest whole number for cleaner display
            seconds = int(remaining_seconds)
            strategic_awareness = f"\n\nApproximately {seconds} seconds remaining. Pace your arguments accordingly."

        return base_prompt + duel_context + strategic_awareness

    def _build_messages(
        self,
        system_prompt: str,
        duel_state: DuelState,
        current_persona: str,
    ) -> list[dict[str, Any]]:
        """Build the messages list for the AI call.

        Args:
            system_prompt: The complete system prompt.
            duel_state: The current duel state.
            current_persona: The name of the persona currently speaking.

        Returns:
            A list of messages for the AI call.
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

        # Add user message with topic as initial prompt
        if not duel_state.messages:
            # First message: introduce the topic (keep it conversational and brief)
            messages.append({
                "role": "user",
                "content": (
                    f"Topic: \"{duel_state.topic}\"\n\n"
                    "Give a quick, punchy take on this. Keep it short - 2-3 sentences max. "
                    "This is banter, not a speech!"
                ),
            })
        else:
            # Add conversation history
            for msg in duel_state.messages:
                msg_persona = msg.get("persona", "")
                msg_content = msg.get("content", "")
                msg_display = msg.get("display_name", msg_persona)

                # Messages from the current persona appear as "assistant" (previous turns)
                # Messages from the opponent appear as "user" (what they need to respond to)
                if msg_persona == current_persona:
                    messages.append({"role": "assistant", "content": msg_content})
                else:
                    # Format opponent's message with their name for context
                    messages.append({"role": "user", "content": f"{msg_display}: {msg_content}"})

            # Add prompt for continuation (keep it snappy)
            messages.append({
                "role": "user",
                "content": "Fire back! Keep it short and spicy - 2-3 sentences.",
            })

        return messages

    async def _invoke_judge(self, channel: discord.abc.Messageable, duel_state: DuelState) -> None:
        """Invoke the neutral judge AI to evaluate the duel and declare a winner.

        Args:
            channel: The Discord channel to post the judgment in.
            duel_state: The completed duel state with all messages.

        Raises:
            discord.NotFound: If channel was deleted.
            discord.Forbidden: If bot lacks permissions.
            discord.HTTPException: For other Discord API errors.
        """
        # Build the transcript for the judge
        transcript_lines = [f"Topic: \"{duel_state.topic}\"", "", "Debate Transcript:"]
        for msg in duel_state.messages:
            display_name = msg.get("display_name", msg.get("persona", "Unknown"))
            content = msg.get("content", "")
            transcript_lines.append(f"{display_name}: {content}")

        transcript = "\n".join(transcript_lines)

        # Build judge messages
        judge_messages: list[dict[str, Any]] = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{transcript}\n\nPlease evaluate this debate and declare a winner.",
            },
        ]

        # Call AI for judge response (no persona model/temperature - use defaults)
        try:
            judge_response, _meta = await self.bot.prism_orc.chat_completion(  # type: ignore[attr-defined]
                messages=judge_messages,
            )
        except Exception as e:
            log.error("Judge AI call failed (channel=%s): %s", duel_state.channel_id, e, exc_info=True)
            judge_response = "The judge was unable to render a verdict due to a technical issue."

        # Simulate typing for the judge response (non-critical)
        await simulate_typing(channel, judge_response)

        # Format and post the judgment
        formatted_judgment = format_judge_response(judge_response, duel_state)
        try:
            await channel.send(formatted_judgment)
        except discord.NotFound:
            log.warning("Channel not found when posting judgment (channel=%s)", duel_state.channel_id)
            raise
        except discord.Forbidden:
            log.warning("Permission denied when posting judgment (channel=%s)", duel_state.channel_id)
            raise
        except discord.HTTPException as e:
            log.error("HTTP error when posting judgment (channel=%s): %s", duel_state.channel_id, e)
            raise


def setup(bot: discord.Bot):
    """Setup the DuelCog and optionally scope commands to specific guilds."""
    gids = getattr(getattr(bot, "prism_cfg", None), "command_guild_ids", None)
    if gids:
        try:
            DuelCog.duel.guild_ids = gids  # type: ignore[attr-defined]
            for sc in getattr(DuelCog.duel, "subcommands", []) or []:
                try:
                    setattr(sc, "guild_ids", gids)
                except AttributeError:
                    # Some subcommand types may not support guild_ids
                    pass
            log.info("duel commands scoped to guilds: %s", ",".join(str(g) for g in gids))
        except Exception:
            log.warning("Failed to scope duel commands to guilds", exc_info=True)
    bot.add_cog(DuelCog(bot))
