"""
Structured logging setup using Python's logging module + Rich for
beautiful console output and rotating file handler for persistence.
CRITICAL: Private keys are NEVER logged anywhere.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


_console = Console(stderr=True)
_loggers: dict[str, logging.Logger] = {}


def setup_logging(log_level: str = "INFO", log_file: str = "logs/whale_bot.log") -> None:
    """
    Configure root logging with Rich console handler and rotating file handler.

    Args:
        log_level: Logging level string (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        log_file: Path to rotating log file.
    """
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Rich console handler
    rich_handler = RichHandler(
        console=_console,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    rich_handler.setLevel(numeric_level)

    # Rotating file handler (10 MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(rich_handler)
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "web3", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info("Logging initialized at level %s", log_level)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Caches loggers to avoid duplicate handlers.

    Args:
        name: Logger name (usually __name__ of calling module).

    Returns:
        Configured Logger instance.
    """
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    return _loggers[name]
