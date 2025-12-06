"""Tests for settings service."""
import pytest

from prism.services.settings import DEFAULT_SETTINGS, SettingsService


class TestDefaultSettings:
    """Tests for DEFAULT_SETTINGS constant."""

    def test_default_settings_has_persona(self):
        """Test DEFAULT_SETTINGS contains default_persona."""
        assert "default_persona" in DEFAULT_SETTINGS
        assert DEFAULT_SETTINGS["default_persona"] == "default"


class TestSettingsService:
    """Tests for SettingsService."""

    @pytest.mark.asyncio
    async def test_service_init(self, db_with_schema):
        """Test SettingsService initialization."""
        service = SettingsService(db=db_with_schema)
        assert service.db == db_with_schema

    @pytest.mark.asyncio
    async def test_get_creates_default(self, db_with_schema):
        """Test get creates default settings for new guild."""
        service = SettingsService(db=db_with_schema)

        settings = await service.get(123456)

        assert settings["default_persona"] == "default"

    @pytest.mark.asyncio
    async def test_get_returns_existing(self, db_with_schema):
        """Test get returns existing settings."""
        service = SettingsService(db=db_with_schema)

        # Set custom settings first
        await service.set(123456, {"default_persona": "custom", "extra": "value"})

        settings = await service.get(123456)

        assert settings["default_persona"] == "custom"
        assert settings["extra"] == "value"

    @pytest.mark.asyncio
    async def test_get_fills_missing_defaults(self, db_with_schema):
        """Test get fills in missing default keys."""
        service = SettingsService(db=db_with_schema)

        # Set partial settings (missing default_persona)
        await db_with_schema.execute(
            "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)",
            ("123456", '{"extra": "value"}'),
        )

        settings = await service.get(123456)

        # Should have both the extra value and the default
        assert settings["extra"] == "value"
        assert settings["default_persona"] == "default"

    @pytest.mark.asyncio
    async def test_get_handles_invalid_json(self, db_with_schema):
        """Test get handles invalid JSON gracefully."""
        service = SettingsService(db=db_with_schema)

        # Insert invalid JSON
        await db_with_schema.execute(
            "INSERT INTO settings (guild_id, data_json) VALUES (?, ?)",
            ("123456", "not valid json"),
        )

        settings = await service.get(123456)

        # Should return defaults
        assert settings["default_persona"] == "default"

    @pytest.mark.asyncio
    async def test_get_idempotent(self, db_with_schema):
        """Test multiple get calls return same data."""
        service = SettingsService(db=db_with_schema)

        settings1 = await service.get(123456)
        settings2 = await service.get(123456)

        assert settings1 == settings2

    @pytest.mark.asyncio
    async def test_set_creates_new(self, db_with_schema):
        """Test set creates new settings."""
        service = SettingsService(db=db_with_schema)

        await service.set(123456, {"default_persona": "custom"})

        settings = await service.get(123456)
        assert settings["default_persona"] == "custom"

    @pytest.mark.asyncio
    async def test_set_updates_existing(self, db_with_schema):
        """Test set updates existing settings."""
        service = SettingsService(db=db_with_schema)

        await service.set(123456, {"default_persona": "first"})
        await service.set(123456, {"default_persona": "second"})

        settings = await service.get(123456)
        assert settings["default_persona"] == "second"

    @pytest.mark.asyncio
    async def test_set_replaces_all_data(self, db_with_schema):
        """Test set replaces all settings data."""
        service = SettingsService(db=db_with_schema)

        await service.set(123456, {"key1": "value1", "key2": "value2"})
        await service.set(123456, {"key3": "value3"})

        settings = await service.get(123456)
        # key1 and key2 should be gone (replaced)
        assert "key1" not in settings or settings.get("key1") is None
        assert settings.get("key3") == "value3"

    @pytest.mark.asyncio
    async def test_set_persona(self, db_with_schema):
        """Test set_persona updates guild persona."""
        service = SettingsService(db=db_with_schema)

        await service.set_persona(123456, "guild", None, "custom-persona")

        settings = await service.get(123456)
        assert settings["default_persona"] == "custom-persona"

    @pytest.mark.asyncio
    async def test_set_persona_preserves_other_settings(self, db_with_schema):
        """Test set_persona preserves other settings."""
        service = SettingsService(db=db_with_schema)

        # Set initial settings with extra data
        await service.set(123456, {"default_persona": "original", "extra": "preserved"})

        # Update just persona
        await service.set_persona(123456, "guild", None, "new-persona")

        settings = await service.get(123456)
        assert settings["default_persona"] == "new-persona"
        assert settings["extra"] == "preserved"

    @pytest.mark.asyncio
    async def test_resolve_persona_name_default(self, db_with_schema):
        """Test resolve_persona_name returns default for new guild."""
        service = SettingsService(db=db_with_schema)

        name = await service.resolve_persona_name(123456, 111, 222)

        assert name == "default"

    @pytest.mark.asyncio
    async def test_resolve_persona_name_custom(self, db_with_schema):
        """Test resolve_persona_name returns custom persona."""
        service = SettingsService(db=db_with_schema)

        await service.set_persona(123456, "guild", None, "custom")

        name = await service.resolve_persona_name(123456, 111, 222)

        assert name == "custom"

    @pytest.mark.asyncio
    async def test_resolve_persona_name_ignores_channel_user(self, db_with_schema):
        """Test resolve_persona_name ignores channel and user IDs."""
        service = SettingsService(db=db_with_schema)

        await service.set_persona(123456, "guild", None, "guild-persona")

        # Different channel and user IDs should return same result
        name1 = await service.resolve_persona_name(123456, 111, 222)
        name2 = await service.resolve_persona_name(123456, 333, 444)

        assert name1 == name2 == "guild-persona"

    @pytest.mark.asyncio
    async def test_multiple_guilds_independent(self, db_with_schema):
        """Test settings are independent per guild."""
        service = SettingsService(db=db_with_schema)

        await service.set_persona(111, "guild", None, "persona-a")
        await service.set_persona(222, "guild", None, "persona-b")

        name1 = await service.resolve_persona_name(111, 0, 0)
        name2 = await service.resolve_persona_name(222, 0, 0)

        assert name1 == "persona-a"
        assert name2 == "persona-b"


class TestSettingsServiceConcurrency:
    """Tests for concurrent access scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_get_same_guild(self, db_with_schema):
        """Test concurrent get calls for same guild."""
        import asyncio

        service = SettingsService(db=db_with_schema)

        # Simulate concurrent access
        results = await asyncio.gather(
            service.get(123456),
            service.get(123456),
            service.get(123456),
        )

        # All should return same defaults
        for settings in results:
            assert settings["default_persona"] == "default"

    @pytest.mark.asyncio
    async def test_get_uses_insert_or_ignore(self, db_with_schema):
        """Test get uses INSERT OR IGNORE for race condition safety."""
        service = SettingsService(db=db_with_schema)

        # Call get twice - should not raise duplicate key error
        await service.get(123456)
        await service.get(123456)

        # Verify only one row exists
        rows = await db_with_schema.fetchall(
            "SELECT COUNT(*) FROM settings WHERE guild_id = ?",
            ("123456",),
        )
        assert rows[0][0] == 1
