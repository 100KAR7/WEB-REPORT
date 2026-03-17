"""
config/logging_config.py
------------------------
Sets up Rich-powered logging for beautiful console output.
"""

import logging
from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    return logging.getLogger("ai_web_tester")


logger = setup_logging()
