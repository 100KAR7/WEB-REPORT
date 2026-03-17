"""
config/settings.py
------------------
Central configuration for the AI Web Tester.
All settings are loaded from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

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

    # --- Reports ---
    report_output_dir: str = "output"
    report_format: str = "html"       # "html" | "json" | "both"

    # --- Toggles ---
    run_seo: bool = True
    run_performance: bool = True
    run_ai_analysis: bool = True


# Singleton instance used across modules
settings = Settings()
