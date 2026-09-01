from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from .storage import StorageLayout


LOGGER_NAME = "alvi_studio"


def configure_logging(layout: StorageLayout) -> Path:
    """Configure bounded diagnostic logs beneath the selected storage root."""

    log_path = layout.path("logs/alvi-studio.log")
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    resolved = log_path.resolve()
    already_configured = any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename).resolve() == resolved
        for handler in logger.handlers
    )
    if not already_configured:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=4,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(threadName)s | %(name)s | %(message)s"
            )
        )
        logger.addHandler(handler)

    def record_uncaught(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        logger.critical("Uncaught application error", exc_info=(exception_type, exception, traceback))

    def record_thread_uncaught(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Uncaught thread error in %s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = record_uncaught
    threading.excepthook = record_thread_uncaught
    return log_path


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{component}")
