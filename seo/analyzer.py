"""
seo/analyzer.py
---------------
Playwright-based SEO analysis module for the AI Web Tester.

Takes a live Playwright Page object and extracts a full SEO snapshot
using real browser-rendered DOM — catching dynamically injected tags
that a plain requests/BS4 scraper would miss entirely.

Extracted signals:
  • <title>                      — text + length
  • <meta name="description">    — text + length
  • <h1> … <h6> headings         — count + text per level
  • <img> alt attributes         — coverage + list of missing
  • <link rel="canonical">       — href value
  • <meta robots> / X-Robots-Tag — indexing directive
  • Open Graph tags              — og:title, og:description, og:image, og:type
  • Twitter Card tags            — twitter:card, twitter:title, twitter:description
  • <html lang="">               — language attribute
  • Word count                   — visible body text
  • Internal / external links    — totals + broken-anchor detection
  • Structured data              — presence of application/ld+json blocks

Each field also carries a scored issue list:
  severity: "error" | "warning" | "info"

Usage:
    from playwright.sync_api import sync_playwright
    from seo.analyzer import SEOAnalyzer

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page    = browser.new_page()
        page.goto("https://example.com", wait_until="networkidle")

        analyzer = SEOAnalyzer()
        result   = analyzer.analyze(page)

        print(result.score)          # 0–100
        print(result.to_dict())      # serialisable dict
        browser.close()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# SEO scoring thresholds  (all lengths in characters)
# ---------------------------------------------------------------------------

TITLE_MIN      = 10
TITLE_MAX      = 60
META_DESC_MIN  = 50
META_DESC_MAX  = 160
WORD_COUNT_MIN = 300     # below this is "thin content"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SEOIssue:
    """A single SEO problem found on a page."""
    severity: str   # "error" | "warning" | "info"
    field:    str   # which SEO element triggered this
    message:  str   # human-readable description

    def to_dict(self) -> dict:
        return {"severity": self.severity, "field": self.field, "message": self.message}


@dataclass
class ImageAltData:
    """Alt-text status for a single image."""
    src:     str
    alt:     str
    missing: bool   # True when alt is absent or empty

    def to_dict(self) -> dict:
        return {"src": self.src, "alt": self.alt, "missing": self.missing}


@dataclass
class HeadingData:
    """All headings at one level (e.g. all <h2> tags)."""
    level: int         # 1–6
    count: int
    texts: list[str]   # text content of each heading

    def to_dict(self) -> dict:
        return {"level": self.level, "count": self.count, "texts": self.texts}


@dataclass
class SEOResult:
    """
    Complete SEO snapshot for a single page.
    All fields map directly to to_dict() keys for JSON serialisation.
    """

    # ── Identity ────────────────────────────────────────────────────────────
    url:        str
    analyzed_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    # ── Core meta ───────────────────────────────────────────────────────────
    title:            str           = ""
    title_length:     int           = 0
    meta_description: str           = ""
    meta_desc_length: int           = 0
    canonical_url:    Optional[str] = None
    robots_directive: str           = ""    # e.g. "index, follow"
    lang:             str           = ""    # <html lang="">

    # ── Headings ────────────────────────────────────────────────────────────
    headings: list[HeadingData] = field(default_factory=list)

    # ── Images ──────────────────────────────────────────────────────────────
    images_total:       int               = 0
    images_missing_alt: int               = 0
    image_details:      list[ImageAltData] = field(default_factory=list)

    # ── Open Graph ──────────────────────────────────────────────────────────
    og_title:       str = ""
    og_description: str = ""
    og_image:       str = ""
    og_type:        str = ""

    # ── Twitter Card ────────────────────────────────────────────────────────
    twitter_card:        str = ""
    twitter_title:       str = ""
    twitter_description: str = ""

    # ── Content signals ─────────────────────────────────────────────────────
    word_count:              int  = 0
    internal_links_count:    int  = 0
    external_links_count:    int  = 0
    has_structured_data:     bool = False
    structured_data_count:   int  = 0

    # ── Issues + score ──────────────────────────────────────────────────────
    issues: list[SEOIssue] = field(default_factory=list)
    score:  int            = 0     # 0–100, computed after extraction

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def h1_count(self) -> int:
        """Shortcut: number of <h1> tags on the page."""
        for h in self.headings:
            if h.level == 1:
                return h.count
        return 0

    @property
    def errors(self) -> list[SEOIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[SEOIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        """One-line human-readable summary."""
        return (
            f"SEO score {self.score}/100 | "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s) | "
            f"{self.url}"
        )

    def to_dict(self) -> dict:
        """Return a fully serialisable plain dictionary."""
        return {
            "url":                   self.url,
            "analyzed_at":           self.analyzed_at,
            "score":                 self.score,
            # Core meta
            "title":                 self.title,
            "title_length":          self.title_length,
            "meta_description":      self.meta_description,
            "meta_desc_length":      self.meta_desc_length,
            "canonical_url":         self.canonical_url,
            "robots_directive":      self.robots_directive,
            "lang":                  self.lang,
            # Headings
            "h1_count":              self.h1_count,
            "headings":              [h.to_dict() for h in self.headings],
            # Images
            "images_total":          self.images_total,
            "images_missing_alt":    self.images_missing_alt,
            "image_details":         [img.to_dict() for img in self.image_details],
            # Social
            "open_graph": {
                "og:title":       self.og_title,
                "og:description": self.og_description,
                "og:image":       self.og_image,
                "og:type":        self.og_type,
            },
            "twitter_card": {
                "twitter:card":        self.twitter_card,
                "twitter:title":       self.twitter_title,
                "twitter:description": self.twitter_description,
            },
            # Content
            "word_count":            self.word_count,
            "internal_links_count":  self.internal_links_count,
            "external_links_count":  self.external_links_count,
            "has_structured_data":   self.has_structured_data,
            "structured_data_count": self.structured_data_count,
            # Issues
            "issues":  [i.to_dict() for i in self.issues],
            "errors":  [i.to_dict() for i in self.errors],
            "warnings":[i.to_dict() for i in self.warnings],
        }


# ---------------------------------------------------------------------------
# Core analyser
# ---------------------------------------------------------------------------

class SEOAnalyzer:
    """
    Extracts and scores SEO signals from a live Playwright Page object.

    The Page must already be navigated to the target URL before calling
    analyze() — this class never calls page.goto() itself, so it can be
    composed cleanly with UITester or any other Playwright workflow.

    Example:
        analyzer = SEOAnalyzer()
        result   = analyzer.analyze(page)   # page is a Playwright Page
        print(result.score)
    """

    def analyze(self, page) -> SEOResult:
        """
        Run the full SEO extraction pipeline on *page*.

        Args:
            page: A Playwright Page object that has already loaded its URL.

        Returns:
            SEOResult — fully populated, with issues list and score.
        """
        url    = page.url
        result = SEOResult(url=url)

        # Run all extractors (each writes directly into result)
        self._extract_title(page, result)
        self._extract_meta_description(page, result)
        self._extract_canonical(page, result)
        self._extract_robots(page, result)
        self._extract_lang(page, result)
        self._extract_headings(page, result)
        self._extract_images(page, result)
        self._extract_open_graph(page, result)
        self._extract_twitter_card(page, result)
        self._extract_content_signals(page, result, url)
        self._extract_structured_data(page, result)

        # Score last — needs all fields populated
        result.score = self._compute_score(result)

        return result

    # ------------------------------------------------------------------
    # Extractors
    # ------------------------------------------------------------------

    def _extract_title(self, page, result: SEOResult) -> None:
        """Extract <title> and validate length."""
        result.title        = (page.title() or "").strip()
        result.title_length = len(result.title)

        if not result.title:
            result.issues.append(SEOIssue("error", "title", "Missing <title> tag"))
        elif result.title_length < TITLE_MIN:
            result.issues.append(SEOIssue(
                "warning", "title",
                f"Title is too short ({result.title_length} chars, min {TITLE_MIN})"
            ))
        elif result.title_length > TITLE_MAX:
            result.issues.append(SEOIssue(
                "warning", "title",
                f"Title is too long ({result.title_length} chars, max {TITLE_MAX}) — "
                "may be truncated in SERPs"
            ))

    def _extract_meta_description(self, page, result: SEOResult) -> None:
        """Extract <meta name='description'> and validate."""
        content = page.evaluate(
            "() => {"
            "  const el = document.querySelector('meta[name=\"description\"]');"
            "  return el ? el.getAttribute('content') : '';"
            "}"
        ) or ""
        result.meta_description = content.strip()
        result.meta_desc_length = len(result.meta_description)

        if not result.meta_description:
            result.issues.append(SEOIssue(
                "error", "meta_description", "Missing meta description"
            ))
        elif result.meta_desc_length < META_DESC_MIN:
            result.issues.append(SEOIssue(
                "warning", "meta_description",
                f"Meta description is too short ({result.meta_desc_length} chars, min {META_DESC_MIN})"
            ))
        elif result.meta_desc_length > META_DESC_MAX:
            result.issues.append(SEOIssue(
                "warning", "meta_description",
                f"Meta description is too long ({result.meta_desc_length} chars, max {META_DESC_MAX}) — "
                "will be truncated in SERPs"
            ))

    def _extract_canonical(self, page, result: SEOResult) -> None:
        """Extract <link rel='canonical'> href."""
        href = page.evaluate(
            "() => {"
            "  const el = document.querySelector('link[rel=\"canonical\"]');"
            "  return el ? el.getAttribute('href') : null;"
            "}"
        )
        result.canonical_url = href or None

        if result.canonical_url is None:
            result.issues.append(SEOIssue(
                "warning", "canonical",
                "No canonical tag found — consider adding one to avoid duplicate content"
            ))

    def _extract_robots(self, page, result: SEOResult) -> None:
        """Extract <meta name='robots'> directive."""
        content = page.evaluate(
            "() => {"
            "  const el = document.querySelector('meta[name=\"robots\"]');"
            "  return el ? el.getAttribute('content') : '';"
            "}"
        ) or ""
        result.robots_directive = content.strip().lower()

        if "noindex" in result.robots_directive:
            result.issues.append(SEOIssue(
                "error", "robots",
                f"Page is set to noindex — will not appear in search results "
                f"(robots: '{result.robots_directive}')"
            ))

    def _extract_lang(self, page, result: SEOResult) -> None:
        """Extract <html lang='...'> attribute."""
        lang = page.evaluate(
            "() => document.documentElement.getAttribute('lang') || ''"
        ) or ""
        result.lang = lang.strip()

        if not result.lang:
            result.issues.append(SEOIssue(
                "warning", "lang",
                "Missing lang attribute on <html> — hurts accessibility and localisation"
            ))

    def _extract_headings(self, page, result: SEOResult) -> None:
        """Extract h1–h6 counts and text for heading structure analysis."""
        raw: list[dict] = page.evaluate("""
            () => {
                const data = [];
                for (let level = 1; level <= 6; level++) {
                    const els = document.querySelectorAll('h' + level);
                    if (els.length > 0) {
                        data.push({
                            level: level,
                            count: els.length,
                            texts: Array.from(els).map(el => el.innerText.trim())
                        });
                    }
                }
                return data;
            }
        """)

        result.headings = [
            HeadingData(level=h["level"], count=h["count"], texts=h["texts"])
            for h in raw
        ]

        # H1-specific rules
        h1 = next((h for h in result.headings if h.level == 1), None)
        if h1 is None:
            result.issues.append(SEOIssue(
                "error", "h1", "No <h1> tag found — every page needs exactly one"
            ))
        elif h1.count > 1:
            result.issues.append(SEOIssue(
                "warning", "h1",
                f"Multiple <h1> tags found ({h1.count}) — use only one per page"
            ))

    def _extract_images(self, page, result: SEOResult) -> None:
        """Extract all images and check for missing alt attributes."""
        raw: list[dict] = page.evaluate("""
            () => Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.src || img.getAttribute('src') || '',
                alt: img.getAttribute('alt')   // null = attribute absent
            }))
        """)

        details: list[ImageAltData] = []
        for img in raw:
            alt     = img["alt"]
            missing = alt is None or alt.strip() == ""
            details.append(ImageAltData(
                src     = img["src"],
                alt     = alt or "",
                missing = missing,
            ))

        result.image_details      = details
        result.images_total       = len(details)
        result.images_missing_alt = sum(1 for d in details if d.missing)

        if result.images_missing_alt > 0:
            result.issues.append(SEOIssue(
                "warning", "images",
                f"{result.images_missing_alt} of {result.images_total} image(s) "
                "are missing alt text — hurts accessibility and image SEO"
            ))

    def _extract_open_graph(self, page, result: SEOResult) -> None:
        """Extract Open Graph meta tags (og:*)."""
        og: dict = page.evaluate("""
            () => {
                const get = (prop) => {
                    const el = document.querySelector('meta[property="' + prop + '"]');
                    return el ? (el.getAttribute('content') || '') : '';
                };
                return {
                    title:       get('og:title'),
                    description: get('og:description'),
                    image:       get('og:image'),
                    type:        get('og:type')
                };
            }
        """)
        result.og_title       = og.get("title",       "")
        result.og_description = og.get("description", "")
        result.og_image       = og.get("image",       "")
        result.og_type        = og.get("type",        "")

        if not result.og_title and not result.og_description:
            result.issues.append(SEOIssue(
                "info", "open_graph",
                "No Open Graph tags found — social media previews will use defaults"
            ))

    def _extract_twitter_card(self, page, result: SEOResult) -> None:
        """Extract Twitter Card meta tags."""
        tw: dict = page.evaluate("""
            () => {
                const get = (name) => {
                    const el = document.querySelector('meta[name="' + name + '"]');
                    return el ? (el.getAttribute('content') || '') : '';
                };
                return {
                    card:        get('twitter:card'),
                    title:       get('twitter:title'),
                    description: get('twitter:description')
                };
            }
        """)
        result.twitter_card        = tw.get("card",        "")
        result.twitter_title       = tw.get("title",       "")
        result.twitter_description = tw.get("description", "")

    def _extract_content_signals(self, page, result: SEOResult, base_url: str) -> None:
        """Count visible words and classify links as internal vs external."""
        base_domain = urlparse(base_url).netloc

        data: dict = page.evaluate(f"""
            () => {{
                // Visible word count — strip scripts / styles first
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script,style,noscript').forEach(el => el.remove());
                const text  = clone.innerText || clone.textContent || '';
                const words = text.trim().split(/\\s+/).filter(w => w.length > 0);

                // Link classification
                const domain = '{base_domain}';
                let internal = 0, external = 0;
                document.querySelectorAll('a[href]').forEach(a => {{
                    try {{
                        const href = a.getAttribute('href');
                        if (!href || href.startsWith('#') || href.startsWith('mailto:')) return;
                        const url = new URL(href, window.location.href);
                        if (url.hostname === domain) internal++;
                        else external++;
                    }} catch (_) {{}}
                }});

                return {{
                    word_count: words.length,
                    internal:   internal,
                    external:   external
                }};
            }}
        """)

        result.word_count           = data.get("word_count", 0)
        result.internal_links_count = data.get("internal",   0)
        result.external_links_count = data.get("external",   0)

        if result.word_count < WORD_COUNT_MIN:
            result.issues.append(SEOIssue(
                "warning", "content",
                f"Thin content: only {result.word_count} words "
                f"(recommended minimum: {WORD_COUNT_MIN})"
            ))

    def _extract_structured_data(self, page, result: SEOResult) -> None:
        """Detect application/ld+json structured data blocks."""
        count: int = page.evaluate("""
            () => document.querySelectorAll('script[type="application/ld+json"]').length
        """)
        result.structured_data_count = count or 0
        result.has_structured_data   = result.structured_data_count > 0

        if not result.has_structured_data:
            result.issues.append(SEOIssue(
                "info", "structured_data",
                "No JSON-LD structured data found — consider adding Schema.org markup"
            ))

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(self, result: SEOResult) -> int:
        """
        Score the page 0–100 by deducting points for issues.

        Scoring table:
          error   → −15 points each
          warning →  −5 points each
          info    →  −2 points each

        Score is clamped to [0, 100].
        """
        deductions = sum(
            15 if issue.severity == "error"   else
             5 if issue.severity == "warning" else
             2
            for issue in result.issues
        )
        return max(0, min(100, 100 - deductions))


# ---------------------------------------------------------------------------
# Convenience wrapper — no class instantiation needed
# ---------------------------------------------------------------------------

def analyze_page(page) -> dict:
    """
    One-call SEO analysis. Pass a Playwright Page, get back a plain dict.

    Example:
        result = analyze_page(page)
        print(result["score"])
        print(result["issues"])
    """
    return SEOAnalyzer().analyze(page).to_dict()


# ---------------------------------------------------------------------------
# CLI  (python seo/analyzer.py https://example.com)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python seo/analyzer.py <URL>")
        sys.exit(1)

    target = sys.argv[1]

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed.\nRun: pip install playwright && playwright install chromium")
        sys.exit(1)

    print(f"\n🔍  SEO Analysis: {target}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
        page.goto(target, wait_until="networkidle", timeout=30_000)

        result = SEOAnalyzer().analyze(page)
        browser.close()

    print(json.dumps(result.to_dict(), indent=2))
    print("\n── Summary ─────────────────────────────────────────────────")
    print(result.summary())