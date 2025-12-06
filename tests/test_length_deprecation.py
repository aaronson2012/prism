"""Tests for /length command deprecation and cleanup verification."""
import pytest


class TestLengthCogDeprecation:
    """Tests verifying LengthCog has been properly removed."""

    def test_length_cog_module_not_importable(self):
        """Test that LengthCog module no longer exists.

        After deprecation, the length.py cog file should be deleted,
        causing imports to fail with either ModuleNotFoundError or ImportError.
        """
        with pytest.raises((ModuleNotFoundError, ImportError)):
            from prism.cogs import length  # noqa: F401

    def test_length_cog_not_loaded_in_main(self):
        """Test that main.py no longer imports or sets up LengthCog.

        The deprecation should remove:
        - from .cogs.length import setup as setup_length
        - setup_length(bot)
        """
        # Read main.py and verify LengthCog references are removed
        import os
        main_path = os.path.join(os.path.dirname(__file__), "../prism/main.py")
        with open(main_path, "r") as f:
            main_content = f.read()

        # Verify the import is removed
        assert "from .cogs.length import setup as setup_length" not in main_content
        # Verify the setup call is removed
        assert "setup_length(bot)" not in main_content
        # Verify no reference to LengthCog
        assert "LengthCog" not in main_content


class TestSettingsServiceBackwardCompatibility:
    """Tests verifying SettingsService maintains backward compatibility."""

    def test_settings_service_has_response_length_methods(self):
        """Test SettingsService still has response_length methods for migration compatibility.

        Even though user-level preferences are now in UserPreferencesService,
        the SettingsService should keep response_length methods for guild-level
        fallback and migration purposes.
        """
        from prism.services.settings import SettingsService

        # Verify methods exist on the class
        assert hasattr(SettingsService, "set_response_length")
        assert hasattr(SettingsService, "resolve_response_length")
        assert callable(getattr(SettingsService, "set_response_length"))
        assert callable(getattr(SettingsService, "resolve_response_length"))

    def test_settings_default_still_has_response_length(self):
        """Test DEFAULT_SETTINGS still includes response_length.

        The response_length key should remain in DEFAULT_SETTINGS for
        backward compatibility with existing guild settings.
        """
        from prism.services.settings import DEFAULT_SETTINGS

        assert "response_length" in DEFAULT_SETTINGS
        assert DEFAULT_SETTINGS["response_length"] == "balanced"

    @pytest.mark.asyncio
    async def test_settings_response_length_still_functional(self, db_with_schema):
        """Test SettingsService response_length methods still work.

        Guild-level response_length should remain functional for
        backward compatibility and potential future use.
        """
        from prism.services.settings import SettingsService

        service = SettingsService(db=db_with_schema)

        # Test set_response_length works
        await service.set_response_length(123456, "concise")

        # Test resolve_response_length returns the set value
        result = await service.resolve_response_length(123456)
        assert result == "concise"
