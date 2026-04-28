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
        [{
            "source_url": ...,
            "source_urls": [...],
            "broken_url": ...,
            "status_code": ...,
            "occurrences": ...
        }]
        """
        all_links: dict[str, set[str]] = {}  # link -> found-on pages
        for page in pages:
            for link in page.links:
                all_links.setdefault(link, set()).add(page.url)

        broken = []
        for link, sources in all_links.items():
            status = self._get_status(link)
            if status not in range(200, 400):
                source_urls = sorted(sources)
                broken.append({
                    "source_url": source_urls[0],
                    "source_urls": source_urls,
                    "broken_url": link,
                    "status_code": status,
                    "occurrences": len(source_urls),
                })
                logger.warning(
                    f"Broken link [{status}]: {link} (found on {', '.join(source_urls)})"
                )

        logger.info(f"Link check complete. {len(broken)} broken links found.")
        return broken

    def _get_status(self, url: str) -> int:
        try:
            resp = self.session.head(
                url,
                timeout=settings.crawl_timeout,
                allow_redirects=True,
            )
            status = resp.status_code
            resp.close()
            if status not in (403, 405, 501):
                return status
        except Exception:
            pass

        try:
            resp = self.session.get(
                url,
                timeout=settings.crawl_timeout,
                allow_redirects=True,
                stream=True,
            )
            status = resp.status_code
            resp.close()
            return status
        except Exception:
            return 0
