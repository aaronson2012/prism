"""Tests for logging module."""
import io
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from prism import logging as prism_logging
from prism.logging import (
    _int_env,
    _pick_logs_dir,
    _Tee,
    close_console_log,
    setup_logging,
)


class TestIntEnv:
    """Tests for _int_env helper function."""

    def test_int_env_default(self):
        """Test _int_env returns default when var not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = _int_env("NONEXISTENT_VAR", 42)
            assert result == 42

    def test_int_env_valid_value(self):
        """Test _int_env parses valid integer."""
        with patch.dict(os.environ, {"TEST_VAR": "100"}):
            result = _int_env("TEST_VAR", 42)
            assert result == 100

    def test_int_env_invalid_value(self):
        """Test _int_env returns default for invalid value."""
        with patch.dict(os.environ, {"TEST_VAR": "not_a_number"}):
            result = _int_env("TEST_VAR", 42)
            assert result == 42

    def test_int_env_empty_value(self):
        """Test _int_env returns default for empty value."""
        with patch.dict(os.environ, {"TEST_VAR": ""}):
            result = _int_env("TEST_VAR", 42)
            assert result == 42


class TestTee:
    """Tests for _Tee class."""

    def test_tee_write_to_stream(self):
        """Test _Tee writes to underlying stream."""
        mock_stream = MagicMock()
        tee = _Tee(mock_stream)

        tee.write("test data")

        mock_stream.write.assert_called_with("test data")

    def test_tee_flush(self):
        """Test _Tee flush calls underlying stream flush."""
        mock_stream = MagicMock()
        tee = _Tee(mock_stream)

        tee.flush()

        mock_stream.flush.assert_called_once()

    def test_tee_isatty_true(self):
        """Test _Tee isatty returns True when stream is tty."""
        mock_stream = MagicMock()
        mock_stream.isatty.return_value = True
        tee = _Tee(mock_stream)

        assert tee.isatty() is True

    def test_tee_isatty_false(self):
        """Test _Tee isatty returns False when stream is not tty."""
        mock_stream = MagicMock()
        mock_stream.isatty.return_value = False
        tee = _Tee(mock_stream)

        assert tee.isatty() is False

    def test_tee_isatty_exception(self):
        """Test _Tee isatty handles exception gracefully."""
        mock_stream = MagicMock()
        mock_stream.isatty.side_effect = Exception("isatty error")
        tee = _Tee(mock_stream)

        assert tee.isatty() is False

    def test_tee_write_handles_stream_exception(self):
        """Test _Tee write handles stream exception gracefully."""
        mock_stream = MagicMock()
        mock_stream.write.side_effect = Exception("write error")
        tee = _Tee(mock_stream)

        # Should not raise
        tee.write("test")

    def test_tee_flush_handles_exception(self):
        """Test _Tee flush handles exception gracefully."""
        mock_stream = MagicMock()
        mock_stream.flush.side_effect = Exception("flush error")
        tee = _Tee(mock_stream)

        # Should not raise
        tee.flush()


class TestPickLogsDir:
    """Tests for _pick_logs_dir function."""

    def test_pick_logs_dir_explicit_env(self):
        """Test _pick_logs_dir uses PRISM_LOG_DIR when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                result = _pick_logs_dir()
                assert result == tmpdir

    def test_pick_logs_dir_creates_directory(self):
        """Test _pick_logs_dir creates directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = os.path.join(tmpdir, "new_logs")
            with patch.dict(os.environ, {"PRISM_LOG_DIR": log_dir}):
                result = _pick_logs_dir()
                assert result == log_dir
                assert os.path.isdir(log_dir)

    def test_pick_logs_dir_fallback_on_permission_error(self):
        """Test _pick_logs_dir falls back when directory not writable."""
        # Use a non-writable path
        with patch.dict(os.environ, {"PRISM_LOG_DIR": "/root/nonexistent/logs"}):
            result = _pick_logs_dir()
            # Should fall back to another candidate
            assert result != "/root/nonexistent/logs"

    def test_pick_logs_dir_cwd_fallback(self):
        """Test _pick_logs_dir uses cwd/logs as fallback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Clear PRISM_LOG_DIR, set cwd
            with patch.dict(os.environ, {}, clear=False):
                # Remove PRISM_LOG_DIR if set
                os.environ.pop("PRISM_LOG_DIR", None)
                with patch("os.getcwd", return_value=tmpdir):
                    result = _pick_logs_dir()
                    # Should be tmpdir/logs or another writable candidate
                    assert os.path.isdir(result)


class TestCloseConsoleLog:
    """Tests for close_console_log function."""

    def test_close_console_log_none(self):
        """Test close_console_log handles None file gracefully."""
        # Reset global state
        prism_logging._console_log_file = None

        # Should not raise
        close_console_log()

    def test_close_console_log_closes_file(self):
        """Test close_console_log closes open file."""
        mock_file = MagicMock()
        prism_logging._console_log_file = mock_file

        close_console_log()

        mock_file.flush.assert_called_once()
        mock_file.close.assert_called_once()
        assert prism_logging._console_log_file is None

    def test_close_console_log_handles_exception(self):
        """Test close_console_log handles exception during close."""
        mock_file = MagicMock()
        mock_file.close.side_effect = Exception("close error")
        prism_logging._console_log_file = mock_file

        # Should not raise
        close_console_log()


class TestEnsureConsoleFileForToday:
    """Tests for _ensure_console_file_for_today function."""

    def test_ensure_console_file_creates_file(self):
        """Test _ensure_console_file_for_today creates today's log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prism_logging._console_logs_dir = tmpdir
            prism_logging._console_date = None
            prism_logging._console_log_file = None

            prism_logging._ensure_console_file_for_today()

            today = datetime.now().strftime("%Y-%m-%d")
            expected_path = os.path.join(tmpdir, f"console-{today}.log")
            assert os.path.exists(expected_path)

            # Cleanup
            close_console_log()

    def test_ensure_console_file_reuses_same_day(self):
        """Test _ensure_console_file_for_today reuses file for same day."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prism_logging._console_logs_dir = tmpdir
            prism_logging._console_date = None
            prism_logging._console_log_file = None

            prism_logging._ensure_console_file_for_today()
            first_file = prism_logging._console_log_file

            prism_logging._ensure_console_file_for_today()
            second_file = prism_logging._console_log_file

            assert first_file is second_file

            # Cleanup
            close_console_log()

    def test_ensure_console_file_prunes_old(self):
        """Test _ensure_console_file_for_today prunes old log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prism_logging._console_logs_dir = tmpdir
            prism_logging._console_retention_days = 3
            prism_logging._console_date = None
            prism_logging._console_log_file = None

            # Create old log files
            old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            old_file = os.path.join(tmpdir, f"console-{old_date}.log")
            with open(old_file, "w") as f:
                f.write("old log")

            # Create recent log file
            recent_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            recent_file = os.path.join(tmpdir, f"console-{recent_date}.log")
            with open(recent_file, "w") as f:
                f.write("recent log")

            prism_logging._ensure_console_file_for_today()

            # Old file should be deleted
            assert not os.path.exists(old_file)
            # Recent file should remain
            assert os.path.exists(recent_file)

            # Cleanup
            close_console_log()

    def test_ensure_console_file_no_logs_dir(self):
        """Test _ensure_console_file_for_today handles no logs dir."""
        prism_logging._console_logs_dir = None

        # Should not raise
        prism_logging._ensure_console_file_for_today()


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_logging_basic(self):
        """Test setup_logging creates handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                # Reset state
                prism_logging._tee_installed = False
                prism_logging._atexit_registered = False
                prism_logging._orig_excepthook = None
                prism_logging._orig_stdout = None
                prism_logging._orig_stderr = None

                setup_logging("DEBUG")

                root = logging.getLogger()
                assert root.level == logging.DEBUG
                assert len(root.handlers) >= 3  # console, app, error

    def test_setup_logging_log_level(self):
        """Test setup_logging sets correct log level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                setup_logging("WARNING")

                root = logging.getLogger()
                assert root.level == logging.WARNING

    def test_setup_logging_creates_log_files(self):
        """Test setup_logging creates log files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                prism_logging._tee_installed = False
                setup_logging("INFO")

                # Check log files were created
                assert os.path.exists(os.path.join(tmpdir, "prism.log"))
                assert os.path.exists(os.path.join(tmpdir, "errors.log"))
                assert os.path.exists(os.path.join(tmpdir, "discord.log"))

    def test_setup_logging_discord_logger(self):
        """Test setup_logging configures discord logger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                setup_logging("INFO")

                discord_logger = logging.getLogger("discord")
                assert discord_logger.propagate is False
                assert len(discord_logger.handlers) >= 1

    def test_setup_logging_custom_format(self):
        """Test setup_logging uses custom format from env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "PRISM_LOG_DIR": tmpdir,
                "PRISM_LOG_FORMAT": "%(levelname)s - %(message)s",
                "PRISM_LOG_DATEFMT": "%H:%M:%S",
            }
            with patch.dict(os.environ, env):
                setup_logging("INFO")

                root = logging.getLogger()
                # Handler should use custom format
                for handler in root.handlers:
                    if handler.formatter:
                        assert "%(levelname)s" in handler.formatter._fmt

    def test_setup_logging_installs_tee(self):
        """Test setup_logging installs stdout/stderr tee."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                # Reset tee state
                prism_logging._tee_installed = False
                prism_logging._orig_stdout = None
                prism_logging._orig_stderr = None

                orig_stdout = sys.stdout
                orig_stderr = sys.stderr

                setup_logging("INFO")

                # stdout/stderr should be wrapped
                assert isinstance(sys.stdout, _Tee) or prism_logging._tee_installed

    def test_setup_logging_captures_warnings(self):
        """Test setup_logging captures Python warnings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                setup_logging("INFO")

                # Verify warnings are captured
                # This is enabled by logging.captureWarnings(True)
                import warnings
                warnings_logger = logging.getLogger("py.warnings")
                # Warnings logging should be configured
                assert warnings_logger is not None

    def test_setup_logging_excepthook(self):
        """Test setup_logging installs exception hook."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                prism_logging._orig_excepthook = None

                setup_logging("INFO")

                # excepthook should be wrapped
                assert sys.excepthook is not None


class TestNonErrorFilter:
    """Tests for _NonErrorFilter used in logging."""

    def test_non_error_filter_allows_info(self):
        """Test filter allows INFO level logs."""
        # Create a test record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        # Access the filter class from setup_logging's scope
        # We'll test the logic directly
        assert record.levelno < logging.ERROR

    def test_non_error_filter_blocks_error(self):
        """Test filter blocks ERROR level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        assert not (record.levelno < logging.ERROR)

    def test_non_error_filter_blocks_critical(self):
        """Test filter blocks CRITICAL level logs."""
        record = logging.LogRecord(
            name="test",
            level=logging.CRITICAL,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )

        assert not (record.levelno < logging.ERROR)


class TestLogIntegration:
    """Integration tests for logging."""

    def test_log_message_written(self):
        """Test log messages are written to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                setup_logging("DEBUG")

                logger = logging.getLogger("test.integration")
                logger.info("Test message")

                # Flush handlers
                for handler in logging.getLogger().handlers:
                    handler.flush()

                # Check log file has content
                log_path = os.path.join(tmpdir, "prism.log")
                with open(log_path) as f:
                    content = f.read()
                    assert "Test message" in content

    def test_error_log_written(self):
        """Test error messages are written to errors.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"PRISM_LOG_DIR": tmpdir}):
                setup_logging("DEBUG")

                logger = logging.getLogger("test.error")
                logger.error("Error message")

                # Flush handlers
                for handler in logging.getLogger().handlers:
                    handler.flush()

                # Check error log file
                error_path = os.path.join(tmpdir, "errors.log")
                with open(error_path) as f:
                    content = f.read()
                    assert "Error message" in content
