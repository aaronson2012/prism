import logging
import sys
from logging import FileHandler


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    # Also log to file 'prism.log' in the working directory
    file_handler: FileHandler = logging.FileHandler("prism.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
