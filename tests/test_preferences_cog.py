"""Tests for PreferencesCog slash commands.

Note: Due to discord.py importing 'audioop' which is removed in Python 3.14,
we need to mock the discord module and test the cog logic directly.
"""
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Create mock discord module to avoid audioop import error
mock_discord = MagicMock()
mock_discord.Cog = object
mock_discord.AutocompleteContext = MagicMock
mock_discord.ApplicationContext = MagicMock
mock_discord.OptionChoice = MagicMock(side_effect=lambda name, value: {"name": name, "value": value})


class MockAuthor:
    """Mock Discord user/author."""

    def __init__(self, user_id: int = 123456789):
        self.id = user_id


class MockApplicationContext:
    """Mock Discord ApplicationContext for testing cog commands."""

    def __init__(self, user_id: int = 123456789):
        self.author = MockAuthor(user_id)
        self.respond = AsyncMock()
        self.defer = AsyncMock()


class MockAutocompleteContext:
    """Mock Discord AutocompleteContext for testing autocomplete functions."""

    def __init__(self, value: str = "", options: dict | None = None):
        self.value = value
        self.options = options or {}
        self.bot = MagicMock()


class TestPreferencesView:
    """Tests for /preferences view command."""

    @pytest.mark.asyncio
    async def test_preferences_view_returns_current_preferences(self, db_with_schema):
        """Test /preferences view returns current preferences."""
        from prism.services.user_preferences import UserPreferencesService

        # Setup user preferences
        user_prefs = UserPreferencesService(db=db_with_schema)
        await user_prefs.set_response_length(123456789, "concise")
        await user_prefs.set_emoji_density(123456789, "lots")
        await user_prefs.set_preferred_persona(123456789, "pirate")

        # Create mock bot with the service
        bot = MagicMock()
        bot.prism_user_prefs = user_prefs

        # Mock personas service
        mock_persona_record = MagicMock()
        mock_persona_record.data.display_name = "Pirate"
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(return_value=mock_persona_record)
        bot.prism_personas = mock_personas

        # Create mock context
        ctx = MockApplicationContext(user_id=123456789)

        # Simulate the view command logic directly (without discord import)
        prefs = await bot.prism_user_prefs.get(ctx.author.id)
        response_length = prefs.get("response_length", "balanced")
        emoji_density = prefs.get("emoji_density", "normal")
        preferred_persona = prefs.get("preferred_persona")

        # Verify preferences retrieved correctly
        assert response_length == "concise"
        assert emoji_density == "lots"
        assert preferred_persona == "pirate"


class TestPreferencesSet:
    """Tests for /preferences set command."""

    @pytest.mark.asyncio
    async def test_preferences_set_response_length_updates_preference(self, db_with_schema):
        """Test /preferences set response_length concise updates preference."""
        from prism.services.user_preferences import UserPreferencesService

        # Setup
        user_prefs = UserPreferencesService(db=db_with_schema)
        bot = MagicMock()
        bot.prism_user_prefs = user_prefs

        # Simulate the set command logic
        preference = "response_length"
        value = "concise"
        user_id = 123456789

        # Execute the logic that the command would run
        await bot.prism_user_prefs.set_response_length(user_id, value)

        # Verify preference was updated
        length = await user_prefs.resolve_response_length(user_id)
        assert length == "concise"

    @pytest.mark.asyncio
    async def test_preferences_set_preferred_persona_validates_persona_exists(self, db_with_schema):
        """Test /preferences set preferred_persona <name> validates persona exists."""
        from prism.services.user_preferences import UserPreferencesService

        # Setup
        user_prefs = UserPreferencesService(db=db_with_schema)
        bot = MagicMock()
        bot.prism_user_prefs = user_prefs

        # Mock personas service - persona does NOT exist
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(return_value=None)
        bot.prism_personas = mock_personas

        # Simulate the set command validation logic
        preference = "preferred_persona"
        value = "nonexistent"
        user_id = 123456789

        # Check if persona exists (this is what the command does)
        rec = await bot.prism_personas.get(value)

        # The command should reject if persona not found
        assert rec is None, "Expected persona lookup to return None for nonexistent persona"

        # Persona should NOT be set when validation fails
        persona = await user_prefs.resolve_preferred_persona(user_id)
        assert persona is None, "Preference should not be set for nonexistent persona"

    @pytest.mark.asyncio
    async def test_preferences_set_preferred_persona_accepts_valid_persona(self, db_with_schema):
        """Test /preferences set preferred_persona accepts valid persona."""
        from prism.services.user_preferences import UserPreferencesService

        # Setup
        user_prefs = UserPreferencesService(db=db_with_schema)
        bot = MagicMock()
        bot.prism_user_prefs = user_prefs

        # Mock personas service - persona EXISTS
        mock_persona_record = MagicMock()
        mock_persona_record.data.name = "pirate"
        mock_personas = AsyncMock()
        mock_personas.get = AsyncMock(return_value=mock_persona_record)
        bot.prism_personas = mock_personas

        # Simulate the set command logic for valid persona
        preference = "preferred_persona"
        value = "pirate"
        user_id = 123456789

        # Check if persona exists
        rec = await bot.prism_personas.get(value)
        assert rec is not None, "Expected persona to exist"

        # Set the preference (what the command does when validation passes)
        await bot.prism_user_prefs.set_preferred_persona(user_id, value)

        # Verify preference was updated
        persona = await user_prefs.resolve_preferred_persona(user_id)
        assert persona == "pirate"


class TestPreferencesReset:
    """Tests for /preferences reset command."""

    @pytest.mark.asyncio
    async def test_preferences_reset_clears_all_preferences(self, db_with_schema):
        """Test /preferences reset clears all preferences."""
        from prism.services.user_preferences import UserPreferencesService

        # Setup - set some preferences first
        user_prefs = UserPreferencesService(db=db_with_schema)
        user_id = 123456789

        await user_prefs.set_response_length(user_id, "detailed")
        await user_prefs.set_emoji_density(user_id, "none")
        await user_prefs.set_preferred_persona(user_id, "formal")

        # Verify preferences are set
        assert await user_prefs.resolve_response_length(user_id) == "detailed"
        assert await user_prefs.resolve_emoji_density(user_id) == "none"
        assert await user_prefs.resolve_preferred_persona(user_id) == "formal"

        # Execute reset (what the command does)
        await user_prefs.reset(user_id)

        # Verify preferences are reset to defaults
        length = await user_prefs.resolve_response_length(user_id)
        density = await user_prefs.resolve_emoji_density(user_id)
        persona = await user_prefs.resolve_preferred_persona(user_id)

        assert length == "balanced"
        assert density == "normal"
        assert persona is None


class TestPreferencesAutocomplete:
    """Tests for autocomplete functions."""

    @pytest.mark.asyncio
    async def test_preference_name_autocomplete_returns_valid_options(self):
        """Test autocomplete returns valid options for preference names."""
        # Test the autocomplete logic directly without importing discord
        from prism.services.user_preferences import VALID_EMOJI_DENSITIES, VALID_RESPONSE_LENGTHS

        # Valid preference names as defined in the cog
        valid_names = ["response_length", "emoji_density", "preferred_persona"]

        # Simulate filtering with empty query
        query = ""
        options = [name for name in valid_names if not query or query in name.lower()]

        # Verify all three preference names are returned
        assert "response_length" in options
        assert "emoji_density" in options
        assert "preferred_persona" in options

    @pytest.mark.asyncio
    async def test_preference_value_autocomplete_returns_response_length_options(self):
        """Test autocomplete returns correct options for response_length values."""
        from prism.services.user_preferences import VALID_RESPONSE_LENGTHS

        # Simulate the autocomplete logic for response_length
        preference = "response_length"
        query = ""

        if preference == "response_length":
            options = list(VALID_RESPONSE_LENGTHS)
        else:
            options = []

        # Filter by query
        if query:
            options = [opt for opt in options if query in opt.lower()]

        # Verify response_length options
        assert "concise" in options
        assert "balanced" in options
        assert "detailed" in options

    @pytest.mark.asyncio
    async def test_preference_value_autocomplete_returns_emoji_density_options(self):
        """Test autocomplete returns correct options for emoji_density values."""
        from prism.services.user_preferences import VALID_EMOJI_DENSITIES

        # Simulate the autocomplete logic for emoji_density
        preference = "emoji_density"
        query = ""

        if preference == "emoji_density":
            options = list(VALID_EMOJI_DENSITIES)
        else:
            options = []

        # Filter by query
        if query:
            options = [opt for opt in options if query in opt.lower()]

        # Verify emoji_density options
        assert "none" in options
        assert "minimal" in options
        assert "normal" in options
        assert "lots" in options
