"""
tests/performance_checker.py
-----------------------------
Analyses page load times and flags slow pages.
"""

from config.logging_config import logger
from crawler.models import PageData

SLOW_THRESHOLD_MS = 2000   # pages slower than this are flagged


class PerformanceChecker:
    """Scores page performance based on load time and content size."""

    def check(self, pages: list[PageData]) -> list[dict]:
        """
        Returns a performance report per page.
        """
        results = []
        for page in pages:
            is_slow = page.load_time_ms > SLOW_THRESHOLD_MS
            score = self._score(page.load_time_ms)
            results.append({
                "url": page.url,
                "load_time_ms": page.load_time_ms,
                "is_slow": is_slow,
                "score": score,
            })
            if is_slow:
                logger.warning(f"Slow page ({page.load_time_ms:.0f}ms): {page.url}")

        avg = sum(r["load_time_ms"] for r in results) / max(len(results), 1)
        logger.info(f"Performance check complete. Avg load time: {avg:.0f}ms")
        return results

    def _score(self, load_ms: float) -> str:
        if load_ms < 500:
            return "Excellent"
        if load_ms < 1000:
            return "Good"
        if load_ms < 2000:
            return "Fair"
        return "Poor"
