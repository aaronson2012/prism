"""Duel state management for persona duels."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# Typing simulation constants (2x for more natural pacing)
TYPING_BASE_DELAY = 3.0  # Base delay in seconds
TYPING_DELAY_PER_CHAR = 0.04  # Additional delay per character
TYPING_MAX_DELAY = 16.0  # Maximum delay cap in seconds


# Neutral judge system prompt for evaluating duel outcomes
JUDGE_SYSTEM_PROMPT = """You are a neutral and impartial judge evaluating a debate between two participants.

Your role is to:
1. Review the complete debate transcript objectively
2. Evaluate the strength of each participant's arguments
3. Consider logical reasoning, evidence, creativity, and persuasiveness
4. Do NOT favor either participant based on personality or popularity

Provide your evaluation in 2-3 sentences explaining your reasoning, then clearly declare the winner.

Format your response as:
[Your 2-3 sentence reasoning explaining why you made your decision]

Winner: [Name of the winning participant]"""


def calculate_typing_delay(message: str) -> float:
    """Calculate typing delay based on message length.

    Formula: base delay (1.5s) + 0.02s per character, capped at 8 seconds.

    Args:
        message: The message content to calculate delay for.

    Returns:
        The typing delay in seconds (between 1.5 and 8.0).
    """
    char_delay = len(message) * TYPING_DELAY_PER_CHAR
    total_delay = TYPING_BASE_DELAY + char_delay
    return min(total_delay, TYPING_MAX_DELAY)


def format_judge_response(judge_response: str, duel_state: DuelState) -> str:
    """Format the judge's response for Discord display.

    Args:
        judge_response: The raw response from the judge AI.
        duel_state: The duel state for context.

    Returns:
        A formatted string suitable for Discord with bold/emphasis.
    """
    if not judge_response:
        judge_response = "The judge was unable to render a verdict."

    # Build the formatted message
    formatted = (
        f"**JUDGMENT**\n\n"
        f"{judge_response}"
    )

    return formatted


class DuelMode(Enum):
    """Enum for duel mode selection."""

    ROUNDS = "rounds"
    TIME = "time"

    # Default values
    @classmethod
    def default_rounds(cls) -> int:
        """Default number of rounds for rounds mode."""
        return 3

    @classmethod
    def default_time(cls) -> int:
        """Default duration in seconds for time mode."""
        return 120

    # Maximum values
    @classmethod
    def max_rounds(cls) -> int:
        """Maximum number of rounds allowed."""
        return 10

    @classmethod
    def max_time(cls) -> int:
        """Maximum duration in seconds allowed."""
        return 300


@dataclass
class DuelState:
    """Tracks the state of an active persona duel.

    Attributes:
        channel_id: Discord channel ID where the duel is taking place
        persona1: Name of the first persona
        persona2: Name of the second persona
        topic: The debate topic
        mode: The duel mode (rounds or time)
        duration: Number of rounds or time limit in seconds
        current_round: Current round number (1-indexed)
        start_time: Monotonic timestamp when the duel started
        messages: List of messages exchanged during the duel
        used_reactions: Set of emoji tokens already used in reactions
    """

    channel_id: int
    persona1: str
    persona2: str
    topic: str
    mode: DuelMode
    duration: int
    current_round: int = 1
    start_time: float = field(default_factory=time.monotonic)
    messages: list[dict[str, Any]] = field(default_factory=list)
    used_reactions: set[str] = field(default_factory=set)

    def is_complete(self) -> bool:
        """Check if the duel has reached its end condition.

        For rounds mode: complete when current_round exceeds duration (total rounds).
        For time mode: complete when elapsed time exceeds duration.

        Returns:
            True if the duel should end, False otherwise.
        """
        if self.mode == DuelMode.ROUNDS:
            # In rounds mode, duration is the total number of rounds
            # A round consists of both personas speaking
            # current_round starts at 1, so > duration means we've completed all rounds
            return self.current_round > self.duration
        else:
            # In time mode, duration is the time limit in seconds
            return self.get_elapsed_time() >= self.duration

    def get_elapsed_time(self) -> float:
        """Return elapsed time in seconds since duel started.

        Returns:
            Elapsed time in seconds as a float.
        """
        return time.monotonic() - self.start_time

    def get_remaining_time(self) -> float:
        """Return remaining time for time mode.

        For rounds mode, returns 0.0 as time is not relevant.

        Returns:
            Remaining time in seconds, or 0.0 if already expired or in rounds mode.
        """
        if self.mode != DuelMode.TIME:
            return 0.0
        remaining = self.duration - self.get_elapsed_time()
        return max(0.0, remaining)

    def increment_round(self) -> None:
        """Advance the round counter by one."""
        self.current_round += 1
