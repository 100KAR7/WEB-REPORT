"""
ai_analysis/analyzer.py
------------------------
LLM-powered reasoning layer — now powered by Ollama (local, free, no API key).

Ollama runs models locally on your machine:
    Install : https://ollama.com
    Pull    : ollama pull llama3
    Run     : ollama serve   (starts automatically on most installs)

The LLM is used ONLY for reasoning — never for browser control.
It receives structured test + SEO data and returns:
  • Executive summary
  • Prioritised bug report
  • SEO improvement suggestions
  • Quick wins list

Usage:
    from ai_analysis.analyzer import LLMAnalyzer

    analyzer = LLMAnalyzer()                    # uses llama3 by default
    report   = analyzer.analyze(page_results)   # list[PageResult]
    print(report.summary)
    print(report.bug_report)

Prerequisites:
    1. Install Ollama:  https://ollama.com/download
    2. Pull a model:    ollama pull llama3
    3. pip install requests   (already in requirements.txt)
"""

from __future__ import annotations

import json
import os
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Ollama configuration
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL    = os.getenv("OLLAMA_URL",   "http://localhost:11434")
DEFAULT_MODEL      = os.getenv("OLLAMA_MODEL", "llama3")   # change to mistral, phi3, etc.
REQUEST_TIMEOUT    = 120          # seconds — local models can be slow on first run
MAX_PAGES_IN_PROMPT = 10          # cap to avoid overflowing context window


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior QA and SEO engineer reviewing automated website test results.

You receive structured data per page:
  1. UI Test Results  — HTTP status, load time, console errors, JS exceptions
  2. SEO Audit Data   — scores, missing tags, headings, image alt coverage

Your job is purely analytical reasoning. You do NOT control a browser.
You do NOT visit URLs. You reason only over the data provided.

Always respond using these exact section headers:

## EXECUTIVE SUMMARY
2-3 sentences: overall site health, most critical finding, first recommended action.

## BUG REPORT
List every issue found. Use this structure for each:
  - [SEVERITY: Critical|High|Medium|Low] Short title
    Page: <url>
    Detail: what the data shows
    Fix: specific actionable recommendation

Severity guide:
  Critical -> page fails to load, noindex set, JS exception blocking render
  High     -> console errors, bad status codes, missing H1 or title
  Medium   -> slow load time, missing meta description, images without alt
  Low      -> missing canonical, no Open Graph, thin content

## SEO IMPROVEMENTS
Group by impact (High / Medium / Low). For each:
  - Affected page(s)
  - What is missing or wrong
  - Exact change to make

## QUICK WINS
3-5 improvements achievable in under 30 minutes, ordered by impact.
"""

USER_PROMPT_TEMPLATE = """\
Website: {site_url}
Pages analysed: {page_count}
Generated: {generated_at}

{pages_block}

Analyse the data above and produce your full report.
"""

PAGE_BLOCK_TEMPLATE = """\
------------------------------------------------------------
Page {index}/{total}: {url}
------------------------------------------------------------
UI TEST:
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
  Canonical      : {canonical}
  Lang           : {lang}
  Images         : {images_total} total | {images_missing_alt} missing alt
  Word count     : {word_count}
  Internal links : {internal_links}
  Robots         : {robots}
  Structured data: {structured_data}
  Open Graph     : {og_present}
SEO ISSUES:
{seo_issues_block}"""


# ---------------------------------------------------------------------------
# Result data structure
# ---------------------------------------------------------------------------

@dataclass
class LLMReport:
    """Structured report returned by the LLM analyzer."""

    site_url:       str
    generated_at:   str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    pages_analyzed: int  = 0

    # Raw LLM response
    raw_response:   str  = ""

    # Parsed sections
    summary:          str = ""
    bug_report:       str = ""
    seo_improvements: str = ""
    quick_wins:       str = ""

    # Meta
    model_used:   str           = DEFAULT_MODEL
    prompt_used:  str           = ""
    backend:      str           = "ollama"
    error:        Optional[str] = None
    success:      bool          = False

    def to_dict(self) -> dict:
        return {
            "site_url":         self.site_url,
            "generated_at":     self.generated_at,
            "pages_analyzed":   self.pages_analyzed,
            "model_used":       self.model_used,
            "backend":          self.backend,
            "success":          self.success,
            "error":            self.error,
            "summary":          self.summary,
            "bug_report":       self.bug_report,
            "seo_improvements": self.seo_improvements,
            "quick_wins":       self.quick_wins,
            "raw_response":     self.raw_response,
        }

    def print_report(self) -> None:
        width = 70
        print("\n" + "=" * width)
        print(f"  LLM Analysis Report  [{self.backend} / {self.model_used}]")
        print(f"  Site: {self.site_url}")
        print("=" * width)
        for title, content in [
            ("EXECUTIVE SUMMARY",   self.summary),
            ("BUG REPORT",          self.bug_report),
            ("SEO IMPROVEMENTS",    self.seo_improvements),
            ("QUICK WINS",          self.quick_wins),
        ]:
            print(f"\n-- {title} {'─' * (width - len(title) - 4)}")
            print(content.strip() if content else "  (no content)")
        print("\n" + "=" * width + "\n")


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

class OllamaClient:
    """
    Minimal client for the Ollama REST API.
    Ollama must be running locally (ollama serve).
    """

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = DEFAULT_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model    = model

    def is_available(self) -> bool:
        """Return True if Ollama is running and reachable."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """Return names of all locally available models."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def generate(self, prompt: str, system: str = "") -> str:
        """
        Send a prompt to Ollama and return the response text.

        Uses /api/generate with stream=False so we wait for the full
        response before returning — simpler than streaming for our use case.
        """
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": 0.3,    # lower = more deterministic / factual
                "num_predict": 2048,   # max tokens to generate
            },
        }

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "")


# ---------------------------------------------------------------------------
# Core analyser
# ---------------------------------------------------------------------------

class LLMAnalyzer:
    """
    Sends structured test + SEO data to a local Ollama model and parses
    the response into a structured LLMReport.

    The LLM is ONLY used for reasoning — never visits URLs or controls browser.

    Args:
        model:    Ollama model name (default: llama3). Run `ollama list` to see available.
        base_url: Ollama server URL (default: http://localhost:11434).

    Example:
        analyzer = LLMAnalyzer(model="llama3")
        report   = analyzer.analyze(page_results, site_url="https://example.com")
        report.print_report()
    """

    def __init__(
        self,
        model:    str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self.model  = model
        self.client = OllamaClient(base_url=base_url, model=model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, page_results: list, site_url: str = "") -> LLMReport:
        """
        Analyze a list of PageResult objects and return an LLMReport.

        Args:
            page_results: list[PageResult] from pipeline/run_pipeline.py
            site_url:     Root URL being tested (for display).

        Returns:
            LLMReport with summary, bug_report, seo_improvements, quick_wins.
        """
        if not site_url and page_results:
            site_url = getattr(page_results[0], "url", "unknown")

        report = LLMReport(
            site_url       = site_url,
            pages_analyzed = len(page_results),
            model_used     = self.model,
            backend        = "ollama",
        )

        # ── Check Ollama is running ────────────────────────────────────────
        if not self.client.is_available():
            report.error = (
                "Ollama is not running or not reachable at "
                f"{self.client.base_url}.\n"
                "Start it with:  ollama serve\n"
                "Install from:   https://ollama.com/download"
            )
            report.success = False
            print(f"  ⚠  {report.error}")
            return report

        # ── Check model is downloaded ──────────────────────────────────────
        available = self.client.list_models()
        if available and not any(self.model in m for m in available):
            report.error = (
                f"Model '{self.model}' not found locally.\n"
                f"Available: {available}\n"
                f"Download with:  ollama pull {self.model}"
            )
            report.success = False
            print(f"  ⚠  {report.error}")
            return report

        # ── Build prompt ───────────────────────────────────────────────────
        prompt = _build_prompt(page_results, site_url)
        report.prompt_used = prompt

        # ── Call Ollama ────────────────────────────────────────────────────
        try:
            print(f"  🤖  Running LLM analysis with {self.model} via Ollama...")
            raw_text         = self.client.generate(prompt, system=SYSTEM_PROMPT)
            report.raw_response = raw_text
            report.success      = True

            # Parse the four sections out of the response
            report.summary          = _extract_section(raw_text, "EXECUTIVE SUMMARY")
            report.bug_report       = _extract_section(raw_text, "BUG REPORT")
            report.seo_improvements = _extract_section(raw_text, "SEO IMPROVEMENTS")
            report.quick_wins       = _extract_section(raw_text, "QUICK WINS")

            print("  ✓  LLM analysis complete.")

        except requests.exceptions.Timeout:
            report.error   = f"Ollama request timed out after {REQUEST_TIMEOUT}s. Try a smaller model."
            report.success = False
        except Exception as exc:
            report.error   = str(exc)
            report.success = False

        return report

    def analyze_single_page(self, page_result, site_url: str = "") -> LLMReport:
        """Convenience wrapper to analyse one page."""
        return self.analyze([page_result], site_url=site_url)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_prompt(page_results: list, site_url: str) -> str:
    capped      = page_results[:MAX_PAGES_IN_PROMPT]
    pages_block = "\n".join(
        _format_page_block(r, i + 1, len(capped))
        for i, r in enumerate(capped)
    )
    return USER_PROMPT_TEMPLATE.format(
        site_url     = site_url,
        page_count   = len(capped),
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        pages_block  = pages_block,
    )


def _format_page_block(result, index: int, total: int) -> str:
    def _get(obj, key, default=None):
        return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

    ui  = _get(result, "ui")
    seo = _get(result, "seo")

    status_code    = _get(ui, "status_code",    "N/A") if ui else "N/A"
    load_time_ms   = f"{_get(ui, 'load_time_ms', 0):.0f}" if ui else "N/A"
    success        = str(_get(ui, "success", False)) if ui else "N/A"
    console_errors = _get(ui, "console_errors", []) if ui else []
    js_exceptions  = _get(ui, "js_exceptions",  []) if ui else []

    console_errors_block = (
        "".join(f"    - {e}\n" for e in console_errors[:5])
        if console_errors else "    (none)\n"
    )
    js_exceptions_block = (
        "".join(f"    - {e}\n" for e in js_exceptions[:5])
        if js_exceptions else "    (none)\n"
    )

    seo_score    = _get(seo, "score",              "N/A") if seo else "N/A"
    title        = str(_get(seo, "title",          ""))[:80] if seo else "N/A"
    title_length = _get(seo, "title_length",       0)    if seo else 0
    meta_desc    = str(_get(seo, "meta_description",""))[:120] if seo else "N/A"
    meta_length  = _get(seo, "meta_desc_length",   0)    if seo else 0
    h1_count     = _get(seo, "h1_count",           "N/A") if seo else "N/A"
    canonical    = _get(seo, "canonical_url",      "N/A") if seo else "N/A"
    lang         = _get(seo, "lang",               "N/A") if seo else "N/A"
    img_total    = _get(seo, "images_total",       "N/A") if seo else "N/A"
    img_missing  = _get(seo, "images_missing_alt", "N/A") if seo else "N/A"
    word_count   = _get(seo, "word_count",         "N/A") if seo else "N/A"
    int_links    = _get(seo, "internal_links_count","N/A") if seo else "N/A"
    robots       = _get(seo, "robots_directive",   "N/A") if seo else "N/A"
    struct_data  = ("yes" if _get(seo, "has_structured_data") else "no") if seo else "N/A"
    og_present   = ("yes" if _get(seo, "og_title") else "no") if seo else "N/A"

    raw_issues   = _get(seo, "issues", []) if seo else []
    seo_issues_block = (
        "".join(
            f"  [{_get(i,'severity','?').upper():>7}] [{_get(i,'field','?')}] {_get(i,'message','')}\n"
            for i in raw_issues
        ) if raw_issues else "  (none)\n"
    )

    return PAGE_BLOCK_TEMPLATE.format(
        index               = index,
        total               = total,
        url                 = _get(result, "url", ""),
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
        meta_desc_length    = meta_length,
        h1_count            = h1_count,
        canonical           = canonical,
        lang                = lang,
        images_total        = img_total,
        images_missing_alt  = img_missing,
        word_count          = word_count,
        internal_links      = int_links,
        robots              = robots,
        structured_data     = struct_data,
        og_present          = og_present,
        seo_issues_block    = seo_issues_block,
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _extract_section(text: str, header: str) -> str:
    import re
    pattern = rf"##\s*{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)"
    match   = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def analyze_with_llm(
    page_results: list,
    site_url:     str = "",
    model:        str = DEFAULT_MODEL,
) -> dict:
    """
    One-call Ollama analysis. Returns a plain dictionary.

    Example:
        from ai_analysis.analyzer import analyze_with_llm
        report = analyze_with_llm(pipeline_results, site_url="https://example.com")
        print(report["summary"])
    """
    return LLMAnalyzer(model=model).analyze(page_results, site_url=site_url).to_dict()


# ---------------------------------------------------------------------------
# CLI  (python ai_analysis/analyzer.py --json output/pipeline_results.json)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Ollama LLM analysis on saved pipeline results")
    parser.add_argument("--json",  required=True, help="Path to pipeline_results.json")
    parser.add_argument("--url",   default="",    help="Site URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default: {DEFAULT_MODEL})")
    args = parser.parse_args()

    with open(args.json) as f:
        data = json.load(f)

    pages    = data.get("pages", [])
    site_url = args.url or (pages[0].get("url", "") if pages else "")

    analyzer = LLMAnalyzer(model=args.model)
    report   = analyzer.analyze(pages, site_url=site_url)
    report.print_report()
