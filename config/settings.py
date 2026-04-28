"""
config/settings.py
------------------
Central configuration for the AI Web Tester.
All settings are loaded from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        """Fallback when python-dotenv is not installed."""
        return False

load_dotenv()


@dataclass
class Settings:
    # --- Target ---
    target_url: str = ""
    max_pages: int = 10

    # --- Crawler ---
    crawl_timeout: int = 10           # seconds per request
    crawl_delay: float = 0.5          # polite delay between requests
    user_agent: str = "AIWebTester/1.0"

    # --- AI ---
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    ai_model: str = "claude-sonnet-4-20250514"
    ollama_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3")
    )
    ai_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("AI_TIMEOUT_SECONDS", "240"))
    )

    # --- Reports ---
    report_output_dir: str = "output"
    report_format: str = "html"       # "html" | "json" | "both"

    # --- Toggles ---
    run_seo: bool = True
    run_performance: bool = True
    run_ai_analysis: bool = True

    def validate_runtime(self, url: str, max_pages: int) -> None:
        """Validate user-provided runtime inputs before pipeline execution."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("`--url` must be a valid http(s) URL.")

        if max_pages < 1:
            raise ValueError("`--max-pages` must be greater than 0.")

        if self.report_format not in {"html", "json", "both"}:
            raise ValueError("`report_format` must be one of: html, json, both.")


# Singleton instance used across modules
settings = Settings()
