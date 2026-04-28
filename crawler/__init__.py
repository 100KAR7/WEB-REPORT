"""Crawler package exports."""

__all__ = ["PageCrawler", "PageData"]


def __getattr__(name: str):
    if name == "PageCrawler":
        from .page_crawler import PageCrawler
        return PageCrawler
    if name == "PageData":
        from .models import PageData
        return PageData
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
