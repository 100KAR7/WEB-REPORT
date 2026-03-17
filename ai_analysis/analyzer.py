"""
ai_analysis/analyzer.py
------------------------
LLM-powered reasoning layer for the AI Web Tester.

The LLM is used ONLY for reasoning — not for browser control.
It receives structured test + SEO data and returns:
  • A prioritised bug report
  • SEO improvement suggestions
  • An executive summary

Data flow:
    list[PageResult]            (from pipeline/run_pipeline.py)
          │
          ▼
    _build_prompt()             formats data as a plain-text context block
          │
          ▼
    Anthropic API (Claude)      reasons over the structured context
          │
          ▼
    LLMReport                   structured dataclass with parsed sections

The LLM never touches a browser, a URL, or any live system.
It only sees text — numbers, labels, issue strings — and reasons over them.

Usage:
    from ai_analysis.analyzer import LLMAnalyzer

    analyzer = LLMAnalyzer()
    report   = analyzer.analyze(page_results)   # list[PageResult]
    print(report.summary)
    print(report.bug_report)
    print(report.seo_improvements)
    print(report.to_dict())

Prerequisites:
    pip install anthropic
    Set ANTHROPIC_API_KEY in your .env file
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

DEFAULT_MODEL      = "claude-sonnet-4-20250514"
MAX_TOKENS         = 2048
MAX_PAGES_IN_PROMPT = 10    # cap so we never overflow the context window


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior QA and SEO engineer reviewing automated test results for a website.

You will receive structured data from two sources per page:
  1. UI Test Results  — HTTP status, load time, browser console errors, JS exceptions
  2. SEO Audit Data   — scores, missing tags, heading structure, image alt coverage, etc.

Your job is purely analytical reasoning. You do NOT control a browser.
You do NOT visit URLs. You reason only over the data provided.

Always respond in this exact format — use these exact section headers:

## EXECUTIVE SUMMARY
2–3 sentences. Overall health of the site, most critical finding, recommended first action.

## BUG REPORT
List every real issue found. For each bug use this structure:
  - [SEVERITY: Critical|High|Medium|Low] <short title>
    Page: <url>
    Detail: <what the data shows>
    Fix: <specific, actionable recommendation>

Severity guide:
  Critical → page fails to load, noindex, JS exception blocking render
  High     → console errors, broken status codes, missing H1/title
  Medium   → slow load time, missing meta description, images without alt
  Low      → missing canonical, no Open Graph, thin content

## SEO IMPROVEMENTS
Group suggestions by impact (High / Medium / Low).
For each suggestion include:
  - The affected page(s)
  - What is missing or wrong
  - The exact change to make (e.g. "Add <meta name='description' content='...'>" )

## QUICK WINS
3–5 improvements that can be made in under 30 minutes, ordered by impact.
"""

# ---------------------------------------------------------------------------
# The user prompt is built dynamically from real test data — see _build_prompt()
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
Website under test: {site_url}
Pages analysed: {page_count}
Report generated: {generated_at}

{pages_block}

Please analyse the data above and produce your full report.
"""

PAGE_BLOCK_TEMPLATE = """\
────────────────────────────────────────────────────
Page {index}/{total}: {url}
────────────────────────────────────────────────────
UI TEST RESULTS:
  Status code    : {status_code}
  Load time      : {load_time_ms} ms
  Success        : {success}
  Console errors : {console_error_count}
{console_errors_block}\
  JS exceptions  : {js_exception_count}
{js_exceptions_block}\
SEO AUDIT:
  Score          : {seo_score}/100
  Title          : {title} ({title_length} chars)
  Meta desc      : {meta_desc} ({meta_desc_length} chars)
  H1 count       : {h1_count}
  Canonical URL  : {canonical}
  Lang attribute : {lang}
  Images total   : {images_total}  |  Missing alt: {images_missing_alt}
  Word count     : {word_count}
  Internal links : {internal_links}
  Robots         : {robots}
  Structured data: {structured_data}
  Open Graph     : {og_present}
SEO ISSUES FOUND:
{seo_issues_block}\
"""


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------

@dataclass
class LLMReport:
    """Structured report returned by the LLM analyzer."""

    site_url:         str
    generated_at:     str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    pages_analyzed:   int  = 0

    # ── Raw LLM response (full text) ────────────────────────────────────────
    raw_response: str = ""

    # ── Parsed sections ─────────────────────────────────────────────────────
    summary:          str = ""
    bug_report:       str = ""
    seo_improvements: str = ""
    quick_wins:       str = ""

    # ── Meta ────────────────────────────────────────────────────────────────
    model_used:   str           = DEFAULT_MODEL
    prompt_used:  str           = ""    # the exact prompt sent (useful for debugging)
    error:        Optional[str] = None
    success:      bool          = False

    def to_dict(self) -> dict:
        return {
            "site_url":         self.site_url,
            "generated_at":     self.generated_at,
            "pages_analyzed":   self.pages_analyzed,
            "model_used":       self.model_used,
            "success":          self.success,
            "error":            self.error,
            "summary":          self.summary,
            "bug_report":       self.bug_report,
            "seo_improvements": self.seo_improvements,
            "quick_wins":       self.quick_wins,
            "raw_response":     self.raw_response,
        }

    def print_report(self) -> None:
        """Pretty-print the full report to stdout."""
        width = 70
        print("\n" + "═" * width)
        print("  🤖  LLM Analysis Report")
        print(f"  Site: {self.site_url}")
        print(f"  Model: {self.model_used}  |  Pages: {self.pages_analyzed}")
        print("═" * width)

        sections = [
            ("EXECUTIVE SUMMARY",   self.summary),
            ("BUG REPORT",          self.bug_report),
            ("SEO IMPROVEMENTS",    self.seo_improvements),
            ("QUICK WINS",          self.quick_wins),
        ]
        for title, content in sections:
            print(f"\n── {title} {'─' * (width - len(title) - 4)}")
            if content:
                for line in content.strip().splitlines():
                    print(f"  {line}")
            else:
                print("  (no content)")
        print("\n" + "═" * width + "\n")


# ---------------------------------------------------------------------------
# Core analyser
# ---------------------------------------------------------------------------

class LLMAnalyzer:
    """
    Sends structured test + SEO data to Claude and parses the response
    into a structured LLMReport.

    The LLM is used ONLY as a reasoning engine — it never visits URLs,
    controls a browser, or interacts with any live system.

    Args:
        api_key:    Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
        model:      Claude model to use.
        max_tokens: Token budget for the response.
    """

    def __init__(
        self,
        api_key:    Optional[str] = None,
        model:      str           = DEFAULT_MODEL,
        max_tokens: int           = MAX_TOKENS,
    ):
        self.model      = model
        self.max_tokens = max_tokens
        self._api_key   = api_key or os.getenv("ANTHROPIC_API_KEY", "")

        if not self._api_key:
            raise ValueError(
                "Anthropic API key not found.\n"
                "Set ANTHROPIC_API_KEY in your .env file or pass api_key= directly."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, page_results: list, site_url: str = "") -> LLMReport:
        """
        Analyze a list of PageResult objects and return an LLMReport.

        Args:
            page_results: list[PageResult] from pipeline/run_pipeline.py
            site_url:     The root URL being tested (used for display).

        Returns:
            LLMReport with summary, bug_report, seo_improvements, quick_wins.
        """
        import anthropic

        # Infer site_url from first result if not provided
        if not site_url and page_results:
            site_url = getattr(page_results[0], "url", "unknown")

        report = LLMReport(
            site_url       = site_url,
            pages_analyzed = len(page_results),
            model_used     = self.model,
        )

        # ── Build prompt ───────────────────────────────────────────────────
        prompt = _build_prompt(page_results, site_url)
        report.prompt_used = prompt

        # ── Call the LLM ───────────────────────────────────────────────────
        try:
            client   = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model      = self.model,
                max_tokens = self.max_tokens,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw_text         = response.content[0].text
            report.raw_response = raw_text
            report.success      = True

            # ── Parse sections from response ───────────────────────────────
            report.summary          = _extract_section(raw_text, "EXECUTIVE SUMMARY")
            report.bug_report       = _extract_section(raw_text, "BUG REPORT")
            report.seo_improvements = _extract_section(raw_text, "SEO IMPROVEMENTS")
            report.quick_wins       = _extract_section(raw_text, "QUICK WINS")

        except Exception as exc:
            report.error   = str(exc)
            report.success = False

        return report

    def analyze_single_page(self, page_result, site_url: str = "") -> LLMReport:
        """Convenience wrapper to analyse just one page."""
        return self.analyze([page_result], site_url=site_url)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_prompt(page_results: list, site_url: str) -> str:
    """
    Convert a list of PageResult objects into a plain-text context block
    the LLM can reason over.

    Caps at MAX_PAGES_IN_PROMPT to avoid context overflow.
    """
    capped   = page_results[:MAX_PAGES_IN_PROMPT]
    pages_block = "\n".join(
        _format_page_block(r, idx + 1, len(capped))
        for idx, r in enumerate(capped)
    )

    return USER_PROMPT_TEMPLATE.format(
        site_url     = site_url,
        page_count   = len(capped),
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pages_block  = pages_block,
    )


def _format_page_block(result, index: int, total: int) -> str:
    """Format one PageResult into the structured text block for the prompt."""

    # ── UI data ────────────────────────────────────────────────────────────
    ui = getattr(result, "ui", None)

    status_code        = ui.status_code   if ui else "N/A"
    load_time_ms       = f"{ui.load_time_ms:.0f}" if ui else "N/A"
    success            = str(ui.success)  if ui else "N/A"
    console_errors     = ui.console_errors  if ui else []
    js_exceptions      = ui.js_exceptions   if ui else []

    console_errors_block = (
        "".join(f"    • {e}\n" for e in console_errors[:5])
        if console_errors else "    (none)\n"
    )
    js_exceptions_block = (
        "".join(f"    • {e}\n" for e in js_exceptions[:5])
        if js_exceptions else "    (none)\n"
    )

    # ── SEO data ───────────────────────────────────────────────────────────
    seo = getattr(result, "seo", None)

    seo_score         = seo.score             if seo else "N/A"
    title             = seo.title             if seo else "N/A"
    title_length      = seo.title_length      if seo else 0
    meta_desc         = seo.meta_description  if seo else "N/A"
    meta_desc_length  = seo.meta_desc_length  if seo else 0
    h1_count          = seo.h1_count          if seo else "N/A"
    canonical         = seo.canonical_url     if seo else "N/A"
    lang              = seo.lang              if seo else "N/A"
    images_total      = seo.images_total      if seo else "N/A"
    images_missing    = seo.images_missing_alt if seo else "N/A"
    word_count        = seo.word_count        if seo else "N/A"
    internal_links    = seo.internal_links_count if seo else "N/A"
    robots            = seo.robots_directive  if seo else "N/A"
    structured_data   = ("yes" if seo.has_structured_data else "no") if seo else "N/A"
    og_present        = ("yes" if seo.og_title else "no") if seo else "N/A"

    seo_issues = getattr(seo, "issues", []) if seo else []
    seo_issues_block = (
        "".join(
            f"  [{i.severity.upper():>7}] [{i.field}] {i.message}\n"
            for i in seo_issues
        ) if seo_issues else "  (none)\n"
    )

    # Truncate long strings so the prompt stays readable
    title    = str(title)[:80]
    meta_desc = str(meta_desc)[:120]

    return PAGE_BLOCK_TEMPLATE.format(
        index               = index,
        total               = total,
        url                 = result.url,
        status_code         = status_code,
        load_time_ms        = load_time_ms,
        success             = success,
        console_error_count = len(console_errors),
        console_errors_block= console_errors_block,
        js_exception_count  = len(js_exceptions),
        js_exceptions_block = js_exceptions_block,
        seo_score           = seo_score,
        title               = title,
        title_length        = title_length,
        meta_desc           = meta_desc,
        meta_desc_length    = meta_desc_length,
        h1_count            = h1_count,
        canonical           = canonical,
        lang                = lang,
        images_total        = images_total,
        images_missing_alt  = images_missing,
        word_count          = word_count,
        internal_links      = internal_links,
        robots              = robots,
        structured_data     = structured_data,
        og_present          = og_present,
        seo_issues_block    = seo_issues_block,
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _extract_section(text: str, header: str) -> str:
    """
    Pull the content under a ## HEADER from the LLM response.

    Handles both exact matches and slight variations in spacing/case.
    Returns empty string if the section is not found.
    """
    import re

    # Match "## HEADER" possibly followed by a newline, capture until next ##
    pattern = rf"##\s*{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)"
    match   = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def analyze_with_llm(
    page_results: list,
    site_url:     str           = "",
    api_key:      Optional[str] = None,
) -> dict:
    """
    One-call LLM analysis. Returns a plain dictionary.

    Example:
        from ai_analysis.analyzer import analyze_with_llm
        report = analyze_with_llm(pipeline_results, site_url="https://example.com")
        print(report["summary"])
        print(report["bug_report"])
    """
    return LLMAnalyzer(api_key=api_key).analyze(page_results, site_url=site_url).to_dict()


# ---------------------------------------------------------------------------
# CLI  (python ai_analysis/analyzer.py --json results.json)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="Run LLM analysis on saved pipeline results")
    parser.add_argument("--json",  required=True, help="Path to pipeline_results.json")
    parser.add_argument("--url",   default="",    help="Site URL (for display)")
    args = parser.parse_args()

    with open(args.json) as f:
        data = json.load(f)

    # Build lightweight duck-typed objects from the JSON so we don't need
    # the full PageResult dataclass at runtime
    class _Obj:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, _Obj(v) if isinstance(v, dict) else v)
            if not hasattr(self, "__iter__"):
                pass

    class _Page:
        def __init__(self, d):
            self.url   = d.get("url", "")
            self.error = d.get("error")
            ui_d       = d.get("ui")
            seo_d      = d.get("seo")

            class UI:
                pass
            class SEO:
                pass

            if ui_d:
                u = UI()
                u.status_code    = ui_d.get("status_code", 0)
                u.load_time_ms   = ui_d.get("load_time_ms", 0)
                u.success        = ui_d.get("success", False)
                u.console_errors = ui_d.get("console_errors", [])
                u.js_exceptions  = ui_d.get("js_exceptions", [])
                self.ui = u
            else:
                self.ui = None

            if seo_d:
                s = SEO()
                s.score              = seo_d.get("score", 0)
                s.title              = seo_d.get("title", "")
                s.title_length       = seo_d.get("title_length", 0)
                s.meta_description   = seo_d.get("meta_description", "")
                s.meta_desc_length   = seo_d.get("meta_desc_length", 0)
                s.h1_count           = seo_d.get("h1_count", 0)
                s.canonical_url      = seo_d.get("canonical_url")
                s.lang               = seo_d.get("lang", "")
                s.images_total       = seo_d.get("images_total", 0)
                s.images_missing_alt = seo_d.get("images_missing_alt", 0)
                s.word_count         = seo_d.get("word_count", 0)
                s.internal_links_count = seo_d.get("internal_links_count", 0)
                s.robots_directive   = seo_d.get("robots_directive", "")
                s.has_structured_data = seo_d.get("has_structured_data", False)
                s.og_title           = seo_d.get("open_graph", {}).get("og:title", "")

                class _Issue:
                    def __init__(self, d):
                        self.severity = d.get("severity", "")
                        self.field    = d.get("field", "")
                        self.message  = d.get("message", "")

                s.issues = [_Issue(i) for i in seo_d.get("issues", [])]
                self.seo = s
            else:
                self.seo = None

    pages    = [_Page(p) for p in data.get("pages", [])]
    site_url = args.url or data.get("pages", [{}])[0].get("url", "unknown")

    analyzer = LLMAnalyzer()
    report   = analyzer.analyze(pages, site_url=site_url)
    report.print_report()