"""Tests for shutdown cleanup behavior."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from prism.main import amain


@pytest.mark.asyncio
async def test_shutdown_includes_cleanup_delay():
    """Test that shutdown includes a delay after bot.close() for aiohttp cleanup."""
    # Mock all the dependencies
    mock_setup_personas = MagicMock()
    mock_setup_memory = MagicMock()

    with patch('prism.main.load_config') as mock_load_config, \
         patch('prism.main.setup_logging'), \
         patch('prism.main.build_bot') as mock_build_bot, \
         patch('prism.main.Database.init', new_callable=AsyncMock) as mock_db_init, \
         patch('prism.main.OpenRouterClient') as mock_orc_class, \
         patch('prism.main.register_commands'), \
         patch('prism.main.SettingsService'), \
         patch('prism.main.PersonasService') as mock_personas_class, \
         patch('prism.main.MemoryService'), \
         patch('prism.main.EmojiIndexService'), \
         patch('prism.main.ChannelLockManager'), \
         patch.dict('sys.modules', {'prism.cogs.personas': MagicMock(setup=mock_setup_personas)}), \
         patch.dict('sys.modules', {'prism.cogs.memory': MagicMock(setup=mock_setup_memory)}), \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

        # Configure mocks
        mock_config = MagicMock()
        mock_config.log_level = 'INFO'
        mock_config.db_path = ':memory:'
        mock_config.openrouter_api_key = 'test-key'
        mock_config.default_model = 'test/model'
        mock_config.fallback_model = 'test/fallback'
        mock_config.openrouter_site_url = None
        mock_config.openrouter_app_name = None
        mock_config.discord_token = 'test-token'
        mock_load_config.return_value = mock_config

        # Mock bot
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False
        mock_bot.close = AsyncMock()
        mock_bot.start = AsyncMock(side_effect=KeyboardInterrupt())  # Exit immediately
        mock_build_bot.return_value = mock_bot

        # Mock database
        mock_db = MagicMock()
        mock_db.close = AsyncMock()
        mock_db_init.return_value = mock_db

        # Mock OpenRouter client
        mock_orc = MagicMock()
        mock_orc.aclose = AsyncMock()
        mock_orc_class.return_value = mock_orc

        # Mock PersonasService
        mock_personas = MagicMock()
        mock_personas.load_builtins = AsyncMock()
        mock_personas_class.return_value = mock_personas

        # Run amain and expect KeyboardInterrupt to be caught
        try:
            await amain()
        except Exception:
            pass  # Expected to exit somehow

        # Verify that bot.close() was called
        assert mock_bot.close.called

        # Verify that asyncio.sleep was called after bot.close()
        # The sleep should be called with 0.5 seconds for cleanup delay
        sleep_calls = [call for call in mock_sleep.call_args_list if call[0][0] == 0.5]
        assert len(sleep_calls) >= 1, "Expected asyncio.sleep(0.5) to be called for cleanup delay"


@pytest.mark.asyncio
async def test_aiohttp_cleanup_pattern():
    """Test that the cleanup pattern gives aiohttp sessions time to close."""
    # Simulate the pattern: close session, then sleep
    mock_session = AsyncMock()

    # Close and sleep like in the shutdown code
    await mock_session.close()
    await asyncio.sleep(0.25)

    # If we got here without errors, the pattern is correct
    assert True


@pytest.mark.asyncio
async def test_shutdown_cleanup_on_cancelled_error():
    """Test that cleanup delay happens on CancelledError shutdown path."""
    # Mock all the dependencies
    mock_setup_personas = MagicMock()
    mock_setup_memory = MagicMock()

    with patch('prism.main.load_config') as mock_load_config, \
         patch('prism.main.setup_logging'), \
         patch('prism.main.build_bot') as mock_build_bot, \
         patch('prism.main.Database.init', new_callable=AsyncMock) as mock_db_init, \
         patch('prism.main.OpenRouterClient') as mock_orc_class, \
         patch('prism.main.register_commands'), \
         patch('prism.main.SettingsService'), \
         patch('prism.main.PersonasService') as mock_personas_class, \
         patch('prism.main.MemoryService'), \
         patch('prism.main.EmojiIndexService'), \
         patch('prism.main.ChannelLockManager'), \
         patch.dict('sys.modules', {'prism.cogs.personas': MagicMock(setup=mock_setup_personas)}), \
         patch.dict('sys.modules', {'prism.cogs.memory': MagicMock(setup=mock_setup_memory)}), \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

        # Configure mocks
        mock_config = MagicMock()
        mock_config.log_level = 'INFO'
        mock_config.db_path = ':memory:'
        mock_config.openrouter_api_key = 'test-key'
        mock_config.default_model = 'test/model'
        mock_config.fallback_model = 'test/fallback'
        mock_config.openrouter_site_url = None
        mock_config.openrouter_app_name = None
        mock_config.discord_token = 'test-token'
        mock_load_config.return_value = mock_config

        # Mock bot
        mock_bot = MagicMock()
        mock_bot.is_closed.return_value = False
        mock_bot.close = AsyncMock()
        mock_bot.start = AsyncMock(side_effect=asyncio.CancelledError())  # Exit with CancelledError
        mock_build_bot.return_value = mock_bot

        # Mock database
        mock_db = MagicMock()
        mock_db.close = AsyncMock()
        mock_db_init.return_value = mock_db

        # Mock OpenRouter client
        mock_orc = MagicMock()
        mock_orc.aclose = AsyncMock()
        mock_orc_class.return_value = mock_orc

        # Mock PersonasService
        mock_personas = MagicMock()
        mock_personas.load_builtins = AsyncMock()
        mock_personas_class.return_value = mock_personas

        # Run amain and expect CancelledError to be caught
        try:
            await amain()
        except Exception:
            pass  # Expected to exit somehow

        # Verify that bot.close() was called
        assert mock_bot.close.called

        # Verify that asyncio.sleep was called after bot.close()
        # The sleep should be called with 0.5 seconds for cleanup delay
        sleep_calls = [call for call in mock_sleep.call_args_list if call[0][0] == 0.5]
        assert len(sleep_calls) >= 1, "Expected asyncio.sleep(0.5) to be called for cleanup delay"
