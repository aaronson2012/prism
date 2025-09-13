import logging
import os
import sys
import threading
from logging import FileHandler
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta


_tee_installed = False
_console_log_file = None  # type: ignore[var-annotated]
_console_date = None  # type: ignore[var-annotated]
_console_logs_dir = None  # type: ignore[var-annotated]
_console_retention_days = 14
_orig_excepthook = None  # type: ignore[var-annotated]


def _int_env(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, str(default)) or default)
        return v
    except Exception:
        return default


def _ensure_console_file_for_today() -> None:
    """Ensure the console tee target points at today's log file and prune old ones."""
    global _console_log_file, _console_date, _console_logs_dir, _console_retention_days
    if not _console_logs_dir:
        return
    today = datetime.now().strftime("%Y-%m-%d")
    if _console_date != today or _console_log_file is None:
        # Close previous file
        try:
            if _console_log_file and hasattr(_console_log_file, "close"):
                _console_log_file.close()
        except Exception:
            pass
        # Open new file for today
        path = os.path.join(_console_logs_dir, f"console-{today}.log")
        try:
            _console_log_file = open(path, "a", encoding="utf-8")
            _console_date = today
        except Exception:
            _console_log_file = None
            _console_date = today
    # Prune older console-*.log files beyond retention (by date in filename)
    try:
        keep_before = (datetime.now() - timedelta(days=_console_retention_days - 1)).strftime("%Y-%m-%d")
        for fn in os.listdir(_console_logs_dir):
            if not fn.startswith("console-") or not fn.endswith(".log"):
                continue
            datepart = fn[len("console-") : len("console-") + 10]
            # Keep today's and recent days; delete anything older lexicographically
            if datepart < keep_before:
                try:
                    os.remove(os.path.join(_console_logs_dir, fn))
                except Exception:
                    pass
    except Exception:
        pass


class _Tee:
    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        try:
            self._stream.write(data)
        except Exception:
            pass
        try:
            _ensure_console_file_for_today()
            if _console_log_file is not None:
                _console_log_file.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            if _console_log_file is not None:
                _console_log_file.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False


def setup_logging(level: str = "INFO") -> None:
    global _tee_installed, _console_logs_dir, _console_retention_days, _orig_excepthook

    logs_dir = os.path.join(os.getcwd(), os.getenv("PRISM_LOG_DIR", "logs"))
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        pass

    # Configure console tee directory and retention
    _console_logs_dir = logs_dir
    _console_retention_days = _int_env("CONSOLE_LOG_RETENTION_DAYS", 14)

    # Install stdout/stderr tee (rotated daily by date-named files with pruning)
    if not _tee_installed:
        try:
            _ensure_console_file_for_today()
            sys.stdout = _Tee(sys.stdout)
            sys.stderr = _Tee(sys.stderr)
            _tee_installed = True
        except Exception:
            _tee_installed = False

    root = logging.getLogger()
    root.setLevel(level.upper())

    fmt = os.getenv("PRISM_LOG_FORMAT", "%(asctime)s %(levelname)s %(name)s: %(message)s")
    datefmt = os.getenv("PRISM_LOG_DATEFMT", "%Y-%m-%d %H:%M:%S")
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # App log (INFO/DEBUG/etc.) with daily rotation
    app_retention = _int_env("LOG_RETENTION_DAYS", 14)
    app_log: FileHandler = TimedRotatingFileHandler(
        os.path.join(logs_dir, "prism.log"), when="midnight", interval=1, backupCount=app_retention, encoding="utf-8"
    )
    app_log.setFormatter(formatter)

    # Error-only log with longer retention
    err_retention = _int_env("ERROR_LOG_RETENTION_DAYS", 90)
    error_log: FileHandler = TimedRotatingFileHandler(
        os.path.join(logs_dir, "errors.log"), when="midnight", interval=1, backupCount=err_retention, encoding="utf-8"
    )
    error_log.setLevel(logging.ERROR)
    error_log.setFormatter(formatter)

    # Discord-specific log (library filter)
    discord_retention = _int_env("DISCORD_LOG_RETENTION_DAYS", 14)
    discord_handler: FileHandler = TimedRotatingFileHandler(
        os.path.join(logs_dir, "discord.log"), when="midnight", interval=1, backupCount=discord_retention, encoding="utf-8"
    )
    discord_handler.setFormatter(formatter)

    # Attach handlers
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(app_log)
    root.addHandler(error_log)

    # Attach discord handler to that logger specifically
    discord_logger = logging.getLogger("discord")
    discord_logger.addHandler(discord_handler)
    discord_level = os.getenv("DISCORD_LOG_LEVEL", "INFO").upper()
    try:
        discord_logger.setLevel(getattr(logging, discord_level, logging.INFO))
    except Exception:
        discord_logger.setLevel(logging.INFO)
    # Keep propagation so discord logs also flow to root handlers
    discord_logger.propagate = True

    logging.captureWarnings(True)

    if _orig_excepthook is None:
        _orig_excepthook = sys.excepthook

        def _log_excepthook(exc_type, exc, tb):
            try:
                logging.getLogger("unhandled").error("Unhandled exception", exc_info=(exc_type, exc, tb))
            finally:
                try:
                    _orig_excepthook(exc_type, exc, tb)  # type: ignore[misc]
                except Exception:
                    pass

        sys.excepthook = _log_excepthook  # type: ignore[assignment]

    # Log unhandled exceptions in threads (Python 3.8+)
    try:
        def _thread_excepthook(args: threading.ExceptHookArgs):  # type: ignore[name-defined]
            try:
                logging.getLogger("threading").error(
                    "Unhandled thread exception in %s",
                    getattr(args.thread, 'name', 'thread'),
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
            except Exception:
                pass
        threading.excepthook = _thread_excepthook  # type: ignore[assignment]
    except Exception:
        pass

    # Log unraisable exceptions (e.g., destructor failures) — Python 3.8+
    try:
        def _unraisable_hook(unraisable):
            try:
                obj = getattr(unraisable, 'object', None)
                msg = getattr(unraisable, 'message', None) or 'Unraisable exception'
                logging.getLogger("unraisable").error(
                    "%s in %r",
                    msg,
                    obj,
                    exc_info=(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback),
                )
            except Exception:
                pass
        sys.unraisablehook = _unraisable_hook  # type: ignore[assignment]
    except Exception:
        pass
