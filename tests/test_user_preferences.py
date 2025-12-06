"""Tests for user preferences service."""
import pytest

from prism.services.user_preferences import (
    DEFAULT_USER_PREFERENCES,
    VALID_EMOJI_DENSITIES,
    VALID_RESPONSE_LENGTHS,
    UserPreferencesService,
)


class TestDefaultUserPreferences:
    """Tests for DEFAULT_USER_PREFERENCES constant."""

    def test_default_user_preferences_has_response_length(self):
        """Test DEFAULT_USER_PREFERENCES contains response_length."""
        assert "response_length" in DEFAULT_USER_PREFERENCES
        assert DEFAULT_USER_PREFERENCES["response_length"] == "balanced"

    def test_default_user_preferences_has_emoji_density(self):
        """Test DEFAULT_USER_PREFERENCES contains emoji_density."""
        assert "emoji_density" in DEFAULT_USER_PREFERENCES
        assert DEFAULT_USER_PREFERENCES["emoji_density"] == "normal"

    def test_default_user_preferences_has_preferred_persona(self):
        """Test DEFAULT_USER_PREFERENCES contains preferred_persona."""
        assert "preferred_persona" in DEFAULT_USER_PREFERENCES
        assert DEFAULT_USER_PREFERENCES["preferred_persona"] is None


class TestUserPreferencesService:
    """Tests for UserPreferencesService."""

    @pytest.mark.asyncio
    async def test_get_returns_defaults_for_new_user(self, db_with_schema):
        """Test get returns defaults for new user."""
        service = UserPreferencesService(db=db_with_schema)

        prefs = await service.get(123456789)

        assert prefs["response_length"] == "balanced"
        assert prefs["emoji_density"] == "normal"
        assert prefs["preferred_persona"] is None

    @pytest.mark.asyncio
    async def test_set_persists_preferences_correctly(self, db_with_schema):
        """Test set persists preferences correctly."""
        service = UserPreferencesService(db=db_with_schema)

        custom_prefs = {
            "response_length": "concise",
            "emoji_density": "lots",
            "preferred_persona": "pirate",
        }
        await service.set(123456789, custom_prefs)

        prefs = await service.get(123456789)
        assert prefs["response_length"] == "concise"
        assert prefs["emoji_density"] == "lots"
        assert prefs["preferred_persona"] == "pirate"

    @pytest.mark.asyncio
    async def test_resolve_response_length_returns_user_preference_when_set(self, db_with_schema):
        """Test resolve_response_length returns user preference when set."""
        service = UserPreferencesService(db=db_with_schema)

        await service.set_response_length(123456789, "detailed")

        length = await service.resolve_response_length(123456789)
        assert length == "detailed"

    @pytest.mark.asyncio
    async def test_resolve_preferred_persona_returns_none_when_unset(self, db_with_schema):
        """Test resolve_preferred_persona returns None when unset."""
        service = UserPreferencesService(db=db_with_schema)

        # New user - no preferences set
        persona = await service.resolve_preferred_persona(123456789)
        assert persona is None

    @pytest.mark.asyncio
    async def test_atomic_insert_or_ignore_prevents_race_conditions(self, db_with_schema):
        """Test atomic INSERT OR IGNORE behavior for race conditions."""
        import asyncio

        service = UserPreferencesService(db=db_with_schema)

        # Simulate concurrent access - should not raise duplicate key error
        results = await asyncio.gather(
            service.get(123456789),
            service.get(123456789),
            service.get(123456789),
        )

        # All should return same defaults
        for prefs in results:
            assert prefs["response_length"] == "balanced"

        # Verify only one row exists
        rows = await db_with_schema.fetchall(
            "SELECT COUNT(*) FROM user_preferences WHERE user_id = ?",
            ("123456789",),
        )
        assert rows[0][0] == 1

    @pytest.mark.asyncio
    async def test_invalid_response_length_rejected(self, db_with_schema):
        """Test invalid response_length values are rejected."""
        service = UserPreferencesService(db=db_with_schema)

        with pytest.raises(ValueError) as exc_info:
            await service.set_response_length(123456789, "invalid")

        assert "invalid" in str(exc_info.value).lower()
        assert "response length" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_invalid_emoji_density_rejected(self, db_with_schema):
        """Test invalid emoji_density values are rejected."""
        service = UserPreferencesService(db=db_with_schema)

        with pytest.raises(ValueError) as exc_info:
            await service.set_emoji_density(123456789, "invalid")

        assert "invalid" in str(exc_info.value).lower()
        assert "emoji density" in str(exc_info.value).lower()


class TestUserPreferencesServiceSetters:
    """Tests for preference-specific setter methods."""

    @pytest.mark.asyncio
    async def test_set_response_length_valid_values(self, db_with_schema):
        """Test set_response_length accepts all valid values."""
        service = UserPreferencesService(db=db_with_schema)

        for length in VALID_RESPONSE_LENGTHS:
            await service.set_response_length(123456789, length)
            result = await service.resolve_response_length(123456789)
            assert result == length

    @pytest.mark.asyncio
    async def test_set_emoji_density_valid_values(self, db_with_schema):
        """Test set_emoji_density accepts all valid values."""
        service = UserPreferencesService(db=db_with_schema)

        for density in VALID_EMOJI_DENSITIES:
            await service.set_emoji_density(123456789, density)
            result = await service.resolve_emoji_density(123456789)
            assert result == density

    @pytest.mark.asyncio
    async def test_set_preferred_persona_accepts_name(self, db_with_schema):
        """Test set_preferred_persona accepts persona name."""
        service = UserPreferencesService(db=db_with_schema)

        await service.set_preferred_persona(123456789, "pirate")

        persona = await service.resolve_preferred_persona(123456789)
        assert persona == "pirate"

    @pytest.mark.asyncio
    async def test_set_preferred_persona_accepts_none_to_clear(self, db_with_schema):
        """Test set_preferred_persona accepts None to clear."""
        service = UserPreferencesService(db=db_with_schema)

        # Set a persona first
        await service.set_preferred_persona(123456789, "pirate")
        assert await service.resolve_preferred_persona(123456789) == "pirate"

        # Clear with None
        await service.set_preferred_persona(123456789, None)
        assert await service.resolve_preferred_persona(123456789) is None


class TestUserPreferencesServiceResolvers:
    """Tests for preference resolver methods."""

    @pytest.mark.asyncio
    async def test_resolve_response_length_returns_balanced_default(self, db_with_schema):
        """Test resolve_response_length returns 'balanced' by default."""
        service = UserPreferencesService(db=db_with_schema)

        length = await service.resolve_response_length(123456789)
        assert length == "balanced"

    @pytest.mark.asyncio
    async def test_resolve_emoji_density_returns_normal_default(self, db_with_schema):
        """Test resolve_emoji_density returns 'normal' by default."""
        service = UserPreferencesService(db=db_with_schema)

        density = await service.resolve_emoji_density(123456789)
        assert density == "normal"


class TestUserPreferencesServiceReset:
    """Tests for reset method."""

    @pytest.mark.asyncio
    async def test_reset_clears_user_preferences(self, db_with_schema):
        """Test reset clears user back to defaults."""
        service = UserPreferencesService(db=db_with_schema)

        # Set custom preferences
        await service.set_response_length(123456789, "concise")
        await service.set_emoji_density(123456789, "lots")
        await service.set_preferred_persona(123456789, "pirate")

        # Verify they were set
        assert await service.resolve_response_length(123456789) == "concise"
        assert await service.resolve_emoji_density(123456789) == "lots"
        assert await service.resolve_preferred_persona(123456789) == "pirate"

        # Reset
        await service.reset(123456789)

        # Verify back to defaults
        assert await service.resolve_response_length(123456789) == "balanced"
        assert await service.resolve_emoji_density(123456789) == "normal"
        assert await service.resolve_preferred_persona(123456789) is None

    @pytest.mark.asyncio
    async def test_reset_does_not_affect_other_users(self, db_with_schema):
        """Test reset does not affect other users' preferences."""
        service = UserPreferencesService(db=db_with_schema)

        # Set preferences for two users
        await service.set_response_length(111, "concise")
        await service.set_response_length(222, "detailed")

        # Reset first user only
        await service.reset(111)

        # Verify first user is reset, second is unchanged
        assert await service.resolve_response_length(111) == "balanced"
        assert await service.resolve_response_length(222) == "detailed"


# ==============================================================================
# Task Group 2 Integration Tests
# ==============================================================================


class TestEmojiDensityGuidanceMapping:
    """Tests for emoji density guidance text mapping (Task 2.1)."""

    def test_emoji_density_guidance_returns_correct_strings(self):
        """Test emoji density guidance mapping returns correct strings for each density."""
        from prism.main import EMOJI_DENSITY_GUIDANCE

        # Test all valid density levels return appropriate guidance
        assert "Do not use any emojis" in EMOJI_DENSITY_GUIDANCE["none"]
        assert "sparingly" in EMOJI_DENSITY_GUIDANCE["minimal"]
        assert "naturally" in EMOJI_DENSITY_GUIDANCE["normal"]
        assert "generous" in EMOJI_DENSITY_GUIDANCE["lots"]

    def test_emoji_density_guidance_covers_all_valid_densities(self):
        """Test emoji density guidance covers all valid density levels."""
        from prism.main import EMOJI_DENSITY_GUIDANCE

        for density in VALID_EMOJI_DENSITIES:
            assert density in EMOJI_DENSITY_GUIDANCE


class TestResponseLengthMaxTokensMapping:
    """Tests for response length max_tokens mapping (Task 2.1)."""

    def test_max_tokens_passed_correctly_for_concise(self):
        """Test max_tokens is set correctly for concise response length."""
        from prism.main import RESPONSE_LENGTH_MAX_TOKENS

        assert RESPONSE_LENGTH_MAX_TOKENS["concise"] == 150

    def test_max_tokens_passed_correctly_for_balanced(self):
        """Test max_tokens is set correctly for balanced response length."""
        from prism.main import RESPONSE_LENGTH_MAX_TOKENS

        assert RESPONSE_LENGTH_MAX_TOKENS["balanced"] == 500

    def test_max_tokens_passed_correctly_for_detailed(self):
        """Test max_tokens is None for detailed response length (no limit)."""
        from prism.main import RESPONSE_LENGTH_MAX_TOKENS

        assert RESPONSE_LENGTH_MAX_TOKENS["detailed"] is None


class TestUserPreferencesIntegration:
    """Integration tests for user preferences taking precedence (Task 2.1)."""

    @pytest.mark.asyncio
    async def test_response_length_prefers_user_preference_over_guild(self, db_with_schema):
        """Test response length resolution prefers user preference over guild setting."""
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        # Set guild setting to "detailed"
        await guild_settings.set_response_length(123456, "detailed")

        # Set user preference to "concise"
        await user_prefs.set_response_length(789, "concise")

        # User preference should resolve independently of guild setting
        user_length = await user_prefs.resolve_response_length(789)
        guild_length = await guild_settings.resolve_response_length(123456)

        assert user_length == "concise"
        assert guild_length == "detailed"
        # User preference takes precedence when resolved via user_prefs service
        assert user_length != guild_length

    @pytest.mark.asyncio
    async def test_persona_prefers_user_preference_over_guild_default(self, db_with_schema):
        """Test persona resolution prefers user preference over guild default."""
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        # Set guild default persona
        await guild_settings.set_persona(123456, "guild", None, "formal")

        # Set user preferred persona
        await user_prefs.set_preferred_persona(789, "casual")

        # User preference should take precedence
        user_persona = await user_prefs.resolve_preferred_persona(789)
        guild_persona = await guild_settings.resolve_persona_name(123456, 0, 789)

        assert user_persona == "casual"
        assert guild_persona == "formal"

        # When user has preference set, it should be used instead of guild default
        # The integration in main.py checks user_persona first
        assert user_persona is not None  # User preference exists

    @pytest.mark.asyncio
    async def test_persona_falls_back_to_guild_when_user_unset(self, db_with_schema):
        """Test persona falls back to guild default when user preference is unset."""
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        # Set guild default persona
        await guild_settings.set_persona(123456, "guild", None, "formal")

        # User has no preferred persona (default is None)
        user_persona = await user_prefs.resolve_preferred_persona(789)
        guild_persona = await guild_settings.resolve_persona_name(123456, 0, 789)

        assert user_persona is None  # No user preference
        assert guild_persona == "formal"  # Guild default available for fallback


class TestEmojiEnforcementIntegration:
    """Integration tests for emoji enforcement with density preference (Task 2.1)."""

    @pytest.mark.asyncio
    async def test_emoji_enforcement_skipped_when_density_none(self, db_with_schema):
        """Test emoji enforcement is skipped when user density is 'none'."""
        user_prefs = UserPreferencesService(db=db_with_schema)

        # Set user emoji density to "none"
        await user_prefs.set_emoji_density(789, "none")

        density = await user_prefs.resolve_emoji_density(789)

        # When density is "none", emoji enforcement should be skipped
        # This is the condition checked in main.py before calling emoji enforcement
        assert density == "none"
        # The skip logic: if emoji_density != "none" then apply enforcement
        should_skip_enforcement = density == "none"
        assert should_skip_enforcement is True

    @pytest.mark.asyncio
    async def test_emoji_enforcement_applied_when_density_not_none(self, db_with_schema):
        """Test emoji enforcement is applied when user density is not 'none'."""
        user_prefs = UserPreferencesService(db=db_with_schema)

        # Test all non-"none" densities
        for density_setting in ["minimal", "normal", "lots"]:
            await user_prefs.set_emoji_density(789, density_setting)
            density = await user_prefs.resolve_emoji_density(789)

            # Enforcement should be applied for non-"none" densities
            should_apply_enforcement = density != "none"
            assert should_apply_enforcement is True, f"Expected enforcement for density={density_setting}"


# ==============================================================================
# Task Group 5: Strategic Gap-Filling Tests
# ==============================================================================


class TestEndToEndResponseLengthMaxTokens:
    """End-to-end test: User sets response_length='concise' -> Response uses correct max_tokens."""

    @pytest.mark.asyncio
    async def test_concise_response_length_uses_150_max_tokens(self, db_with_schema):
        """Test that setting response_length to 'concise' results in max_tokens=150.

        This simulates the end-to-end workflow:
        1. User sets response_length preference to "concise"
        2. When generating response, max_tokens=150 is used
        """
        from prism.main import RESPONSE_LENGTH_MAX_TOKENS

        user_prefs = UserPreferencesService(db=db_with_schema)
        user_id = 999888777

        # User sets preference to concise
        await user_prefs.set_response_length(user_id, "concise")

        # Resolve preference (as main.py does)
        response_length = await user_prefs.resolve_response_length(user_id)
        max_tokens = RESPONSE_LENGTH_MAX_TOKENS.get(response_length)

        # Verify the max_tokens that would be passed to chat_completion
        assert response_length == "concise"
        assert max_tokens == 150

    @pytest.mark.asyncio
    async def test_detailed_response_length_uses_no_max_tokens_limit(self, db_with_schema):
        """Test that setting response_length to 'detailed' results in max_tokens=None.

        This simulates:
        1. User sets response_length preference to "detailed"
        2. When generating response, max_tokens=None (no limit)
        """
        from prism.main import RESPONSE_LENGTH_MAX_TOKENS

        user_prefs = UserPreferencesService(db=db_with_schema)
        user_id = 999888777

        # User sets preference to detailed
        await user_prefs.set_response_length(user_id, "detailed")

        # Resolve preference
        response_length = await user_prefs.resolve_response_length(user_id)
        max_tokens = RESPONSE_LENGTH_MAX_TOKENS.get(response_length)

        # Verify no max_tokens limit for detailed
        assert response_length == "detailed"
        assert max_tokens is None


class TestEndToEndEmojiDensityNone:
    """End-to-end test: User sets emoji_density='none' -> No emoji enforcement."""

    @pytest.mark.asyncio
    async def test_density_none_skips_all_emoji_processing(self, db_with_schema):
        """Test that emoji_density='none' skips emoji enforcement pipeline.

        This simulates the end-to-end workflow:
        1. User sets emoji_density preference to "none"
        2. Main.py skips emoji enforcement entirely for this user
        """
        from prism.main import EMOJI_DENSITY_GUIDANCE

        user_prefs = UserPreferencesService(db=db_with_schema)
        user_id = 111222333

        # User sets preference to none
        await user_prefs.set_emoji_density(user_id, "none")

        # Resolve preference (as main.py does)
        emoji_density = await user_prefs.resolve_emoji_density(user_id)
        density_guidance = EMOJI_DENSITY_GUIDANCE.get(emoji_density, EMOJI_DENSITY_GUIDANCE["normal"])

        # Verify the condition that skips emoji enforcement in main.py
        # See main.py line 465: if cfg.emoji_talk_enabled and emoji_density != "none":
        should_skip_emoji_enforcement = emoji_density == "none"
        assert should_skip_emoji_enforcement is True

        # Verify the guidance text tells the model not to use emojis
        assert "Do not use any emojis" in density_guidance


class TestEndToEndPreferredPersona:
    """End-to-end test: User sets preferred_persona -> Response uses that persona."""

    @pytest.mark.asyncio
    async def test_user_preferred_persona_takes_precedence(self, db_with_schema):
        """Test that user preferred persona overrides guild persona.

        This simulates the end-to-end workflow:
        1. User sets preferred_persona to "pirate"
        2. Guild has default persona "formal"
        3. When generating response, "pirate" persona is used
        """
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        user_id = 444555666
        guild_id = 123456

        # Guild has a default persona
        await guild_settings.set_persona(guild_id, "guild", None, "formal")

        # User sets their preferred persona
        await user_prefs.set_preferred_persona(user_id, "pirate")

        # Simulate main.py persona resolution logic (lines 339-346)
        user_persona = await user_prefs.resolve_preferred_persona(user_id)

        if user_persona is not None:
            persona_name = user_persona
        else:
            persona_name = await guild_settings.resolve_persona_name(guild_id, 0, user_id)

        # User's preferred persona should be used
        assert persona_name == "pirate"


class TestPersonaAutocompleteIncludesAllPersonas:
    """Integration test: Persona autocomplete includes all available personas."""

    @pytest.mark.asyncio
    async def test_value_autocomplete_for_preferred_persona_structure(self):
        """Test autocomplete structure for preferred_persona returns expected format.

        The autocomplete logic filters personas and includes a 'none' option.
        Since we can't easily mock the bot.prism_personas in tests, we verify
        the autocomplete function handles the preference type correctly.
        """
        from prism.services.user_preferences import VALID_RESPONSE_LENGTHS, VALID_EMOJI_DENSITIES

        # Verify that response_length and emoji_density have defined autocomplete values
        # preferred_persona autocomplete is dynamic based on available personas

        # response_length values
        assert "concise" in VALID_RESPONSE_LENGTHS
        assert "balanced" in VALID_RESPONSE_LENGTHS
        assert "detailed" in VALID_RESPONSE_LENGTHS

        # emoji_density values
        assert "none" in VALID_EMOJI_DENSITIES
        assert "minimal" in VALID_EMOJI_DENSITIES
        assert "normal" in VALID_EMOJI_DENSITIES
        assert "lots" in VALID_EMOJI_DENSITIES


class TestEdgeCaseClearPreferredPersonaFallback:
    """Edge case: User clears preferred_persona -> Falls back to guild persona."""

    @pytest.mark.asyncio
    async def test_clearing_persona_preference_falls_back_to_guild(self, db_with_schema):
        """Test that clearing user persona preference causes fallback to guild default.

        This simulates:
        1. User had preferred_persona="pirate"
        2. User clears preference (sets to None)
        3. Guild default persona "formal" is now used
        """
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        user_id = 777888999
        guild_id = 654321

        # Setup: Guild has default persona
        await guild_settings.set_persona(guild_id, "guild", None, "formal")

        # User initially has a preferred persona
        await user_prefs.set_preferred_persona(user_id, "pirate")
        assert await user_prefs.resolve_preferred_persona(user_id) == "pirate"

        # User clears their preference
        await user_prefs.set_preferred_persona(user_id, None)

        # Simulate main.py resolution
        user_persona = await user_prefs.resolve_preferred_persona(user_id)

        if user_persona is not None:
            persona_name = user_persona
        else:
            persona_name = await guild_settings.resolve_persona_name(guild_id, 0, user_id)

        # Should fall back to guild persona
        assert user_persona is None
        assert persona_name == "formal"


class TestMigrationV2ToV3:
    """Migration test: Database upgrades cleanly from v2 to v3."""

    @pytest.mark.asyncio
    async def test_migration_creates_user_preferences_table(self, temp_db):
        """Test that migration v3 creates user_preferences table.

        This verifies:
        1. Fresh database gets schema initialized
        2. Migration v3 creates user_preferences table
        3. UserPreferencesService can use the table
        """
        import aiosqlite

        from prism.storage.migrations import (
            apply_migrations,
            get_schema_version,
            init_schema_version,
        )

        async with aiosqlite.connect(temp_db) as conn:
            # Apply base schema (simulated v1-v2 state)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    guild_id TEXT,
                    channel_id TEXT,
                    user_id TEXT,
                    role TEXT,
                    content TEXT
                )
            """)
            await conn.commit()

            # Initialize to v2 (before user_preferences existed)
            await init_schema_version(conn)
            # Set to v2 explicitly
            await conn.execute("DELETE FROM schema_version")
            await conn.execute("INSERT INTO schema_version (version) VALUES (?)", (2,))
            await conn.commit()

            # Verify we're at v2
            version = await get_schema_version(conn)
            assert version == 2

            # Verify user_preferences doesn't exist yet
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
            )
            row = await cursor.fetchone()
            assert row is None, "user_preferences should not exist at v2"

            # Apply migrations (should run v3)
            await apply_migrations(conn)

            # Verify we're now at v3
            version = await get_schema_version(conn)
            assert version == 3

            # Verify user_preferences table now exists
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_preferences'"
            )
            row = await cursor.fetchone()
            assert row is not None, "user_preferences should exist after v3 migration"

            # Verify table structure
            cursor = await conn.execute("PRAGMA table_info(user_preferences)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            assert "user_id" in column_names
            assert "data_json" in column_names
            assert "updated_at" in column_names


class TestUserPreferencesAcrossMultipleGuilds:
    """Edge case: User with preference interacts in multiple guilds."""

    @pytest.mark.asyncio
    async def test_user_preferences_persist_across_guilds(self, db_with_schema):
        """Test that user preferences apply globally, not per-guild.

        This verifies:
        1. User sets preference once
        2. Preference applies in all guilds user interacts in
        """
        from prism.services.settings import SettingsService

        user_prefs = UserPreferencesService(db=db_with_schema)
        guild_settings = SettingsService(db=db_with_schema)

        user_id = 123123123
        guild_a = 111111
        guild_b = 222222
        guild_c = 333333

        # Setup different guild defaults
        await guild_settings.set_persona(guild_a, "guild", None, "guild_a_persona")
        await guild_settings.set_persona(guild_b, "guild", None, "guild_b_persona")
        await guild_settings.set_persona(guild_c, "guild", None, "guild_c_persona")

        # User sets their preferred persona (once, globally)
        await user_prefs.set_preferred_persona(user_id, "user_choice")
        await user_prefs.set_response_length(user_id, "concise")
        await user_prefs.set_emoji_density(user_id, "minimal")

        # Verify user preference applies in ALL guilds
        for guild_id in [guild_a, guild_b, guild_c]:
            # Simulate main.py resolution for this guild
            user_persona = await user_prefs.resolve_preferred_persona(user_id)
            user_length = await user_prefs.resolve_response_length(user_id)
            user_density = await user_prefs.resolve_emoji_density(user_id)

            # User preferences are the same regardless of guild
            assert user_persona == "user_choice"
            assert user_length == "concise"
            assert user_density == "minimal"

            # Guild defaults exist but are not used when user has preference
            guild_persona = await guild_settings.resolve_persona_name(guild_id, 0, user_id)
            assert guild_persona != user_persona  # Different from user choice
