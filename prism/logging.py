import logging
import os
import sys
from logging import FileHandler


_tee_installed = False
_console_log_file = None  # type: ignore[var-annotated]
_orig_excepthook = None  # type: ignore[var-annotated]


class _Tee:
    def __init__(self, stream, file_obj):
        self._stream = stream
        self._file = file_obj

    def write(self, data):
        try:
            self._stream.write(data)
        except Exception:
            pass
        try:
            self._file.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            self._file.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False


def setup_logging(level: str = "INFO") -> None:
    global _tee_installed, _console_log_file, _orig_excepthook

    logs_dir = os.path.join(os.getcwd(), "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        pass

    if not _tee_installed:
        try:
            _console_log_file = open(os.path.join(logs_dir, "console.log"), "a", encoding="utf-8")
            sys.stdout = _Tee(sys.stdout, _console_log_file)
            sys.stderr = _Tee(sys.stderr, _console_log_file)
            _tee_installed = True
        except Exception:
            _tee_installed = False

    root = logging.getLogger()
    root.setLevel(level.upper())

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    app_log: FileHandler = logging.FileHandler(os.path.join(logs_dir, "prism.log"), encoding="utf-8")
    app_log.setFormatter(formatter)

    error_log: FileHandler = logging.FileHandler(os.path.join(logs_dir, "errors.log"), encoding="utf-8")
    error_log.setLevel(logging.ERROR)
    error_log.setFormatter(formatter)

    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(app_log)
    root.addHandler(error_log)

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
