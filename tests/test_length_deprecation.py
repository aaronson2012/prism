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

    def test_settings_service_response_length_methods_removed(self):
        """Test deprecated response_length methods removed from SettingsService.

        After full migration to UserPreferencesService, the deprecated
        guild-level response_length methods should be removed.
        """
        from prism.services.settings import SettingsService

        # Verify methods no longer exist on the class
        assert not hasattr(SettingsService, "set_response_length")
        assert not hasattr(SettingsService, "resolve_response_length")
