"""
config/logging_config.py
------------------------
Sets up Rich-powered logging for beautiful console output.
"""

import logging
import os
import sys
from datetime import datetime, timezone


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


_configure_stdio()

try:
    from rich.logging import RichHandler
except ImportError:
    RichHandler = None


class JsonFormatter(logging.Formatter):
    """Structured JSON logs for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        message = record.getMessage()
        payload = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
            "module": record.module,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        import json

        return json.dumps(payload, ensure_ascii=True)


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("ai_web_tester")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    if logger.handlers:
        return logger

    log_json = os.getenv("LOG_JSON", "").lower() in {"1", "true", "yes"}

    if log_json:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
    elif RichHandler is not None:
        handler = RichHandler(rich_tracebacks=True)
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="[%X]",
            )
        )

    logger.addHandler(handler)
    return logger


logger = setup_logging()
