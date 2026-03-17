"""
crawler/models.py
-----------------
Data models for crawled page results.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PageData:
    url: str
    status_code: int
    title: str = ""
    html: str = ""
    text_content: str = ""
    meta_description: str = ""
    h1_tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)   # [{src, alt}]
    load_time_ms: float = 0.0
    error: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        return self.status_code == 200 and self.error is None
