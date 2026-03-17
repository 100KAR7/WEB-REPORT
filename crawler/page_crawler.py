"""
crawler/page_crawler.py
-----------------------
Fetches pages and extracts structured data using requests + BeautifulSoup.
"""

import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .models import PageData
from config.settings import settings
from config.logging_config import logger


class PageCrawler:
    """Crawls a website up to `max_pages` pages starting from a root URL."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = settings.user_agent
        self.visited: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self, start_url: str, max_pages: int | None = None) -> list[PageData]:
        """Crawl from start_url and return a list of PageData objects."""
        max_pages = max_pages or settings.max_pages
        queue = [start_url]
        results: list[PageData] = []
        base_domain = urlparse(start_url).netloc

        while queue and len(results) < max_pages:
            url = queue.pop(0)
            if url in self.visited:
                continue
            self.visited.add(url)

            logger.info(f"Crawling: {url}")
            page = self._fetch(url)
            results.append(page)

            # Enqueue same-domain links
            if page.is_ok:
                for link in page.links:
                    if urlparse(link).netloc == base_domain and link not in self.visited:
                        queue.append(link)

            time.sleep(settings.crawl_delay)

        return results

    def fetch_single(self, url: str) -> PageData:
        """Fetch and parse a single page."""
        return self._fetch(url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> PageData:
        start = time.time()
        try:
            resp = self.session.get(url, timeout=settings.crawl_timeout)
            load_ms = (time.time() - start) * 1000
            return self._parse(url, resp, load_ms)
        except Exception as exc:
            logger.warning(f"Failed to fetch {url}: {exc}")
            return PageData(url=url, status_code=0, error=str(exc))

    def _parse(self, url: str, resp: requests.Response, load_ms: float) -> PageData:
        soup = BeautifulSoup(resp.text, "html.parser")

        title = soup.title.string.strip() if soup.title else ""
        meta_desc = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_desc = meta_tag.get("content", "")

        h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1")]
        links = [
            urljoin(url, a["href"])
            for a in soup.find_all("a", href=True)
            if not a["href"].startswith(("#", "mailto:", "tel:"))
        ]
        images = [
            {"src": urljoin(url, img.get("src", "")), "alt": img.get("alt", "")}
            for img in soup.find_all("img")
        ]

        return PageData(
            url=url,
            status_code=resp.status_code,
            title=title,
            html=resp.text,
            text_content=soup.get_text(separator=" ", strip=True)[:5000],
            meta_description=meta_desc,
            h1_tags=h1_tags,
            links=list(set(links)),
            images=images,
            load_time_ms=round(load_ms, 2),
        )
