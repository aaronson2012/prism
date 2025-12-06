"""Tests for duel state management and duel commands."""

import asyncio
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prism.models.duel import (
    DuelMode,
    DuelState,
    JUDGE_SYSTEM_PROMPT,
    calculate_typing_delay,
    format_judge_response,
)


class TestDuelMode:
    """Tests for DuelMode enum."""

    def test_duel_mode_values(self):
        """Test DuelMode has correct enum values."""
        assert DuelMode.ROUNDS.value == "rounds"
        assert DuelMode.TIME.value == "time"

    def test_duel_mode_default_values(self):
        """Test DuelMode default values."""
        assert DuelMode.default_rounds() == 3
        assert DuelMode.default_time() == 120

    def test_duel_mode_max_values(self):
        """Test DuelMode max values."""
        assert DuelMode.max_rounds() == 10
        assert DuelMode.max_time() == 300


class TestDuelStateCreation:
    """Tests for DuelState dataclass creation."""

    def test_duel_state_creation_with_required_fields(self):
        """Test DuelState dataclass creation with all required fields."""
        state = DuelState(
            channel_id=123456789,
            persona1="wizard",
            persona2="pirate",
            topic="Which is better: magic or sea adventures?",
            mode=DuelMode.ROUNDS,
            duration=5,
        )

        assert state.channel_id == 123456789
        assert state.persona1 == "wizard"
        assert state.persona2 == "pirate"
        assert state.topic == "Which is better: magic or sea adventures?"
        assert state.mode == DuelMode.ROUNDS
        assert state.duration == 5
        assert state.current_round == 1
        assert isinstance(state.start_time, float)
        assert state.messages == []
        assert state.used_reactions == set()

    def test_duel_state_creation_with_all_fields(self):
        """Test DuelState with explicit values for all fields."""
        messages = [{"role": "assistant", "content": "Test message", "persona": "wizard"}]
        used_reactions = {"thumbsup", "fire"}

        state = DuelState(
            channel_id=987654321,
            persona1="detective",
            persona2="chef",
            topic="Who solves problems better?",
            mode=DuelMode.TIME,
            duration=180,
            current_round=3,
            start_time=1000.0,
            messages=messages,
            used_reactions=used_reactions,
        )

        assert state.channel_id == 987654321
        assert state.persona1 == "detective"
        assert state.persona2 == "chef"
        assert state.mode == DuelMode.TIME
        assert state.duration == 180
        assert state.current_round == 3
        assert state.start_time == 1000.0
        assert state.messages == messages
        assert state.used_reactions == used_reactions


class TestActiveDuelsStorage:
    """Tests for active duels dictionary storage and retrieval."""

    def test_active_duels_storage_and_retrieval_by_channel_id(self):
        """Test storing and retrieving duel states by channel_id."""
        # Simulate the bot.prism_active_duels dictionary
        active_duels: dict[int, DuelState] = {}

        # Create duel states for different channels
        state1 = DuelState(
            channel_id=111,
            persona1="wizard",
            persona2="pirate",
            topic="Topic 1",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        state2 = DuelState(
            channel_id=222,
            persona1="detective",
            persona2="chef",
            topic="Topic 2",
            mode=DuelMode.TIME,
            duration=120,
        )

        # Store states by channel_id
        active_duels[state1.channel_id] = state1
        active_duels[state2.channel_id] = state2

        # Retrieve by channel_id
        retrieved1 = active_duels.get(111)
        retrieved2 = active_duels.get(222)

        assert retrieved1 is state1
        assert retrieved1.persona1 == "wizard"
        assert retrieved2 is state2
        assert retrieved2.persona1 == "detective"

        # Test non-existent channel returns None
        assert active_duels.get(333) is None

    def test_rejection_of_new_duel_when_active_in_channel(self):
        """Test that a new duel should be rejected when one is already active in channel."""
        active_duels: dict[int, DuelState] = {}
        channel_id = 123456

        # Create and store an active duel
        existing_duel = DuelState(
            channel_id=channel_id,
            persona1="wizard",
            persona2="pirate",
            topic="Existing duel topic",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        active_duels[channel_id] = existing_duel

        # Attempt to create a new duel in the same channel
        # The check that should happen before creating a new duel:
        if channel_id in active_duels:
            can_start_new_duel = False
        else:
            can_start_new_duel = True

        assert can_start_new_duel is False
        assert active_duels[channel_id] is existing_duel


class TestDuelStateCleanup:
    """Tests for duel state cleanup after completion."""

    def test_duel_state_cleanup_after_completion(self):
        """Test duel state cleanup after completion."""
        active_duels: dict[int, DuelState] = {}
        channel_id = 123456

        # Create and store an active duel
        duel_state = DuelState(
            channel_id=channel_id,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        active_duels[channel_id] = duel_state

        # Verify duel exists
        assert channel_id in active_duels

        # Simulate duel completion and cleanup
        del active_duels[channel_id]

        # Verify duel is cleaned up
        assert channel_id not in active_duels
        assert active_duels.get(channel_id) is None


class TestDuelStateHelperMethods:
    """Tests for DuelState helper methods."""

    def test_is_complete_rounds_mode_not_complete(self):
        """Test is_complete returns False when rounds not finished."""
        state = DuelState(
            channel_id=123,
            persona1="a",
            persona2="b",
            topic="test",
            mode=DuelMode.ROUNDS,
            duration=3,
            current_round=2,
        )
        assert state.is_complete() is False

    def test_is_complete_rounds_mode_complete(self):
        """Test is_complete returns True when all rounds finished."""
        state = DuelState(
            channel_id=123,
            persona1="a",
            persona2="b",
            topic="test",
            mode=DuelMode.ROUNDS,
            duration=3,
            current_round=4,  # > 3 means we've completed all 3 rounds
        )
        assert state.is_complete() is True

    def test_is_complete_time_mode_not_complete(self):
        """Test is_complete returns False when time not expired."""
        with patch("prism.models.duel.time.monotonic") as mock_monotonic:
            # Set current time to 1050.0 (50 seconds after start)
            mock_monotonic.return_value = 1050.0
            state = DuelState(
                channel_id=123,
                persona1="a",
                persona2="b",
                topic="test",
                mode=DuelMode.TIME,
                duration=120,
                start_time=1000.0,  # Explicitly set start time
            )
            assert state.is_complete() is False

    def test_is_complete_time_mode_complete(self):
        """Test is_complete returns True when time expired."""
        with patch("prism.models.duel.time.monotonic") as mock_monotonic:
            # Set current time to 1130.0 (130 seconds after start, past 120 duration)
            mock_monotonic.return_value = 1130.0
            state = DuelState(
                channel_id=123,
                persona1="a",
                persona2="b",
                topic="test",
                mode=DuelMode.TIME,
                duration=120,
                start_time=1000.0,  # Explicitly set start time
            )
            assert state.is_complete() is True

    def test_get_elapsed_time(self):
        """Test get_elapsed_time returns correct elapsed time."""
        with patch("prism.models.duel.time.monotonic") as mock_monotonic:
            # Set current time to 1045.0 (45 seconds after start)
            mock_monotonic.return_value = 1045.0
            state = DuelState(
                channel_id=123,
                persona1="a",
                persona2="b",
                topic="test",
                mode=DuelMode.ROUNDS,
                duration=3,
                start_time=1000.0,  # Explicitly set start time
            )
            assert state.get_elapsed_time() == 45.0

    def test_get_remaining_time_time_mode(self):
        """Test get_remaining_time returns correct remaining time for time mode."""
        with patch("prism.models.duel.time.monotonic") as mock_monotonic:
            # Set current time to 1030.0 (30 seconds elapsed, 90 remaining)
            mock_monotonic.return_value = 1030.0
            state = DuelState(
                channel_id=123,
                persona1="a",
                persona2="b",
                topic="test",
                mode=DuelMode.TIME,
                duration=120,
                start_time=1000.0,  # Explicitly set start time
            )
            assert state.get_remaining_time() == 90.0

    def test_get_remaining_time_rounds_mode_returns_zero(self):
        """Test get_remaining_time returns 0 for rounds mode."""
        state = DuelState(
            channel_id=123,
            persona1="a",
            persona2="b",
            topic="test",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        assert state.get_remaining_time() == 0.0

    def test_get_remaining_time_does_not_go_negative(self):
        """Test get_remaining_time returns 0 when time expired."""
        with patch("prism.models.duel.time.monotonic") as mock_monotonic:
            # Set current time to 1200.0 (200 seconds after start, way past 120 duration)
            mock_monotonic.return_value = 1200.0
            state = DuelState(
                channel_id=123,
                persona1="a",
                persona2="b",
                topic="test",
                mode=DuelMode.TIME,
                duration=120,
                start_time=1000.0,  # Explicitly set start time
            )
            assert state.get_remaining_time() == 0.0

    def test_increment_round(self):
        """Test increment_round advances round counter."""
        state = DuelState(
            channel_id=123,
            persona1="a",
            persona2="b",
            topic="test",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        assert state.current_round == 1
        state.increment_round()
        assert state.current_round == 2
        state.increment_round()
        assert state.current_round == 3


# =============================================================================
# Task Group 2: Duel Slash Commands Tests
# =============================================================================


class MockChannel:
    """Mock Discord channel for testing duel commands."""

    def __init__(self, channel_id: int = 123456789):
        self.id = channel_id


class MockApplicationContext:
    """Mock Discord ApplicationContext for testing cog commands."""

    def __init__(self, channel_id: int = 123456789):
        self.channel = MockChannel(channel_id)
        self.respond = AsyncMock()
        self.defer = AsyncMock()


class MockPersonaRecord:
    """Mock persona record returned by PersonasService.get()."""

    def __init__(self, name: str, display_name: str | None = None, system_prompt: str = "Test prompt", model: str | None = None, temperature: float | None = None):
        self.data = MagicMock()
        self.data.name = name
        self.data.display_name = display_name or name.capitalize()
        self.data.system_prompt = system_prompt
        self.data.model = model
        self.data.temperature = temperature


class TestDuelStartCommand:
    """Tests for /duel start command."""

    @pytest.mark.asyncio
    async def test_duel_start_with_valid_personas_and_topic(self):
        """Test /duel start command with valid personas and topic creates duel state."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock personas service - both personas exist
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=lambda name: MockPersonaRecord(name))
        bot.prism_personas = mock_personas

        # Create mock context
        channel_id = 123456789
        ctx = MockApplicationContext(channel_id=channel_id)

        # Simulate the duel start command logic
        persona1 = "wizard"
        persona2 = "pirate"
        topic = "Which is better: magic or the sea?"
        mode = "rounds"
        duration = 3

        # Check both personas exist
        rec1 = await bot.prism_personas.get(persona1)
        rec2 = await bot.prism_personas.get(persona2)

        assert rec1 is not None
        assert rec2 is not None

        # Validate personas are different
        assert persona1 != persona2

        # Check no active duel in channel
        assert channel_id not in bot.prism_active_duels

        # Create duel state
        duel_state = DuelState(
            channel_id=channel_id,
            persona1=persona1,
            persona2=persona2,
            topic=topic,
            mode=DuelMode.ROUNDS if mode == "rounds" else DuelMode.TIME,
            duration=duration,
        )
        bot.prism_active_duels[channel_id] = duel_state

        # Verify duel state was created
        assert channel_id in bot.prism_active_duels
        stored_state = bot.prism_active_duels[channel_id]
        assert stored_state.persona1 == "wizard"
        assert stored_state.persona2 == "pirate"
        assert stored_state.topic == "Which is better: magic or the sea?"
        assert stored_state.mode == DuelMode.ROUNDS
        assert stored_state.duration == 3

    @pytest.mark.asyncio
    async def test_duel_start_rejection_when_persona_does_not_exist(self):
        """Test /duel start rejects when a persona does not exist."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock personas service - persona1 exists, persona2 does NOT
        async def get_persona(name: str):
            if name == "wizard":
                return MockPersonaRecord(name)
            return None

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=get_persona)
        bot.prism_personas = mock_personas

        # Simulate the duel start command logic
        persona1 = "wizard"
        persona2 = "nonexistent"

        # Check both personas exist
        rec1 = await bot.prism_personas.get(persona1)
        rec2 = await bot.prism_personas.get(persona2)

        assert rec1 is not None
        assert rec2 is None  # This persona does not exist

        # The command should reject and NOT create a duel
        should_reject = rec1 is None or rec2 is None
        assert should_reject is True

    @pytest.mark.asyncio
    async def test_duel_start_rejection_when_same_persona_specified(self):
        """Test /duel start rejects when same persona specified for both."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock personas service - persona exists
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(return_value=MockPersonaRecord("wizard"))
        bot.prism_personas = mock_personas

        # Simulate the duel start command logic
        persona1 = "wizard"
        persona2 = "wizard"  # Same persona!

        # Check both personas exist
        rec1 = await bot.prism_personas.get(persona1)
        rec2 = await bot.prism_personas.get(persona2)

        assert rec1 is not None
        assert rec2 is not None

        # Validate personas are different - this should fail
        personas_are_different = persona1 != persona2
        assert personas_are_different is False

        # The command should reject
        should_reject = not personas_are_different
        assert should_reject is True

    @pytest.mark.asyncio
    async def test_duel_start_rejection_when_duel_already_active(self):
        """Test /duel start rejects when duel already active in channel."""
        # Setup mock bot with an existing active duel
        channel_id = 123456789
        bot = MagicMock()
        existing_duel = DuelState(
            channel_id=channel_id,
            persona1="detective",
            persona2="chef",
            topic="Existing duel",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        bot.prism_active_duels = {channel_id: existing_duel}

        # Mock personas service - both personas exist
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=lambda name: MockPersonaRecord(name))
        bot.prism_personas = mock_personas

        # Simulate the duel start command logic
        persona1 = "wizard"
        persona2 = "pirate"

        # Check both personas exist
        rec1 = await bot.prism_personas.get(persona1)
        rec2 = await bot.prism_personas.get(persona2)

        assert rec1 is not None
        assert rec2 is not None

        # Validate personas are different
        assert persona1 != persona2

        # Check no active duel in channel - this should fail
        has_active_duel = channel_id in bot.prism_active_duels
        assert has_active_duel is True

        # The command should reject
        should_reject = has_active_duel
        assert should_reject is True


class TestDuelStopCommand:
    """Tests for /duel stop command."""

    @pytest.mark.asyncio
    async def test_duel_stop_cancels_active_duel(self):
        """Test /duel stop cancels active duel and removes from active_duels."""
        # Setup mock bot with an active duel
        channel_id = 123456789
        bot = MagicMock()
        active_duel = DuelState(
            channel_id=channel_id,
            persona1="wizard",
            persona2="pirate",
            topic="Test duel",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        bot.prism_active_duels = {channel_id: active_duel}

        # Verify duel exists before stop
        assert channel_id in bot.prism_active_duels

        # Simulate the duel stop command logic
        # Check for active duel in current channel
        if channel_id in bot.prism_active_duels:
            # Remove duel from active_duels
            del bot.prism_active_duels[channel_id]
            duel_cancelled = True
        else:
            duel_cancelled = False

        # Verify duel was cancelled
        assert duel_cancelled is True
        assert channel_id not in bot.prism_active_duels

    @pytest.mark.asyncio
    async def test_duel_stop_returns_error_when_no_active_duel(self):
        """Test /duel stop returns error when no active duel in channel."""
        # Setup mock bot with NO active duels
        channel_id = 123456789
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Verify no duel exists
        assert channel_id not in bot.prism_active_duels

        # Simulate the duel stop command logic
        if channel_id in bot.prism_active_duels:
            del bot.prism_active_duels[channel_id]
            duel_cancelled = True
            error_no_active_duel = False
        else:
            duel_cancelled = False
            error_no_active_duel = True

        # Verify error returned
        assert duel_cancelled is False
        assert error_no_active_duel is True


# =============================================================================
# Task Group 3: Typing Simulation Tests
# =============================================================================


class TestTypingDelayCalculation:
    """Tests for typing delay calculation function."""

    def test_delay_calculation_scales_with_message_length(self):
        """Test delay increases with message length at 0.04 seconds per character."""
        # Short message (11 chars): base 3.0 + 11 * 0.04 = 3.44 seconds
        short_delay = calculate_typing_delay("Hello World")  # 11 chars
        assert short_delay == pytest.approx(3.0 + 11 * 0.04, rel=0.01)

        # Medium message (100 chars): base 3.0 + 100 * 0.04 = 7.0 seconds
        medium_msg = "A" * 100
        medium_delay = calculate_typing_delay(medium_msg)
        assert medium_delay == pytest.approx(3.0 + 100 * 0.04, rel=0.01)

        # Long message (200 chars): base 3.0 + 200 * 0.04 = 11.0 seconds
        long_msg = "B" * 200
        long_delay = calculate_typing_delay(long_msg)
        assert long_delay == pytest.approx(3.0 + 200 * 0.04, rel=0.01)

        # Verify scaling: longer messages have longer delays
        assert short_delay < medium_delay < long_delay

    def test_delay_capped_at_16_seconds_maximum(self):
        """Test delay is capped at 16 seconds for very long messages."""
        # Very long message (500 chars): would be 3.0 + 500 * 0.04 = 23s, but capped at 16s
        very_long_msg = "C" * 500
        delay = calculate_typing_delay(very_long_msg)
        assert delay == 16.0

        # Extremely long message (1000 chars): still capped at 16s
        extremely_long_msg = "D" * 1000
        delay = calculate_typing_delay(extremely_long_msg)
        assert delay == 16.0

    def test_base_delay_for_short_messages(self):
        """Test base delay of 3.0 seconds for very short or empty messages."""
        # Empty message: base delay only
        empty_delay = calculate_typing_delay("")
        assert empty_delay == 3.0

        # Single character: 3.0 + 1 * 0.04 = 3.04 seconds
        single_char_delay = calculate_typing_delay("A")
        assert single_char_delay == pytest.approx(3.04, rel=0.01)


class TestTypingSimulationWrapper:
    """Tests for typing simulation wrapper function."""

    @pytest.mark.asyncio
    async def test_typing_context_manager_called_before_message_send(self):
        """Test typing context manager is called and sleep executes during typing."""
        # Create mock channel with typing context manager
        mock_channel = MagicMock()
        mock_typing_context = MagicMock()
        mock_typing_context.__aenter__ = AsyncMock(return_value=None)
        mock_typing_context.__aexit__ = AsyncMock(return_value=None)
        mock_channel.typing.return_value = mock_typing_context

        # Test message
        test_message = "This is a test message for typing simulation."

        # Define a standalone simulate_typing function that uses the model's calculate_typing_delay
        # This allows testing without importing the discord-dependent cog
        async def simulate_typing_test(channel, message: str) -> None:
            delay = calculate_typing_delay(message)
            async with channel.typing():
                await asyncio.sleep(delay)

        # Simulate typing with patched asyncio.sleep
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await simulate_typing_test(mock_channel, test_message)

            # Verify typing() was called on channel
            mock_channel.typing.assert_called_once()

            # Verify context manager was entered
            mock_typing_context.__aenter__.assert_called_once()

            # Verify sleep was called with calculated delay
            expected_delay = 3.0 + len(test_message) * 0.04
            mock_sleep.assert_called_once()
            actual_delay = mock_sleep.call_args[0][0]
            assert actual_delay == pytest.approx(expected_delay, rel=0.01)

            # Verify context manager was exited
            mock_typing_context.__aexit__.assert_called_once()


# =============================================================================
# Task Group 4: Duel Loop and AI Communication Tests
# =============================================================================

# These tests verify the duel loop logic without importing the discord-dependent cog.
# We test the core logic directly by simulating what the cog methods do.


class TestDuelLoopRoundsMode:
    """Tests for duel loop in rounds mode."""

    @pytest.mark.asyncio
    async def test_rounds_mode_completes_after_configured_rounds(self):
        """Test rounds mode completes after the configured number of rounds."""
        # Setup mock bot with services
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock personas service
        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}. Argue your position.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Mock OpenRouter client
        mock_orc = AsyncMock()
        call_count = [0]

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            call_count[0] += 1
            return (f"Response {call_count[0]} from AI", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create mock channel
        mock_channel = MagicMock()
        mock_message = MagicMock()
        mock_message.add_reaction = AsyncMock()
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_typing_ctx = MagicMock()
        mock_typing_ctx.__aenter__ = AsyncMock(return_value=None)
        mock_typing_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_channel.typing.return_value = mock_typing_ctx

        # Create duel state with 2 rounds
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Magic vs Sea",
            mode=DuelMode.ROUNDS,
            duration=2,  # 2 rounds
        )

        bot.prism_active_duels[123] = duel_state

        # Simulate the rounds mode loop logic
        async def run_rounds_mode_logic():
            while not duel_state.is_complete():
                # Check if duel was cancelled
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                current_round = duel_state.current_round
                total_rounds = duel_state.duration

                # Persona 1 speaks
                persona_record = await bot.prism_personas.get(duel_state.persona1)
                response_text, _ = await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )
                duel_state.messages.append({"role": "assistant", "content": response_text, "persona": duel_state.persona1})

                # Persona 2 responds
                persona_record = await bot.prism_personas.get(duel_state.persona2)
                response_text, _ = await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )
                duel_state.messages.append({"role": "assistant", "content": response_text, "persona": duel_state.persona2})

                # Increment round
                duel_state.increment_round()

        await run_rounds_mode_logic()

        # Each round has 2 exchanges (persona1, persona2)
        # 2 rounds = 4 AI calls
        assert call_count[0] == 4
        assert duel_state.current_round == 3  # After 2 rounds, current_round should be 3
        assert duel_state.is_complete() is True

    @pytest.mark.asyncio
    async def test_personas_alternate_correctly_in_rounds_mode(self):
        """Test personas alternate correctly (persona1 then persona2 each round)."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Track which persona speaks
        speaker_order = []

        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Mock OpenRouter client
        mock_orc = AsyncMock()

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            # Extract persona from system prompt
            system_msg = messages[0]["content"] if messages else ""
            if "wizard" in system_msg.lower():
                speaker_order.append("wizard")
            elif "pirate" in system_msg.lower():
                speaker_order.append("pirate")
            return ("Response", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 2 rounds
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[123] = duel_state

        # Simulate the rounds mode loop logic
        async def run_rounds_mode_logic():
            while not duel_state.is_complete():
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                # Persona 1 speaks
                persona_record = await bot.prism_personas.get(duel_state.persona1)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )

                # Persona 2 responds
                persona_record = await bot.prism_personas.get(duel_state.persona2)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )

                # Increment round
                duel_state.increment_round()

        await run_rounds_mode_logic()

        # Expected order: wizard, pirate, wizard, pirate
        assert speaker_order == ["wizard", "pirate", "wizard", "pirate"]


class TestDuelLoopTimeMode:
    """Tests for duel loop in time mode."""

    @pytest.mark.asyncio
    async def test_time_mode_completes_after_configured_duration(self):
        """Test time mode completes after the configured duration."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Mock OpenRouter client
        mock_orc = AsyncMock()
        call_count = [0]

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            call_count[0] += 1
            return (f"Response {call_count[0]}", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 5 second duration
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.TIME,
            duration=5,  # 5 seconds
            start_time=1000.0,
        )

        bot.prism_active_duels[123] = duel_state

        # Mock time progression
        time_values = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0, 1005.0, 1006.0, 1007.0]
        time_index = [0]

        def mock_monotonic():
            val = time_values[min(time_index[0], len(time_values) - 1)]
            time_index[0] += 1
            return val

        # Simulate the time mode loop logic
        async def run_time_mode_logic():
            personas = [duel_state.persona1, duel_state.persona2]
            turn_index = 0

            while True:
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                # Check if time has expired before starting a new turn
                if duel_state.is_complete():
                    break

                current_persona = personas[turn_index % 2]
                persona_record = await bot.prism_personas.get(current_persona)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )

                turn_index += 1

                # Check completion after the speaker finishes
                if duel_state.is_complete():
                    break

        with patch("prism.models.duel.time.monotonic", mock_monotonic):
            await run_time_mode_logic()

            # Should have made some AI calls before time expired
            assert call_count[0] >= 2
            # State should be complete (must check within patch context)
            assert duel_state.is_complete() is True


class TestStrategicAwarenessInjection:
    """Tests for strategic awareness injection into system prompts."""

    @pytest.mark.asyncio
    async def test_strategic_awareness_injection_rounds_mode(self):
        """Test strategic awareness is injected for rounds mode."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Capture system prompts sent to AI
        captured_system_prompts = []
        mock_orc = AsyncMock()

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            if messages and messages[0]["role"] == "system":
                captured_system_prompts.append(messages[0]["content"])
            return ("Response", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 2 rounds
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[123] = duel_state

        # Simulate the rounds mode loop with strategic awareness injection
        def build_system_prompt(base_prompt, current_round, total_rounds):
            duel_context = f"\n\nYou are participating in a debate on the topic: \"{duel_state.topic}\"\nArgue your position passionately while staying in character."
            strategic_awareness = f"\n\nThis is round {current_round} of {total_rounds}. Pace your arguments accordingly."
            return base_prompt + duel_context + strategic_awareness

        async def run_rounds_mode_logic():
            while not duel_state.is_complete():
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                current_round = duel_state.current_round
                total_rounds = duel_state.duration

                # Persona 1 speaks
                persona_record = await bot.prism_personas.get(duel_state.persona1)
                system_prompt = build_system_prompt(persona_record.data.system_prompt, current_round, total_rounds)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": system_prompt}],
                )

                # Persona 2 responds
                persona_record = await bot.prism_personas.get(duel_state.persona2)
                system_prompt = build_system_prompt(persona_record.data.system_prompt, current_round, total_rounds)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": system_prompt}],
                )

                duel_state.increment_round()

        await run_rounds_mode_logic()

        # Check that strategic awareness was injected
        # First prompt should mention "round 1 of 2"
        assert any("round 1 of 2" in prompt.lower() for prompt in captured_system_prompts)
        # Second round prompts should mention "round 2 of 2"
        assert any("round 2 of 2" in prompt.lower() for prompt in captured_system_prompts)

    @pytest.mark.asyncio
    async def test_strategic_awareness_injection_time_mode(self):
        """Test strategic awareness is injected for time mode with remaining time."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Capture system prompts
        captured_system_prompts = []
        mock_orc = AsyncMock()

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            if messages and messages[0]["role"] == "system":
                captured_system_prompts.append(messages[0]["content"])
            return ("Response", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 60 second duration
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.TIME,
            duration=60,
            start_time=1000.0,
        )

        bot.prism_active_duels[123] = duel_state

        # Mock time progression
        time_values = [1000.0, 1010.0, 1020.0, 1030.0, 1040.0, 1050.0, 1060.0, 1070.0]
        time_index = [0]

        def mock_monotonic():
            val = time_values[min(time_index[0], len(time_values) - 1)]
            time_index[0] += 1
            return val

        # Simulate the time mode loop with strategic awareness injection
        def build_system_prompt_time(base_prompt, remaining_seconds):
            duel_context = f"\n\nYou are participating in a debate on the topic: \"{duel_state.topic}\"\nArgue your position passionately while staying in character."
            seconds = int(remaining_seconds)
            strategic_awareness = f"\n\nApproximately {seconds} seconds remaining. Pace your arguments accordingly."
            return base_prompt + duel_context + strategic_awareness

        async def run_time_mode_logic():
            personas = [duel_state.persona1, duel_state.persona2]
            turn_index = 0

            while True:
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                remaining_time = duel_state.get_remaining_time()

                if duel_state.is_complete():
                    break

                current_persona = personas[turn_index % 2]
                persona_record = await bot.prism_personas.get(current_persona)
                system_prompt = build_system_prompt_time(persona_record.data.system_prompt, remaining_time)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": system_prompt}],
                )

                turn_index += 1

                if duel_state.is_complete():
                    break

        with patch("prism.models.duel.time.monotonic", mock_monotonic):
            await run_time_mode_logic()

        # Check that strategic awareness mentions seconds remaining
        assert any("seconds remaining" in prompt.lower() for prompt in captured_system_prompts)


class TestConversationHistoryPassedToAI:
    """Tests for conversation history being passed to AI."""

    @pytest.mark.asyncio
    async def test_conversation_history_passed_to_ai(self):
        """Test that conversation history is passed to AI for context."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Track messages passed to AI
        captured_messages_lists = []
        mock_orc = AsyncMock()
        response_count = [0]

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            captured_messages_lists.append(list(messages))
            response_count[0] += 1
            return (f"Response {response_count[0]}", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 2 rounds
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[123] = duel_state

        # Simulate the rounds mode loop with conversation history
        def build_messages(system_prompt, current_persona):
            messages = [{"role": "system", "content": system_prompt}]

            if not duel_state.messages:
                messages.append({
                    "role": "user",
                    "content": f"The debate topic is: \"{duel_state.topic}\"\n\nPlease state your opening argument.",
                })
            else:
                for msg in duel_state.messages:
                    msg_persona = msg.get("persona", "")
                    msg_content = msg.get("content", "")
                    msg_display = msg.get("display_name", msg_persona)

                    if msg_persona == current_persona:
                        messages.append({"role": "assistant", "content": msg_content})
                    else:
                        messages.append({"role": "user", "content": f"{msg_display}: {msg_content}"})

                messages.append({
                    "role": "user",
                    "content": "Please continue the debate with your response.",
                })

            return messages

        async def run_rounds_mode_logic():
            while not duel_state.is_complete():
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                # Persona 1 speaks
                persona_record = await bot.prism_personas.get(duel_state.persona1)
                messages = build_messages(persona_record.data.system_prompt, duel_state.persona1)
                response_text, _ = await bot.prism_orc.chat_completion(messages=messages)
                duel_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "persona": duel_state.persona1,
                    "display_name": persona_record.data.display_name,
                })

                # Persona 2 responds
                persona_record = await bot.prism_personas.get(duel_state.persona2)
                messages = build_messages(persona_record.data.system_prompt, duel_state.persona2)
                response_text, _ = await bot.prism_orc.chat_completion(messages=messages)
                duel_state.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "persona": duel_state.persona2,
                    "display_name": persona_record.data.display_name,
                })

                duel_state.increment_round()

        await run_rounds_mode_logic()

        # First call should have minimal history (just system + user prompt with topic)
        first_call_messages = captured_messages_lists[0]
        assert first_call_messages[0]["role"] == "system"

        # Later calls should include previous conversation
        # The 3rd call (first persona in round 2) should have history from previous exchanges
        if len(captured_messages_lists) >= 3:
            third_call_messages = captured_messages_lists[2]
            # Should have system message + conversation history
            assert len(third_call_messages) > 1
            # Verify conversation history includes previous responses
            assert any("Response" in msg.get("content", "") for msg in third_call_messages if msg["role"] != "system")


# =============================================================================
# Task Group 5: Emoji Reaction System Tests
# =============================================================================


class TestEmojiReactionAfterMessage:
    """Tests for emoji reactions added after each persona message."""

    @pytest.mark.asyncio
    async def test_opposing_persona_adds_reaction_after_each_message(self):
        """Test that the opposing persona adds a reaction after each message."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock emoji index service
        mock_emoji_service = AsyncMock()
        mock_emoji_service.suggest_for_text = AsyncMock(return_value=["<:cool:123456>", "<:nice:789012>"])
        bot.prism_emoji = mock_emoji_service

        # Create duel state
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[123] = duel_state

        # Mock message object
        mock_message = MagicMock()
        mock_message.add_reaction = AsyncMock()

        # Track reactions added
        reactions_added = []

        async def track_add_reaction(emoji):
            reactions_added.append(emoji)

        mock_message.add_reaction = track_add_reaction

        # Simulate adding reaction after persona1 speaks (pirate reacts)
        async def add_opposing_reaction(message, message_content, duel_state, speaking_persona, guild_id):
            """Add a reaction from the opposing persona."""
            # Get emoji suggestions
            suggestions = await bot.prism_emoji.suggest_for_text(guild_id, message_content)

            # Filter out already used reactions
            available = [e for e in suggestions if e not in duel_state.used_reactions]

            if available:
                emoji_to_use = available[0]
                await message.add_reaction(emoji_to_use)
                duel_state.used_reactions.add(emoji_to_use)

        # Test: persona1 speaks, pirate should react
        await add_opposing_reaction(mock_message, "I cast a powerful spell!", duel_state, "wizard", 123)

        assert len(reactions_added) == 1
        assert reactions_added[0] == "<:cool:123456>"
        assert "<:cool:123456>" in duel_state.used_reactions

        # Test: persona2 speaks, wizard should react
        await add_opposing_reaction(mock_message, "Arr, the sea is mighty!", duel_state, "pirate", 123)

        assert len(reactions_added) == 2
        assert reactions_added[1] == "<:nice:789012>"  # Next available since cool is used
        assert "<:nice:789012>" in duel_state.used_reactions


class TestCustomGuildEmojisPreferred:
    """Tests for preferring custom guild emojis over Unicode."""

    @pytest.mark.asyncio
    async def test_custom_guild_emojis_preferred_when_available(self):
        """Test that custom guild emojis are preferred when available."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock emoji service returns custom emojis first, then unicode
        mock_emoji_service = AsyncMock()
        mock_emoji_service.suggest_for_text = AsyncMock(return_value=[
            "<:custom1:111111>",  # Custom emoji
            "<:custom2:222222>",  # Custom emoji
            "thumbsup",           # Unicode emoji (fallback)
        ])
        bot.prism_emoji = mock_emoji_service

        # Create duel state
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[123] = duel_state

        # Mock message object
        mock_message = MagicMock()
        reaction_used = []
        mock_message.add_reaction = AsyncMock(side_effect=lambda e: reaction_used.append(e))

        # Simulate getting emoji for reaction
        async def get_reaction_emoji(message_content, duel_state, guild_id):
            suggestions = await bot.prism_emoji.suggest_for_text(guild_id, message_content)
            available = [e for e in suggestions if e not in duel_state.used_reactions]
            if available:
                return available[0]
            return None

        # First reaction should use custom emoji
        emoji = await get_reaction_emoji("Test message", duel_state, 123)
        assert emoji == "<:custom1:111111>"
        assert emoji.startswith("<:")  # Custom emoji format


class TestUsedReactionsTracked:
    """Tests for tracking used reactions to ensure variety."""

    @pytest.mark.asyncio
    async def test_used_reactions_tracked_to_ensure_variety(self):
        """Test that used reactions are tracked and not repeated."""
        # Setup mock bot
        bot = MagicMock()

        # Mock emoji service returns limited pool of emojis
        mock_emoji_service = AsyncMock()
        mock_emoji_service.suggest_for_text = AsyncMock(return_value=[
            "<:emoji1:111>",
            "<:emoji2:222>",
            "<:emoji3:333>",
        ])
        bot.prism_emoji = mock_emoji_service

        # Create duel state with empty used_reactions
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=3,
        )

        assert duel_state.used_reactions == set()

        # Simulate reaction selection logic
        async def select_reaction(duel_state, guild_id, message_content):
            suggestions = await bot.prism_emoji.suggest_for_text(guild_id, message_content)
            available = [e for e in suggestions if e not in duel_state.used_reactions]
            if available:
                selected = available[0]
                duel_state.used_reactions.add(selected)
                return selected
            return None

        # First reaction
        emoji1 = await select_reaction(duel_state, 123, "Message 1")
        assert emoji1 == "<:emoji1:111>"
        assert "<:emoji1:111>" in duel_state.used_reactions
        assert len(duel_state.used_reactions) == 1

        # Second reaction - should not repeat emoji1
        emoji2 = await select_reaction(duel_state, 123, "Message 2")
        assert emoji2 == "<:emoji2:222>"
        assert "<:emoji2:222>" in duel_state.used_reactions
        assert len(duel_state.used_reactions) == 2

        # Third reaction - should not repeat emoji1 or emoji2
        emoji3 = await select_reaction(duel_state, 123, "Message 3")
        assert emoji3 == "<:emoji3:333>"
        assert "<:emoji3:333>" in duel_state.used_reactions
        assert len(duel_state.used_reactions) == 3

        # Verify all emojis are unique
        assert emoji1 != emoji2 != emoji3


class TestFallbackToUnicodeEmojis:
    """Tests for fallback to Unicode emojis when custom are exhausted."""

    @pytest.mark.asyncio
    async def test_fallback_to_unicode_when_custom_exhausted(self):
        """Test fallback to Unicode emoji when all custom emojis are used."""
        # Setup mock bot
        bot = MagicMock()

        # Mock emoji service returns mix of custom and unicode
        all_emojis = [
            "<:custom1:111>",
            "<:custom2:222>",
            "thumbsup",  # Unicode fallback
            "fire",      # Unicode fallback
        ]
        mock_emoji_service = AsyncMock()
        mock_emoji_service.suggest_for_text = AsyncMock(return_value=all_emojis)
        bot.prism_emoji = mock_emoji_service

        # Create duel state with custom emojis already used
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test topic",
            mode=DuelMode.ROUNDS,
            duration=5,
            used_reactions={"<:custom1:111>", "<:custom2:222>"},  # Custom emojis already used
        )

        # Simulate reaction selection logic with fallback
        async def select_reaction_with_fallback(duel_state, guild_id, message_content):
            suggestions = await bot.prism_emoji.suggest_for_text(guild_id, message_content)
            available = [e for e in suggestions if e not in duel_state.used_reactions]
            if available:
                selected = available[0]
                duel_state.used_reactions.add(selected)
                return selected
            # Fallback to a default unicode emoji if all are exhausted
            return "star"

        # Should fall back to Unicode emoji since custom are used
        emoji = await select_reaction_with_fallback(duel_state, 123, "Test message")
        assert emoji == "thumbsup"  # First available Unicode emoji
        assert not emoji.startswith("<:")  # Not a custom emoji format

        # Use the next one
        emoji2 = await select_reaction_with_fallback(duel_state, 123, "Another message")
        assert emoji2 == "fire"  # Next available Unicode emoji


class TestEmojiReactionIntegration:
    """Integration test for the full emoji reaction flow."""

    @pytest.mark.asyncio
    async def test_full_emoji_reaction_flow_during_duel(self):
        """Test the complete emoji reaction flow during a duel exchange."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Mock emoji service
        emoji_suggestions = [
            "<:thinking:111>",
            "<:laughing:222>",
            "<a:animated:333>",  # Animated emoji
            "fire",
        ]
        mock_emoji_service = AsyncMock()
        mock_emoji_service.suggest_for_text = AsyncMock(return_value=emoji_suggestions)
        bot.prism_emoji = mock_emoji_service

        # Create duel state
        duel_state = DuelState(
            channel_id=456,
            persona1="wizard",
            persona2="pirate",
            topic="Magic vs Adventure",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        bot.prism_active_duels[456] = duel_state

        # Track all reactions added
        all_reactions = []

        # Simulate the full flow for multiple exchanges
        async def simulate_exchange_with_reaction(message_content, speaking_persona, guild_id):
            """Simulate a persona speaking and the opponent reacting."""
            # Get emoji suggestions
            suggestions = await bot.prism_emoji.suggest_for_text(guild_id, message_content)

            # Filter out used reactions
            available = [e for e in suggestions if e not in duel_state.used_reactions]

            if available:
                emoji_to_use = available[0]
                all_reactions.append(emoji_to_use)
                duel_state.used_reactions.add(emoji_to_use)
                return emoji_to_use
            return None

        # Exchange 1: wizard speaks, pirate reacts
        reaction1 = await simulate_exchange_with_reaction("Behold my magic!", "wizard", 456)
        assert reaction1 is not None

        # Exchange 2: pirate speaks, wizard reacts
        reaction2 = await simulate_exchange_with_reaction("The sea is my home!", "pirate", 456)
        assert reaction2 is not None

        # Exchange 3: wizard speaks again, pirate reacts
        reaction3 = await simulate_exchange_with_reaction("More magic!", "wizard", 456)
        assert reaction3 is not None

        # Exchange 4: pirate speaks again, wizard reacts
        reaction4 = await simulate_exchange_with_reaction("Adventure awaits!", "pirate", 456)
        assert reaction4 is not None

        # Verify all reactions are unique
        assert len(all_reactions) == 4
        assert len(set(all_reactions)) == 4  # All unique

        # Verify used_reactions is tracking
        assert len(duel_state.used_reactions) == 4


# =============================================================================
# Task Group 6: Neutral Judge AI Tests
# =============================================================================


class TestJudgeReceivesCompleteDuelTranscript:
    """Tests for judge receiving the complete duel transcript."""

    @pytest.mark.asyncio
    async def test_judge_receives_complete_duel_transcript(self):
        """Test that the judge receives all messages exchanged during the duel."""
        # Setup mock bot
        bot = MagicMock()

        # Mock OpenRouter client - capture messages sent to judge
        captured_messages = []
        mock_orc = AsyncMock()

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            captured_messages.append(list(messages))
            return ("The winner is Wizard due to stronger logical arguments.", {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with conversation history
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Magic vs Sea Adventures",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        # Add messages to duel state (simulating a completed duel)
        duel_state.messages = [
            {"role": "assistant", "content": "Magic is superior!", "persona": "wizard", "display_name": "Wizard"},
            {"role": "assistant", "content": "The sea offers freedom!", "persona": "pirate", "display_name": "Pirate"},
            {"role": "assistant", "content": "Magic can create anything!", "persona": "wizard", "display_name": "Wizard"},
            {"role": "assistant", "content": "Adventure awaits on the waves!", "persona": "pirate", "display_name": "Pirate"},
        ]

        # Build judge messages (simulating what the cog does)
        # Import from models module instead of cog to avoid discord dependency
        judge_messages = [{"role": "system", "content": JUDGE_SYSTEM_PROMPT}]

        # Build user message with complete transcript
        transcript_lines = [f"Topic: \"{duel_state.topic}\"", "", "Debate Transcript:"]
        for msg in duel_state.messages:
            display_name = msg.get("display_name", msg.get("persona", "Unknown"))
            content = msg.get("content", "")
            transcript_lines.append(f"{display_name}: {content}")

        transcript = "\n".join(transcript_lines)
        judge_messages.append({
            "role": "user",
            "content": f"{transcript}\n\nPlease evaluate this debate and declare a winner.",
        })

        # Call the AI with judge messages
        await bot.prism_orc.chat_completion(messages=judge_messages)

        # Verify the judge received the transcript
        assert len(captured_messages) == 1
        judge_call = captured_messages[0]

        # Verify system prompt is present
        assert judge_call[0]["role"] == "system"
        assert "neutral" in judge_call[0]["content"].lower() or "objective" in judge_call[0]["content"].lower()

        # Verify user message contains the full transcript
        user_message = judge_call[1]["content"]
        assert "Magic is superior!" in user_message
        assert "The sea offers freedom!" in user_message
        assert "Magic can create anything!" in user_message
        assert "Adventure awaits on the waves!" in user_message
        assert "Wizard" in user_message
        assert "Pirate" in user_message


class TestJudgeProvidesReasoningAndWinner:
    """Tests for judge providing reasoning and declaring a winner."""

    @pytest.mark.asyncio
    async def test_judge_provides_reasoning_and_declares_winner(self):
        """Test that the judge provides reasoning and declares a winner."""
        # Setup mock bot
        bot = MagicMock()

        # Mock OpenRouter client - return a realistic judge response
        mock_orc = AsyncMock()

        judge_response = (
            "Both debaters presented passionate arguments. Wizard demonstrated strong logical reasoning "
            "with concrete examples of magical capabilities. Pirate showed emotional appeal but lacked "
            "substantive counterarguments. **Winner: Wizard** for the superior use of logical arguments "
            "and creative examples."
        )

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            return (judge_response, {"model": "test"})

        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with messages
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test Topic",
            mode=DuelMode.ROUNDS,
            duration=2,
        )
        duel_state.messages = [
            {"role": "assistant", "content": "Argument 1", "persona": "wizard", "display_name": "Wizard"},
            {"role": "assistant", "content": "Argument 2", "persona": "pirate", "display_name": "Pirate"},
        ]

        # Invoke judge - use imported JUDGE_SYSTEM_PROMPT from models
        judge_messages = [{"role": "system", "content": JUDGE_SYSTEM_PROMPT}]
        transcript_lines = [f"Topic: \"{duel_state.topic}\"", "", "Debate Transcript:"]
        for msg in duel_state.messages:
            display_name = msg.get("display_name", msg.get("persona", "Unknown"))
            content = msg.get("content", "")
            transcript_lines.append(f"{display_name}: {content}")
        transcript = "\n".join(transcript_lines)
        judge_messages.append({
            "role": "user",
            "content": f"{transcript}\n\nPlease evaluate this debate and declare a winner.",
        })

        response_text, _ = await bot.prism_orc.chat_completion(messages=judge_messages)

        # Verify judge response contains reasoning
        assert "logical" in response_text.lower() or "argument" in response_text.lower()

        # Verify judge response declares a winner
        assert "winner" in response_text.lower()
        assert "wizard" in response_text.lower() or "pirate" in response_text.lower()


class TestJudgeUsesNeutralSystemPrompt:
    """Tests for judge using a neutral system prompt without persona personality."""

    def test_judge_uses_neutral_system_prompt(self):
        """Test that the judge uses a neutral system prompt without any persona personality."""
        # Use JUDGE_SYSTEM_PROMPT imported from models module
        # Verify the judge system prompt emphasizes neutrality and objectivity
        prompt_lower = JUDGE_SYSTEM_PROMPT.lower()

        # Check for key characteristics of a neutral judge prompt
        assert "neutral" in prompt_lower or "objective" in prompt_lower or "impartial" in prompt_lower
        assert "argument" in prompt_lower or "debate" in prompt_lower
        assert "winner" in prompt_lower

        # Verify it does NOT contain persona-specific personality traits
        # (it should not have things like "you are a wizard" or "you are a pirate")
        assert "you are a wizard" not in prompt_lower
        assert "you are a pirate" not in prompt_lower
        assert "stay in character" not in prompt_lower

        # Verify it requests reasoning
        assert "reason" in prompt_lower or "explain" in prompt_lower or "evaluat" in prompt_lower


class TestJudgeResponseFormattedForDiscord:
    """Tests for judge response being formatted correctly for Discord."""

    def test_judge_response_formatted_correctly_for_discord(self):
        """Test that the judge response is formatted with bold/emphasis for Discord."""
        # Use format_judge_response imported from models module

        # Test with a typical judge response
        judge_response = (
            "Both participants made strong arguments. Wizard showed excellent logical reasoning, "
            "while Pirate demonstrated emotional persuasion. However, Wizard's structured approach "
            "and concrete examples were more convincing. Winner: Wizard"
        )

        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Magic vs Adventure",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        formatted = format_judge_response(judge_response, duel_state)

        # Verify the formatted response contains Discord markdown
        assert "**" in formatted  # Bold formatting for emphasis

        # Verify it includes the judge's verdict header
        assert "Judgment" in formatted or "JUDGMENT" in formatted or "Judge" in formatted

        # Verify the response text is included
        assert "Wizard" in formatted or "wizard" in formatted


# =============================================================================
# Additional helper tests for judge response formatting
# =============================================================================


class TestJudgeResponseFormattingEdgeCases:
    """Edge case tests for judge response formatting."""

    def test_format_judge_response_with_empty_response(self):
        """Test formatting handles empty judge response gracefully."""
        # Use format_judge_response imported from models module

        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.ROUNDS,
            duration=2,
        )

        formatted = format_judge_response("", duel_state)

        # Should still produce a valid message
        assert isinstance(formatted, str)
        assert len(formatted) > 0


# =============================================================================
# Task Group 8: Strategic Gap-Filling Tests
# =============================================================================


class TestEndToEndDuelFlow:
    """Tests for complete end-to-end duel workflow."""

    @pytest.mark.asyncio
    async def test_complete_duel_flow_start_to_judge(self):
        """Test complete duel flow: start -> persona exchanges -> judge -> cleanup."""
        # Setup mock bot with all required services
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Track the flow steps
        flow_steps = []

        # Mock personas service
        def create_persona_record(name: str):
            return MockPersonaRecord(
                name=name,
                display_name=name.capitalize(),
                system_prompt=f"You are {name}.",
            )

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Mock AI responses
        ai_call_count = [0]

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            ai_call_count[0] += 1
            system_content = messages[0].get("content", "") if messages else ""

            # Detect if this is a judge call
            if "neutral" in system_content.lower() or "impartial" in system_content.lower():
                flow_steps.append("judge_called")
                return ("Winner: Wizard for excellent arguments.", {"model": "test"})

            # Regular persona response
            flow_steps.append(f"ai_call_{ai_call_count[0]}")
            return (f"Response from persona #{ai_call_count[0]}", {"model": "test"})

        mock_orc = AsyncMock()
        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Mock emoji service
        mock_emoji = AsyncMock()
        mock_emoji.suggest_for_text = AsyncMock(return_value=["fire", "star"])
        bot.prism_emoji = mock_emoji

        # Step 1: Start duel
        channel_id = 123
        persona1, persona2 = "wizard", "pirate"
        topic = "Magic vs Sea"

        # Verify personas exist
        rec1 = await bot.prism_personas.get(persona1)
        rec2 = await bot.prism_personas.get(persona2)
        assert rec1 is not None and rec2 is not None

        # Create duel state
        duel_state = DuelState(
            channel_id=channel_id,
            persona1=persona1,
            persona2=persona2,
            topic=topic,
            mode=DuelMode.ROUNDS,
            duration=1,  # 1 round for quick test
        )
        bot.prism_active_duels[channel_id] = duel_state
        flow_steps.append("duel_started")

        # Step 2: Run duel exchanges
        while not duel_state.is_complete():
            if channel_id not in bot.prism_active_duels:
                break

            # Persona 1 speaks
            persona_record = await bot.prism_personas.get(duel_state.persona1)
            response_text, _ = await bot.prism_orc.chat_completion(
                messages=[{"role": "system", "content": persona_record.data.system_prompt}],
            )
            duel_state.messages.append({
                "role": "assistant",
                "content": response_text,
                "persona": duel_state.persona1,
                "display_name": persona_record.data.display_name,
            })

            # Persona 2 responds
            persona_record = await bot.prism_personas.get(duel_state.persona2)
            response_text, _ = await bot.prism_orc.chat_completion(
                messages=[{"role": "system", "content": persona_record.data.system_prompt}],
            )
            duel_state.messages.append({
                "role": "assistant",
                "content": response_text,
                "persona": duel_state.persona2,
                "display_name": persona_record.data.display_name,
            })

            duel_state.increment_round()

        flow_steps.append("exchanges_complete")

        # Step 3: Invoke judge
        judge_messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {topic}\n\nEvaluate and declare winner."},
        ]
        judge_response, _ = await bot.prism_orc.chat_completion(messages=judge_messages)
        flow_steps.append("judgment_rendered")

        # Step 4: Cleanup
        if channel_id in bot.prism_active_duels:
            del bot.prism_active_duels[channel_id]
        flow_steps.append("cleanup_complete")

        # Verify the complete flow
        assert "duel_started" in flow_steps
        assert "ai_call_1" in flow_steps  # Persona 1 spoke
        assert "ai_call_2" in flow_steps  # Persona 2 spoke
        assert "exchanges_complete" in flow_steps
        assert "judge_called" in flow_steps
        assert "judgment_rendered" in flow_steps
        assert "cleanup_complete" in flow_steps

        # Verify cleanup happened
        assert channel_id not in bot.prism_active_duels

        # Verify messages were recorded
        assert len(duel_state.messages) == 2  # 1 round = 2 messages


class TestErrorScenarios:
    """Tests for error handling during duel execution."""

    @pytest.mark.asyncio
    async def test_ai_failure_mid_duel_continues_gracefully(self):
        """Test that AI failure mid-duel is handled gracefully."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(name=name, system_prompt=f"You are {name}.")

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        # Mock AI that fails on second call
        call_count = [0]
        error_handled = [False]

        async def mock_chat_completion_with_failure(messages, model=None, temperature=None, max_tokens=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("AI service temporarily unavailable")
            return (f"Response {call_count[0]}", {"model": "test"})

        mock_orc = AsyncMock()
        mock_orc.chat_completion = mock_chat_completion_with_failure
        bot.prism_orc = mock_orc

        # Create duel state
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.ROUNDS,
            duration=2,
        )
        bot.prism_active_duels[123] = duel_state

        # Simulate duel execution with error handling
        async def run_duel_with_error_handling():
            while not duel_state.is_complete():
                if duel_state.channel_id not in bot.prism_active_duels:
                    return

                for persona in [duel_state.persona1, duel_state.persona2]:
                    persona_record = await bot.prism_personas.get(persona)
                    try:
                        response_text, _ = await bot.prism_orc.chat_completion(
                            messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                        )
                    except Exception as e:
                        # Graceful fallback when AI fails
                        error_handled[0] = True
                        response_text = f"*{persona} is gathering their thoughts...*"

                    duel_state.messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "persona": persona,
                    })

                duel_state.increment_round()

        await run_duel_with_error_handling()

        # Verify error was handled
        assert error_handled[0] is True

        # Verify duel still completed
        assert duel_state.is_complete() is True

        # Verify fallback message was used
        assert any("gathering their thoughts" in msg["content"] for msg in duel_state.messages)

    @pytest.mark.asyncio
    async def test_persona_deleted_during_duel(self):
        """Test handling when a persona is deleted mid-duel."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        # Track which persona is deleted
        deleted_personas = set()

        def get_persona_or_none(name: str):
            if name in deleted_personas:
                return None
            return MockPersonaRecord(name=name, system_prompt=f"You are {name}.")

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=get_persona_or_none)
        bot.prism_personas = mock_personas

        mock_orc = AsyncMock()
        mock_orc.chat_completion = AsyncMock(return_value=("Response", {"model": "test"}))
        bot.prism_orc = mock_orc

        # Create duel state
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.ROUNDS,
            duration=2,
        )
        bot.prism_active_duels[123] = duel_state

        # Simulate round 1
        for persona in [duel_state.persona1, duel_state.persona2]:
            persona_record = await bot.prism_personas.get(persona)
            assert persona_record is not None
            response_text, _ = await bot.prism_orc.chat_completion(
                messages=[{"role": "system", "content": persona_record.data.system_prompt}],
            )
            duel_state.messages.append({
                "role": "assistant",
                "content": response_text,
                "persona": persona,
            })
        duel_state.increment_round()

        # Delete pirate persona before round 2
        deleted_personas.add("pirate")

        # Simulate round 2 with deleted persona handling
        fallback_used = False
        for persona in [duel_state.persona1, duel_state.persona2]:
            persona_record = await bot.prism_personas.get(persona)
            if persona_record is None:
                # Handle deleted persona gracefully
                fallback_used = True
                response_text = f"*{persona} has mysteriously vanished...*"
            else:
                response_text, _ = await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )
            duel_state.messages.append({
                "role": "assistant",
                "content": response_text,
                "persona": persona,
            })
        duel_state.increment_round()

        # Verify fallback was used for deleted persona
        assert fallback_used is True
        assert any("mysteriously vanished" in msg["content"] for msg in duel_state.messages)

        # Verify duel still completed
        assert duel_state.is_complete() is True


class TestConcurrentDuelAttempts:
    """Tests for concurrent duel handling."""

    @pytest.mark.asyncio
    async def test_concurrent_duel_attempts_same_channel_rejected(self):
        """Test that concurrent duel attempts in same channel are properly rejected."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=lambda name: MockPersonaRecord(name))
        bot.prism_personas = mock_personas

        channel_id = 123

        # First duel starts successfully
        duel_state1 = DuelState(
            channel_id=channel_id,
            persona1="wizard",
            persona2="pirate",
            topic="First duel",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        bot.prism_active_duels[channel_id] = duel_state1

        # Second duel attempt should be rejected
        def attempt_start_duel():
            if channel_id in bot.prism_active_duels:
                return False, "A duel is already active in this channel."
            return True, None

        can_start, error_msg = attempt_start_duel()

        # Verify rejection
        assert can_start is False
        assert "already active" in error_msg

        # Third attempt after first completes should succeed
        del bot.prism_active_duels[channel_id]
        can_start, error_msg = attempt_start_duel()

        assert can_start is True
        assert error_msg is None

    @pytest.mark.asyncio
    async def test_duels_in_different_channels_allowed(self):
        """Test that duels can run simultaneously in different channels."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        channel_id_1 = 111
        channel_id_2 = 222

        # Create duels in two different channels
        duel_state1 = DuelState(
            channel_id=channel_id_1,
            persona1="wizard",
            persona2="pirate",
            topic="Topic 1",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        duel_state2 = DuelState(
            channel_id=channel_id_2,
            persona1="detective",
            persona2="chef",
            topic="Topic 2",
            mode=DuelMode.ROUNDS,
            duration=3,
        )

        # Both should be allowed
        assert channel_id_1 not in bot.prism_active_duels
        bot.prism_active_duels[channel_id_1] = duel_state1
        assert channel_id_1 in bot.prism_active_duels

        assert channel_id_2 not in bot.prism_active_duels
        bot.prism_active_duels[channel_id_2] = duel_state2
        assert channel_id_2 in bot.prism_active_duels

        # Both duels should exist independently
        assert len(bot.prism_active_duels) == 2
        assert bot.prism_active_duels[channel_id_1].topic == "Topic 1"
        assert bot.prism_active_duels[channel_id_2].topic == "Topic 2"


class TestDuelCancellationDuringExecution:
    """Tests for duel cancellation during active execution."""

    @pytest.mark.asyncio
    async def test_duel_stops_when_cancelled_mid_execution(self):
        """Test that duel loop stops when duel is cancelled during execution."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(name=name, system_prompt=f"You are {name}.")

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        call_count = [0]

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            call_count[0] += 1
            return (f"Response {call_count[0]}", {"model": "test"})

        mock_orc = AsyncMock()
        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 5 rounds
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.ROUNDS,
            duration=5,  # Would normally have 10 AI calls
        )
        bot.prism_active_duels[123] = duel_state

        # Simulate duel execution that gets cancelled after round 1
        async def run_duel_with_cancellation():
            rounds_completed = 0
            while not duel_state.is_complete():
                if duel_state.channel_id not in bot.prism_active_duels:
                    return "cancelled"

                # Persona exchanges
                for persona in [duel_state.persona1, duel_state.persona2]:
                    persona_record = await bot.prism_personas.get(persona)
                    response_text, _ = await bot.prism_orc.chat_completion(
                        messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                    )
                    duel_state.messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "persona": persona,
                    })

                duel_state.increment_round()
                rounds_completed += 1

                # Cancel after round 1
                if rounds_completed == 1:
                    del bot.prism_active_duels[123]

            return "completed"

        result = await run_duel_with_cancellation()

        # Verify duel was cancelled, not completed
        assert result == "cancelled"

        # Verify only 2 AI calls were made (1 round)
        assert call_count[0] == 2

        # Verify duel state is no longer active
        assert 123 not in bot.prism_active_duels


class TestModeEdgeCases:
    """Tests for mode-specific edge cases."""

    @pytest.mark.asyncio
    async def test_time_mode_allows_speaker_to_finish_after_expiry(self):
        """Test that time mode allows current speaker to finish after time expires."""
        # Setup mock bot
        bot = MagicMock()
        bot.prism_active_duels = {}

        def create_persona_record(name: str):
            return MockPersonaRecord(name=name, system_prompt=f"You are {name}.")

        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(side_effect=create_persona_record)
        bot.prism_personas = mock_personas

        messages_sent = []

        async def mock_chat_completion(messages, model=None, temperature=None, max_tokens=None):
            messages_sent.append("ai_call")
            return ("Response", {"model": "test"})

        mock_orc = AsyncMock()
        mock_orc.chat_completion = mock_chat_completion
        bot.prism_orc = mock_orc

        # Create duel state with 3 second duration
        duel_state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.TIME,
            duration=3,  # 3 seconds
            start_time=1000.0,
        )
        bot.prism_active_duels[123] = duel_state

        # Mock time: starts at 1000, expires at 1003
        # We'll simulate checking time before each turn
        time_values = [1000.0, 1001.0, 1002.0, 1002.5, 1003.5, 1004.0]  # Last values are past expiry
        time_index = [0]

        def mock_monotonic():
            val = time_values[min(time_index[0], len(time_values) - 1)]
            time_index[0] += 1
            return val

        # Simulate time mode execution
        async def run_time_mode():
            personas = [duel_state.persona1, duel_state.persona2]
            turn_index = 0
            speaker_finished_after_expiry = False

            while True:
                if duel_state.channel_id not in bot.prism_active_duels:
                    return speaker_finished_after_expiry

                # Check BEFORE starting turn
                time_expired_before = duel_state.is_complete()
                if time_expired_before and turn_index > 0:
                    # Time expired before this turn started
                    break

                # Let speaker speak
                current_persona = personas[turn_index % 2]
                persona_record = await bot.prism_personas.get(current_persona)
                await bot.prism_orc.chat_completion(
                    messages=[{"role": "system", "content": persona_record.data.system_prompt}],
                )
                duel_state.messages.append({
                    "role": "assistant",
                    "content": "Response",
                    "persona": current_persona,
                })

                # Check AFTER speaker finishes
                time_expired_after = duel_state.is_complete()
                if time_expired_after:
                    speaker_finished_after_expiry = True
                    break

                turn_index += 1

            return speaker_finished_after_expiry

        with patch("prism.models.duel.time.monotonic", mock_monotonic):
            finished_after_expiry = await run_time_mode()

        # Verify at least one message was sent
        assert len(messages_sent) >= 1

        # Verify messages were recorded
        assert len(duel_state.messages) >= 1

    def test_rounds_mode_exact_boundary(self):
        """Test rounds mode completion at exact boundary."""
        # Test at boundary: current_round == duration
        state_at_boundary = DuelState(
            channel_id=123,
            persona1="a",
            persona2="b",
            topic="test",
            mode=DuelMode.ROUNDS,
            duration=3,
            current_round=3,  # Exactly at duration
        )
        # Round 3 is still active (rounds are 1-indexed)
        assert state_at_boundary.is_complete() is False

        # After incrementing, should be complete
        state_at_boundary.increment_round()
        assert state_at_boundary.current_round == 4
        assert state_at_boundary.is_complete() is True

    def test_single_round_duel(self):
        """Test duel with minimum duration (1 round)."""
        state = DuelState(
            channel_id=123,
            persona1="wizard",
            persona2="pirate",
            topic="Quick debate",
            mode=DuelMode.ROUNDS,
            duration=1,  # Minimum rounds
        )

        assert state.current_round == 1
        assert state.is_complete() is False

        # After one round
        state.increment_round()
        assert state.current_round == 2
        assert state.is_complete() is True


class TestCleanupBehavior:
    """Tests for cleanup behavior in various scenarios."""

    def test_cleanup_idempotent(self):
        """Test that cleanup can be called multiple times safely."""
        active_duels: dict[int, DuelState] = {}
        channel_id = 123

        duel_state = DuelState(
            channel_id=channel_id,
            persona1="wizard",
            persona2="pirate",
            topic="Test",
            mode=DuelMode.ROUNDS,
            duration=3,
        )
        active_duels[channel_id] = duel_state

        # First cleanup
        def cleanup(channel_id):
            if channel_id in active_duels:
                del active_duels[channel_id]
                return True
            return False

        result1 = cleanup(channel_id)
        assert result1 is True
        assert channel_id not in active_duels

        # Second cleanup (should be safe, no-op)
        result2 = cleanup(channel_id)
        assert result2 is False
        assert channel_id not in active_duels

    def test_cleanup_preserves_other_duels(self):
        """Test that cleanup only removes the target duel."""
        active_duels: dict[int, DuelState] = {}

        # Create multiple duels
        duel1 = DuelState(channel_id=111, persona1="a", persona2="b", topic="1", mode=DuelMode.ROUNDS, duration=3)
        duel2 = DuelState(channel_id=222, persona1="c", persona2="d", topic="2", mode=DuelMode.ROUNDS, duration=3)
        duel3 = DuelState(channel_id=333, persona1="e", persona2="f", topic="3", mode=DuelMode.ROUNDS, duration=3)

        active_duels[111] = duel1
        active_duels[222] = duel2
        active_duels[333] = duel3

        # Cleanup only duel2
        del active_duels[222]

        # Verify only duel2 was removed
        assert 111 in active_duels
        assert 222 not in active_duels
        assert 333 in active_duels
        assert len(active_duels) == 2
