"""
crawler/discover_pages.py
-------------------------
Discover internal pages for a site using requests + BeautifulSoup.

This module powers the newer pipeline in ``pipeline/run_pipeline.py`` and
returns a plain ``list[str]`` of crawlable internal URLs.
"""

from __future__ import annotations

import time
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup


def discover_pages(
    start_url: str,
    max_pages: int = 10,
    verbose: bool = False,
    timeout: float = 10.0,
    crawl_delay: float = 0.0,
    user_agent: str = "AIWebTester/1.0",
) -> list[str]:
    """
    Crawl ``start_url`` and return up to ``max_pages`` internal URLs.

    The crawler keeps the traversal intentionally simple:
      - breadth-first search from the seed URL
      - same-host links only
      - fragments, mailto, tel, and javascript links are ignored
    """
    if max_pages < 1:
        return []

    session = requests.Session()
    session.headers["User-Agent"] = user_agent

    seed = _normalize_url(start_url, start_url)
    if not seed:
        return []

    base_host = urlparse(seed).netloc
    queue: deque[str] = deque([seed])
    visited: set[str] = set()
    discovered: list[str] = []

    while queue and len(discovered) < max_pages:
        url = queue.popleft()
        if url in visited:
            continue

        visited.add(url)

        if verbose:
            print(f"  • Crawling: {url}")

        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
        except Exception as exc:
            if verbose:
                print(f"    ! Skipping links on {url}: {exc}")
            continue

        discovered.append(url)

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            candidate = _normalize_url(anchor["href"], url)
            if not candidate:
                continue

            parsed = urlparse(candidate)
            if parsed.netloc != base_host:
                continue
            if candidate in visited or candidate in queue:
                continue
            if len(discovered) + len(queue) >= max_pages:
                break

            queue.append(candidate)

        if crawl_delay > 0:
            time.sleep(crawl_delay)

    return discovered


def _normalize_url(href: str, current_url: str) -> str:
    """Resolve and clean a URL so it is stable for dedupe and crawling."""
    if not href:
        return ""

    href = href.strip()
    if href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return ""

    absolute = urljoin(current_url, href)
    cleaned, _fragment = urldefrag(absolute)
    parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"}:
        return ""

    path = parsed.path or "/"
    return parsed._replace(path=path, params="", query="", fragment="").geturl()
