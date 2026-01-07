"""Tests for configuration loading."""
import os
from unittest.mock import patch

import pytest

from prism.config import Config, load_config


class TestConfigDataclass:
    """Tests for Config dataclass defaults."""

    def test_config_required_fields(self):
        """Test that Config requires discord_token and openrouter_api_key."""
        config = Config(
            discord_token="test-token",
            openrouter_api_key="test-key",
        )
        assert config.discord_token == "test-token"
        assert config.openrouter_api_key == "test-key"

    def test_config_default_values(self):
        """Test that Config has expected default values."""
        config = Config(
            discord_token="test-token",
            openrouter_api_key="test-key",
        )
        assert config.default_model == "google/gemini-3-flash-preview:online"
        assert config.fallback_model == "google/gemini-2.5-flash-lite"
        assert config.openrouter_site_url is None
        assert config.openrouter_app_name is None
        assert config.db_path == "data/prism.db"
        assert config.log_level == "INFO"
        assert config.intents_message_content is True
        assert config.emoji_talk_enabled is True
        assert config.command_guild_ids is None

    def test_config_custom_values(self):
        """Test that Config accepts custom values."""
        config = Config(
            discord_token="test-token",
            openrouter_api_key="test-key",
            default_model="custom/model",
            fallback_model="custom/fallback",
            openrouter_site_url="https://example.com",
            openrouter_app_name="MyApp",
            db_path="/custom/path.db",
            log_level="DEBUG",
            intents_message_content=False,
            emoji_talk_enabled=False,
            command_guild_ids=[123, 456],
        )
        assert config.default_model == "custom/model"
        assert config.fallback_model == "custom/fallback"
        assert config.openrouter_site_url == "https://example.com"
        assert config.openrouter_app_name == "MyApp"
        assert config.db_path == "/custom/path.db"
        assert config.log_level == "DEBUG"
        assert config.intents_message_content is False
        assert config.emoji_talk_enabled is False
        assert config.command_guild_ids == [123, 456]


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_missing_discord_token(self):
        """Test that load_config raises when DISCORD_TOKEN is missing."""
        env = {
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="DISCORD_TOKEN is required"):
                load_config()

    def test_load_config_missing_openrouter_key(self):
        """Test that load_config raises when OPENROUTER_API_KEY is missing."""
        env = {
            "DISCORD_TOKEN": "test-token",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
                load_config()

    def test_load_config_empty_discord_token(self):
        """Test that load_config raises when DISCORD_TOKEN is empty."""
        env = {
            "DISCORD_TOKEN": "   ",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="DISCORD_TOKEN is required"):
                load_config()

    def test_load_config_empty_openrouter_key(self):
        """Test that load_config raises when OPENROUTER_API_KEY is empty."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "   ",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
                load_config()

    def test_load_config_minimal(self):
        """Test load_config with minimal required env vars."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.discord_token == "test-token"
            assert config.openrouter_api_key == "test-key"
            # Check defaults are applied
            assert config.default_model == "google/gemini-3-flash-preview:online"
            assert config.log_level == "INFO"

    def test_load_config_with_all_env_vars(self):
        """Test load_config with all environment variables set."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "DEFAULT_MODEL": "custom/model",
            "FALLBACK_MODEL": "custom/fallback",
            "OPENROUTER_SITE_URL": "https://example.com",
            "OPENROUTER_APP_NAME": "TestApp",
            "PRISM_DB_PATH": "/custom/db.sqlite",
            "LOG_LEVEL": "DEBUG",
            "INTENTS_MESSAGE_CONTENT": "false",
            "EMOJI_TALK_ENABLED": "false",
            "COMMAND_GUILD_IDS": "123,456,789",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.default_model == "custom/model"
            assert config.fallback_model == "custom/fallback"
            assert config.openrouter_site_url == "https://example.com"
            assert config.openrouter_app_name == "TestApp"
            assert config.db_path == "/custom/db.sqlite"
            assert config.log_level == "DEBUG"
            assert config.intents_message_content is False
            assert config.emoji_talk_enabled is False
            assert config.command_guild_ids == [123, 456, 789]

    def test_load_config_strips_whitespace(self):
        """Test that load_config strips whitespace from values."""
        env = {
            "DISCORD_TOKEN": "  test-token  ",
            "OPENROUTER_API_KEY": "  test-key  ",
            "DEFAULT_MODEL": "  custom/model  ",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.discord_token == "test-token"
            assert config.openrouter_api_key == "test-key"
            assert config.default_model == "custom/model"

    def test_load_config_boolean_true_variants(self):
        """Test that boolean env vars accept various true values."""
        true_values = ["1", "true", "yes", "on", "TRUE", "True", "YES", "ON"]
        for val in true_values:
            env = {
                "DISCORD_TOKEN": "test-token",
                "OPENROUTER_API_KEY": "test-key",
                "INTENTS_MESSAGE_CONTENT": val,
                "EMOJI_TALK_ENABLED": val,
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_config()
                assert config.intents_message_content is True, f"Failed for value: {val}"
                assert config.emoji_talk_enabled is True, f"Failed for value: {val}"

    def test_load_config_boolean_false_variants(self):
        """Test that boolean env vars treat other values as false."""
        false_values = ["0", "false", "no", "off", "FALSE", "anything", ""]
        for val in false_values:
            env = {
                "DISCORD_TOKEN": "test-token",
                "OPENROUTER_API_KEY": "test-key",
                "INTENTS_MESSAGE_CONTENT": val,
                "EMOJI_TALK_ENABLED": val,
            }
            with patch.dict(os.environ, env, clear=True):
                config = load_config()
                assert config.intents_message_content is False, f"Failed for value: {val}"
                assert config.emoji_talk_enabled is False, f"Failed for value: {val}"

    def test_load_config_guild_ids_parsing(self):
        """Test parsing of COMMAND_GUILD_IDS."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "123, 456, 789",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids == [123, 456, 789]

    def test_load_config_guild_ids_with_semicolons(self):
        """Test that COMMAND_GUILD_IDS accepts semicolon separators."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "123;456;789",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids == [123, 456, 789]

    def test_load_config_guild_ids_mixed_separators(self):
        """Test COMMAND_GUILD_IDS with mixed separators."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "123,456;789, 1011",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids == [123, 456, 789, 1011]

    def test_load_config_guild_ids_ignores_invalid(self):
        """Test that invalid guild IDs are silently ignored."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "123,invalid,456,not-a-number,789",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids == [123, 456, 789]

    def test_load_config_guild_ids_empty(self):
        """Test that empty COMMAND_GUILD_IDS results in None."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids is None

    def test_load_config_guild_ids_whitespace_only(self):
        """Test that whitespace-only COMMAND_GUILD_IDS results in None."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "COMMAND_GUILD_IDS": "   ",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.command_guild_ids is None

    def test_load_config_empty_model_uses_default(self):
        """Test that empty model env vars fall back to defaults."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "DEFAULT_MODEL": "",
            "FALLBACK_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.default_model == "google/gemini-3-flash-preview:online"
            assert config.fallback_model == "google/gemini-2.5-flash-lite"

    def test_load_config_openrouter_urls_empty_as_none(self):
        """Test that empty OpenRouter URL/name becomes None."""
        env = {
            "DISCORD_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_SITE_URL": "",
            "OPENROUTER_APP_NAME": "",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()
            assert config.openrouter_site_url is None
            assert config.openrouter_app_name is None
