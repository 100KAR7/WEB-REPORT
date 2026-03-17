"""
ai_analysis/ai_analyzer.py
---------------------------
Uses the Anthropic API (Claude) to analyse page content for UX, clarity,
and actionable improvement suggestions.
"""

import anthropic

from crawler.models import PageData
from config.settings import settings
from config.logging_config import logger


SYSTEM_PROMPT = """You are an expert web analyst. Given a webpage's title and 
text content, provide a concise audit covering:
1. Content clarity (is the purpose of the page immediately clear?)
2. User experience issues (confusing language, missing calls-to-action, etc.)
3. Three specific, actionable improvement suggestions

Keep the response under 200 words and use plain language."""


class AIAnalyzer:
    """Sends page content to Claude and returns AI-generated insights."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def analyze(self, pages: list[PageData]) -> list[dict]:
        """Analyse each page and return a list of AI insight records."""
        results = []
        for page in pages:
            if not page.is_ok or not page.text_content:
                continue
            logger.info(f"AI analysing: {page.url}")
            insight = self._analyze_page(page)
            results.append({"url": page.url, "insight": insight})
        return results

    # ------------------------------------------------------------------

    def _analyze_page(self, page: PageData) -> str:
        user_message = (
            f"Page title: {page.title}\n\n"
            f"Page content (first 1500 chars):\n{page.text_content[:1500]}"
        )
        try:
            message = self.client.messages.create(
                model=settings.ai_model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return message.content[0].text
        except Exception as exc:
            logger.error(f"AI analysis failed for {page.url}: {exc}")
            return f"Analysis unavailable: {exc}"
