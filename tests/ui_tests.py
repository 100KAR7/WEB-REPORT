"""
tests/ui_tests.py
-----------------
Playwright-based UI testing module for the AI Web Tester.

Captures per-page:
  • Page title
  • Full-page screenshot (saved to disk)
  • All console errors and warnings
  • Basic load timing
  • Page dimensions
  • Any JS exceptions thrown during load

Installation (run once before using this module):
  pip install playwright
  playwright install chromium

Quick test without the rest of the project:
  python tests/ui_tests.py https://example.com
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------

@dataclass
class UITestResult:
    """All data captured from a single page visit."""

    # ── Identification ──────────────────────────────────────────────────────
    url: str
    tested_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # ── Page metadata ───────────────────────────────────────────────────────
    title: str          = ""
    final_url: str      = ""       # after redirects
    status_code: int    = 0
    load_time_ms: float = 0.0
    page_width: int     = 0
    page_height: int    = 0

    # ── Screenshot ──────────────────────────────────────────────────────────
    screenshot_path: Optional[str] = None

    # ── Console output ──────────────────────────────────────────────────────
    console_errors:   list[str] = field(default_factory=list)
    console_warnings: list[str] = field(default_factory=list)
    console_logs:     list[str] = field(default_factory=list)

    # ── JS Exceptions ───────────────────────────────────────────────────────
    js_exceptions: list[str] = field(default_factory=list)

    # ── Status ──────────────────────────────────────────────────────────────
    success: bool           = False
    error:   Optional[str]  = None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def has_errors(self) -> bool:
        """True if any console errors or JS exceptions were recorded."""
        return bool(self.console_errors or self.js_exceptions)

    def summary(self) -> str:
        """One-line human-readable summary of the test result."""
        status = "✓ PASS" if self.success and not self.has_errors() else "✗ FAIL"
        errs   = len(self.console_errors) + len(self.js_exceptions)
        return (
            f"{status}  {self.url}\n"
            f"       title={self.title!r}  load={self.load_time_ms:.0f}ms  "
            f"errors={errs}  screenshot={self.screenshot_path}"
        )

    def to_dict(self) -> dict:
        """Serialisable dictionary — ready for JSON reports."""
        return {
            "url":              self.url,
            "tested_at":        self.tested_at,
            "title":            self.title,
            "final_url":        self.final_url,
            "status_code":      self.status_code,
            "load_time_ms":     self.load_time_ms,
            "page_width":       self.page_width,
            "page_height":      self.page_height,
            "screenshot_path":  self.screenshot_path,
            "console_errors":   self.console_errors,
            "console_warnings": self.console_warnings,
            "console_logs":     self.console_logs,
            "js_exceptions":    self.js_exceptions,
            "success":          self.success,
            "error":            self.error,
        }


# ---------------------------------------------------------------------------
# Core tester class
# ---------------------------------------------------------------------------

class UITester:
    """
    Runs Playwright-based UI tests against one or more URLs.

    Usage:
        tester = UITester(screenshot_dir="output/screenshots")
        result = tester.test_page("https://example.com")
        print(result.summary())

        # Or test many pages at once:
        results = tester.test_pages(["https://example.com/about", "https://example.com/contact"])
    """

    def __init__(
        self,
        screenshot_dir: str  = "output/screenshots",
        browser:        str  = "chromium",     # "chromium" | "firefox" | "webkit"
        headless:       bool = True,
        viewport_width: int  = 1280,
        viewport_height: int = 800,
        timeout_ms:     int  = 30_000,         # page-load timeout in milliseconds
    ):
        self.screenshot_dir  = Path(screenshot_dir)
        self.browser_name    = browser
        self.headless        = headless
        self.viewport_width  = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms      = timeout_ms

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_page(self, url: str) -> UITestResult:
        """
        Open *url* in a real browser, capture all signals, and return
        a UITestResult.  Each call spins up its own browser context so
        sessions never leak between pages.
        """
        # Import here so the rest of the project still loads even if
        # Playwright is not installed yet.
        try:
            from playwright.sync_api import sync_playwright, ConsoleMessage, Page
        except ImportError:
            raise ImportError(
                "Playwright is not installed.\n"
                "Run:  pip install playwright && playwright install chromium"
            )

        result = UITestResult(url=url)

        with sync_playwright() as pw:
            browser = self._launch_browser(pw)

            try:
                context = browser.new_context(
                    viewport={"width": self.viewport_width, "height": self.viewport_height},
                    ignore_https_errors=True,
                )
                page = context.new_page()

                # ── Wire up listeners BEFORE navigation ──────────────────────
                self._attach_listeners(page, result)

                # ── Navigate ─────────────────────────────────────────────────
                t0 = time.perf_counter()
                response = page.goto(
                    url,
                    wait_until="networkidle",   # wait for all XHR/fetch to settle
                    timeout=self.timeout_ms,
                )
                result.load_time_ms = round((time.perf_counter() - t0) * 1000, 2)

                # ── Collect page metadata ─────────────────────────────────────
                result.title       = page.title()
                result.final_url   = page.url
                result.status_code = response.status if response else 0

                # Real rendered dimensions (after JS has run)
                dims = page.evaluate(
                    "() => ({ w: document.body.scrollWidth, h: document.body.scrollHeight })"
                )
                result.page_width  = dims.get("w", 0)
                result.page_height = dims.get("h", 0)

                # ── Screenshot ────────────────────────────────────────────────
                result.screenshot_path = self._take_screenshot(page, url)

                result.success = True

            except Exception as exc:
                result.error   = str(exc)
                result.success = False
                # Still attempt a screenshot if the page partially loaded
                try:
                    result.screenshot_path = self._take_screenshot(page, url)
                except Exception:
                    pass

            finally:
                try:
                    context.close()
                except Exception:
                    pass
                browser.close()

        return result

    def test_pages(self, urls: list[str]) -> list[UITestResult]:
        """
        Test multiple pages in sequence and return all results.

        Each page gets its own isolated browser context, so cookies /
        local-storage from page A cannot affect page B.
        """
        results = []
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] Testing: {url}")
            result = self.test_page(url)
            print(f"        {result.summary()}")
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _launch_browser(self, pw):
        """Launch the configured browser type."""
        launcher = {
            "chromium": pw.chromium,
            "firefox":  pw.firefox,
            "webkit":   pw.webkit,
        }.get(self.browser_name, pw.chromium)

        return launcher.launch(headless=self.headless)

    def _attach_listeners(self, page, result: UITestResult) -> None:
        """
        Register event handlers on *page* that write into *result*.
        These fire asynchronously during page load; Playwright collects
        them before goto() returns.
        """

        # ── Console messages ──────────────────────────────────────────────
        def on_console(msg):
            text = f"[{msg.type.upper()}] {msg.text}"
            if msg.type == "error":
                result.console_errors.append(text)
            elif msg.type == "warning":
                result.console_warnings.append(text)
            else:
                result.console_logs.append(text)

        page.on("console", on_console)

        # ── Uncaught JS exceptions ────────────────────────────────────────
        def on_page_error(exc):
            result.js_exceptions.append(str(exc))

        page.on("pageerror", on_page_error)

    def _take_screenshot(self, page, url: str) -> str:
        """
        Save a full-page screenshot and return its file path.

        Screenshots are saved to the 'screenshots/' folder with a
        timestamp filename: screenshots/20240315_143022.png

        Also prints the saved path to the console for easy verification.
        """
        os.makedirs("screenshots", exist_ok=True)
        filename = f"screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        page.screenshot(path=filename, full_page=True)
        print(f"Saved screenshot at: {filename}")
        return filename


# ---------------------------------------------------------------------------
# Standalone helper: test a single page with one function call
# ---------------------------------------------------------------------------

def test_single_page(
    url: str,
    screenshot_dir: str = "output/screenshots",
    headless: bool      = True,
) -> dict:
    """
    Convenience wrapper — test one page and return a plain dictionary.

    Perfect for quick scripts or pipeline integration.

    Args:
        url:            The page to test.
        screenshot_dir: Where to save the screenshot.
        headless:       False opens a visible browser window (useful for debugging).

    Returns:
        A dictionary with keys: url, title, screenshot_path,
        console_errors, console_warnings, js_exceptions,
        load_time_ms, status_code, success, error.

    Example:
        result = test_single_page("https://example.com")
        if result["console_errors"]:
            print("Errors found:", result["console_errors"])
    """
    tester = UITester(screenshot_dir=screenshot_dir, headless=headless)
    result = tester.test_page(url)
    return result.to_dict()


# ---------------------------------------------------------------------------
# Private utility
# ---------------------------------------------------------------------------

def _url_to_slug(url: str, max_len: int = 60) -> str:
    """
    Convert a URL to a filesystem-safe slug for screenshot file names.

    https://example.com/about/team  →  example_com_about_team
    """
    parsed = urlparse(url)
    raw    = f"{parsed.netloc}{parsed.path}"
    slug   = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_")
    return slug[:max_len]


# ---------------------------------------------------------------------------
# CLI  (python tests/ui_tests.py https://example.com)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python tests/ui_tests.py <URL> [screenshot_dir]")
        print("       python tests/ui_tests.py https://example.com output/screenshots")
        sys.exit(1)

    target = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "output/screenshots"

    print(f"\n🎭  Playwright UI Test")
    print(f"    URL : {target}")
    print(f"    Dest: {outdir}\n")

    data = test_single_page(target, screenshot_dir=outdir)

    print("\n── Result ──────────────────────────────────────────────────")
    print(json.dumps(data, indent=2))

    if data["console_errors"] or data["js_exceptions"]:
        print("\n⚠  Issues detected — see console_errors / js_exceptions above.")
        sys.exit(1)
    else:
        print("\n✅  No errors detected.")