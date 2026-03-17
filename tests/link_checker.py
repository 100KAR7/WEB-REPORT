"""
tests/link_checker.py
---------------------
Checks all internal links for broken URLs (non-2xx status codes).
"""

import requests
from config.settings import settings
from config.logging_config import logger
from crawler.models import PageData


class LinkChecker:
    """Validates every link found across crawled pages."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = settings.user_agent

    def check(self, pages: list[PageData]) -> list[dict]:
        """
        Returns a list of broken link records:
        [{"source_url": ..., "broken_url": ..., "status_code": ...}]
        """
        all_links: dict[str, str] = {}  # link -> found-on page
        for page in pages:
            for link in page.links:
                if link not in all_links:
                    all_links[link] = page.url

        broken = []
        for link, source in all_links.items():
            status = self._get_status(link)
            if status not in range(200, 400):
                broken.append({"source_url": source, "broken_url": link, "status_code": status})
                logger.warning(f"Broken link [{status}]: {link} (found on {source})")

        logger.info(f"Link check complete. {len(broken)} broken links found.")
        return broken

    def _get_status(self, url: str) -> int:
        try:
            resp = self.session.head(url, timeout=settings.crawl_timeout, allow_redirects=True)
            return resp.status_code
        except Exception:
            return 0
