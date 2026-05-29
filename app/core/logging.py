"""Structured logging setup for RetainPDF Server."""

import logging
import sys
from pathlib import Path

from app.core.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
    )
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    # Rotating file handler for persistent logs
    try:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            settings.log_dir / "server.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(file_handler)
    except Exception:
        pass

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )

    # Quiet down noisy third-party libs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
