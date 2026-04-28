"""
pipeline/run_pipeline.py
------------------------
Main pipeline that wires every module together into one end-to-end run.

Flow:
    URL
     │
     ▼
  ① Crawler ──── discover_pages() ──► list[str]  (all internal URLs)
     │
     ▼
  ② Loop over each URL
     │
     ├─► ③ UITester    ──► UITestResult   (title, screenshot, console errors)
     │
     └─► ④ SEOAnalyzer ──► SEOResult      (title, meta, h1, images, score)
     │
     ▼
  ⑤ Collect all results into a list[PageResult]
     │
     ▼
  ⑥ Print summary table to console

Usage:
    # From project root:
    python pipeline/run_pipeline.py --url https://example.com
    python pipeline/run_pipeline.py --url https://example.com --max-pages 5
    python pipeline/run_pipeline.py --url https://example.com --no-ui
    python pipeline/run_pipeline.py --url https://example.com --save-json

    # As a module:
    from pipeline.run_pipeline import Pipeline
    results = Pipeline("https://example.com").run()
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# ── Project root on path so imports work when run directly ─────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler.discover_pages import discover_pages   # ① URL discovery
from tests.ui_tests import UITester, UITestResult   # ③ Playwright UI tests
from seo.analyzer import SEOAnalyzer, SEOResult     # ④ SEO analysis


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


_configure_stdio()


# ---------------------------------------------------------------------------
# Result container — one per crawled page
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    """
    Holds everything collected for a single page during the pipeline run.
    Both ui and seo fields are Optional — they stay None if that step
    was skipped (e.g. --no-ui flag or Playwright not installed).
    """
    url:       str
    ui:        Optional[UITestResult] = None
    seo:       Optional[SEOResult]    = None
    error:     Optional[str]          = None
    duration_s: float                 = 0.0     # wall-clock seconds for this page

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def ui_ok(self) -> bool:
        return self.ui is not None and self.ui.success

    @property
    def seo_score(self) -> int:
        return self.seo.score if self.seo else -1

    @property
    def console_errors(self) -> list[str]:
        return self.ui.console_errors if self.ui else []

    def to_dict(self) -> dict:
        return {
            "url":        self.url,
            "duration_s": round(self.duration_s, 2),
            "error":      self.error,
            "ui":         self.ui.to_dict()  if self.ui  else None,
            "seo":        self.seo.to_dict() if self.seo else None,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """
    End-to-end pipeline: crawl → UI test → SEO analysis → results.

    Args:
        url:           Seed URL to start crawling from.
        max_pages:     Hard cap on how many pages to process.
        run_ui:        Whether to run Playwright UI tests.
        run_seo:       Whether to run SEO analysis.
        screenshot_dir: Where to store screenshots.
        headless:      Run browser headlessly (True) or visibly (False).
    """

    def __init__(
        self,
        url:            str,
        max_pages:      int  = 10,
        run_ui:         bool = True,
        run_seo:        bool = True,
        screenshot_dir: str  = "output/screenshots",
        headless:       bool = True,
    ):
        self.url            = url
        self.max_pages      = max_pages
        self.run_ui         = run_ui
        self.run_seo        = run_seo
        self.screenshot_dir = screenshot_dir
        self.headless       = headless

        # Lazy-init so we create one browser session for all UI tests
        self._ui_tester:  Optional[UITester]   = None
        self._seo_analyzer: SEOAnalyzer        = SEOAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> list[PageResult]:
        """
        Execute the full pipeline and return results for every page.
        """
        _print_header(self.url, self.max_pages, self.run_ui, self.run_seo)
        started_at = time.perf_counter()

        # ── ① Crawl: discover all internal URLs ───────────────────────
        _section("STEP 1 — Crawling internal pages")
        urls = discover_pages(self.url, max_pages=self.max_pages, verbose=True)

        if not urls:
            print("  ⚠  No pages found. Exiting.")
            return []

        # ── ② Prepare shared resources ────────────────────────────────
        if self.run_ui:
            self._ui_tester = UITester(
                screenshot_dir=self.screenshot_dir,
                headless=self.headless,
            )

        # ── ③ + ④  Loop: UI test + SEO per page ──────────────────────
        _section(f"STEP 2 — Running UI tests + SEO analysis ({len(urls)} pages)")
        results: list[PageResult] = []

        for idx, url in enumerate(urls, 1):
            print(f"\n  [{idx}/{len(urls)}] {url}")
            result = self._process_page(url, idx, len(urls))
            results.append(result)

        # ── ⑤ Summary ─────────────────────────────────────────────────
        total_s = time.perf_counter() - started_at
        _section("STEP 3 — Results")
        _print_results_table(results)
        _print_footer(results, total_s)

        return results

    # ------------------------------------------------------------------
    # Per-page processing
    # ------------------------------------------------------------------

    def _process_page(self, url: str, idx: int, total: int) -> PageResult:
        """Run UI test and SEO analysis on one page; return a PageResult."""
        result     = PageResult(url=url)
        page_start = time.perf_counter()
        errors: list[str] = []

        # ── ③ UI Test ─────────────────────────────────────────────
        if self.run_ui and self._ui_tester:
            try:
                print("       → UI test ...", end=" ", flush=True)
                result.ui = self._ui_tester.test_page(url)
                status    = "✓" if result.ui.success else "✗"
                errs      = len(result.ui.console_errors)
                print(f"{status}  load={result.ui.load_time_ms:.0f}ms  console_errors={errs}")
            except Exception as exc:
                errors.append(f"UI test failed: {exc}")
                print(f"✗  {exc}")

        # ── ④ SEO Analysis ────────────────────────────────────────
        if self.run_seo:
            try:
                print("       → SEO analysis ...", end=" ", flush=True)
                seo_result = self._run_seo(url, result.ui)
                result.seo = seo_result
                print(f"✓  score={seo_result.score}/100  issues={len(seo_result.issues)}")
            except Exception as exc:
                errors.append(f"SEO analysis failed: {exc}")
                print(f"✗  {exc}")

        result.duration_s = time.perf_counter() - page_start
        if errors:
            result.error = " | ".join(errors)
        return result

    def _run_seo(self, url: str, ui_result: Optional[UITestResult]) -> SEOResult:
        """
        Run SEO analysis against the page.

        Strategy:
          • If a UI test was already run, reuse its Playwright page by
            opening a fresh page in the same browser session (avoids a
            second network fetch).
          • If UI tests are disabled, spin up a minimal Playwright
            session just for SEO extraction.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            page    = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            seo_result = self._seo_analyzer.analyze(page)
            browser.close()

        return seo_result


# ---------------------------------------------------------------------------
# Console output helpers
# ---------------------------------------------------------------------------

_W = 70   # table width


def _print_header(url: str, max_pages: int, run_ui: bool, run_seo: bool) -> None:
    print("\n" + "═" * _W)
    print("  🤖  AI Web Tester — Pipeline")
    print("═" * _W)
    print(f"  URL       : {url}")
    print(f"  Max pages : {max_pages}")
    print(f"  UI tests  : {'enabled' if run_ui  else 'disabled'}")
    print(f"  SEO audit : {'enabled' if run_seo else 'disabled'}")
    print(f"  Started   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * _W)


def _section(title: str) -> None:
    print(f"\n{'─' * _W}")
    print(f"  {title}")
    print(f"{'─' * _W}")


def _print_results_table(results: list[PageResult]) -> None:
    """Print a per-page summary table to stdout."""
    col_url   = 42
    col_stat  =  7
    col_load  =  9
    col_errs  =  8
    col_seo   =  8

    header = (
        f"  {'URL':<{col_url}} "
        f"{'Status':>{col_stat}} "
        f"{'Load':>{col_load}} "
        f"{'CE':>{col_errs}} "    # Console Errors
        f"{'SEO':>{col_seo}}"
    )
    print(header)
    print("  " + "-" * (_W - 2))

    for r in results:
        # UI columns
        if r.ui:
            status   = f"{'✓' if r.ui_ok else '✗'} {r.ui.status_code}"
            load     = f"{r.ui.load_time_ms:.0f}ms"
            ce_count = str(len(r.console_errors))
        else:
            status = load = ce_count = "—"

        # SEO column
        seo_col = f"{r.seo_score}/100" if r.seo else "—"

        # Truncate URL for display
        url_display = r.url
        if len(url_display) > col_url:
            url_display = url_display[:col_url - 1] + "…"

        # Flag rows with issues
        flag = ""
        if r.error:
            flag = " ⚠"
        elif r.console_errors or (r.seo and r.seo.errors):
            flag = " !"

        print(
            f"  {url_display:<{col_url}} "
            f"{status:>{col_stat}} "
            f"{load:>{col_load}} "
            f"{ce_count:>{col_errs}} "
            f"{seo_col:>{col_seo}}"
            f"{flag}"
        )

    print("  " + "-" * (_W - 2))
    print("  Legend: CE = Console Errors  |  SEO = SEO score out of 100")


def _print_footer(results: list[PageResult], total_s: float) -> None:
    """Print aggregate stats after the table."""
    total     = len(results)
    ui_ok     = sum(1 for r in results if r.ui_ok)
    ui_errors = sum(len(r.console_errors) for r in results)
    seo_scored = [r for r in results if r.seo]
    avg_seo   = (
        sum(r.seo_score for r in seo_scored) // len(seo_scored)
        if seo_scored else 0
    )
    errored   = sum(1 for r in results if r.error)

    print(f"\n  {'─' * (_W - 2)}")
    print(f"  Pages tested   : {total}")
    print(f"  UI passed      : {ui_ok}/{total}")
    print(f"  Console errors : {ui_errors} total")
    print(f"  Avg SEO score  : {avg_seo}/100")
    if errored:
        print(f"  ⚠  Pipeline errors on {errored} page(s) — check output above")
    print(f"  Total time     : {total_s:.1f}s")
    print("═" * _W + "\n")


# ---------------------------------------------------------------------------
# Save results to JSON
# ---------------------------------------------------------------------------

def save_results(results: list[PageResult], output_path: str = "output/pipeline_results.json") -> str:
    """Serialise all PageResult objects to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_pages":  len(results),
        "pages":        [r.to_dict() for r in results],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"  💾  Results saved → {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Web Tester — main pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pipeline/run_pipeline.py --url https://example.com
  python pipeline/run_pipeline.py --url https://example.com --max-pages 5
  python pipeline/run_pipeline.py --url https://example.com --no-ui
  python pipeline/run_pipeline.py --url https://example.com --save-json
        """,
    )
    parser.add_argument("--url",        required=True,  help="Seed URL to crawl")
    parser.add_argument("--max-pages",  type=int, default=10, help="Max pages (default: 10)")
    parser.add_argument("--no-ui",      action="store_true",  help="Skip Playwright UI tests")
    parser.add_argument("--no-seo",     action="store_true",  help="Skip SEO analysis")
    parser.add_argument("--no-headless",action="store_true",  help="Show browser window")
    parser.add_argument("--save-json",  action="store_true",  help="Save results to JSON")
    parser.add_argument("--output",     default="output/pipeline_results.json",
                        help="JSON output path (used with --save-json)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    pipeline = Pipeline(
        url            = args.url,
        max_pages      = args.max_pages,
        run_ui         = not args.no_ui,
        run_seo        = not args.no_seo,
        headless       = not args.no_headless,
    )

    results = pipeline.run()

    if args.save_json:
        save_results(results, output_path=args.output)
