"""
reports/generate_report.py
---------------------------
Generates two outputs from the full pipeline results:

  1. JSON report  — machine-readable, every field preserved
  2. Text summary — human-readable, printed to console and saved as .txt

Input:
    list[PageResult]  from pipeline/run_pipeline.py
    LLMReport         from ai_analysis/analyzer.py  (optional)

Output files (all written to output/ by default):
    output/report_<timestamp>.json
    output/report_<timestamp>.txt

Usage:
    from reports.generate_report import ReportBuilder

    builder = ReportBuilder(site_url="https://example.com")
    builder.add_pages(pipeline_results)          # list[PageResult]
    builder.add_llm_report(llm_report)           # optional LLMReport
    paths = builder.save()                       # writes both files
    builder.print_summary()                      # prints to console

    # One-liner:
    from reports.generate_report import generate_report
    paths = generate_report(pipeline_results, site_url="https://example.com")

CLI:
    python reports/generate_report.py --json output/pipeline_results.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = "output"


# ---------------------------------------------------------------------------
# Internal data models (built from PageResult dicts)
# ---------------------------------------------------------------------------

@dataclass
class _PageSummary:
    """Flattened view of one page — UI + SEO combined."""
    url:               str
    status_code:       int   = 0
    load_time_ms:      float = 0.0
    ui_success:        bool  = False
    console_errors:    list  = field(default_factory=list)
    js_exceptions:     list  = field(default_factory=list)
    seo_score:         int   = 0
    seo_title:         str   = ""
    seo_meta_desc:     str   = ""
    seo_h1_count:      int   = 0
    seo_canonical:     Optional[str] = None
    seo_images_total:  int   = 0
    seo_missing_alt:   int   = 0
    seo_word_count:    int   = 0
    seo_issues:        list  = field(default_factory=list)   # [{"severity","field","message"}]
    page_error:        Optional[str] = None


# ---------------------------------------------------------------------------
# ReportBuilder
# ---------------------------------------------------------------------------

class ReportBuilder:
    """
    Collects all pipeline data and writes JSON + text reports.

    Typical usage:
        builder = ReportBuilder("https://example.com")
        builder.add_pages(pipeline_results)
        builder.add_llm_report(llm_report)     # optional
        paths   = builder.save()
        builder.print_summary()
    """

    def __init__(
        self,
        site_url:   str = "",
        output_dir: str = DEFAULT_OUTPUT_DIR,
    ):
        self.site_url    = site_url
        self.output_dir  = output_dir
        self.generated_at = datetime.now().isoformat(timespec="seconds")
        self._pages:  list[_PageSummary] = []
        self._llm:    Optional[dict]     = None   # LLMReport.to_dict()

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def add_pages(self, page_results: list) -> "ReportBuilder":
        """
        Ingest a list of PageResult objects (or dicts).
        Accepts both live PageResult dataclasses and plain dicts
        (e.g. loaded from a saved JSON file).
        """
        for r in page_results:
            self._pages.append(_extract_page_summary(r))
        return self

    def add_llm_report(self, llm_report) -> "ReportBuilder":
        """
        Attach an LLMReport (or its to_dict() output).
        Pass None to skip — the report still generates without LLM data.
        """
        if llm_report is None:
            return self
        self._llm = (
            llm_report.to_dict()
            if hasattr(llm_report, "to_dict")
            else llm_report
        )
        return self

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------

    def save(self) -> dict[str, str]:
        """
        Write both files and return their paths:
            {"json": "output/report_....json", "txt": "output/report_....txt"}
        """
        os.makedirs(self.output_dir, exist_ok=True)
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem  = os.path.join(self.output_dir, f"report_{ts}")

        json_path = stem + ".json"
        txt_path  = stem + ".txt"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._build_json(), f, indent=2)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._build_text())

        print(f"  💾  JSON report → {json_path}")
        print(f"  📄  Text report → {txt_path}")
        return {"json": json_path, "txt": txt_path}

    def save_json(self, path: Optional[str] = None) -> str:
        """Save JSON report only."""
        os.makedirs(self.output_dir, exist_ok=True)
        if not path:
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.output_dir, f"report_{ts}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._build_json(), f, indent=2)
        return path

    def save_txt(self, path: Optional[str] = None) -> str:
        """Save text summary only."""
        os.makedirs(self.output_dir, exist_ok=True)
        if not path:
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.output_dir, f"report_{ts}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._build_text())
        return path

    def print_summary(self) -> None:
        """Print the human-readable summary to stdout."""
        print(self._build_text())

    # ------------------------------------------------------------------
    # JSON builder
    # ------------------------------------------------------------------

    def _build_json(self) -> dict:
        """
        Build the complete JSON payload.

        Structure:
          {
            meta:         { site_url, generated_at, total_pages, ... }
            summary:      { scores, issue counts, averages }
            seo_summary:  { per-field aggregate stats }
            pages:        [ full per-page data ]
            llm_report:   { summary, bug_report, seo_improvements, quick_wins }
          }
        """
        stats   = _compute_stats(self._pages)
        seo_agg = _compute_seo_aggregates(self._pages)

        return {
            "meta": {
                "site_url":     self.site_url,
                "generated_at": self.generated_at,
                "total_pages":  len(self._pages),
                "tool":         "AI Web Tester",
            },
            "summary": {
                "total_pages":          len(self._pages),
                "pages_ok":             stats["ui_ok"],
                "pages_failed":         stats["ui_failed"],
                "pages_with_errors":    stats["pages_with_errors"],
                "total_console_errors": stats["total_console_errors"],
                "total_js_exceptions":  stats["total_js_exceptions"],
                "avg_load_time_ms":     stats["avg_load_ms"],
                "avg_seo_score":        stats["avg_seo"],
                "min_seo_score":        stats["min_seo"],
                "max_seo_score":        stats["max_seo"],
                "total_seo_errors":     stats["total_seo_errors"],
                "total_seo_warnings":   stats["total_seo_warnings"],
            },
            "seo_summary": {
                "pages_missing_title":       seo_agg["missing_title"],
                "pages_missing_meta_desc":   seo_agg["missing_meta"],
                "pages_missing_h1":          seo_agg["missing_h1"],
                "pages_missing_canonical":   seo_agg["missing_canonical"],
                "total_images":              seo_agg["total_images"],
                "images_missing_alt":        seo_agg["missing_alt"],
                "pages_thin_content":        seo_agg["thin_content"],
                "avg_word_count":            seo_agg["avg_words"],
            },
            "pages": [_page_to_dict(p) for p in self._pages],
            "llm_report": self._llm or {},
        }

    # ------------------------------------------------------------------
    # Text summary builder
    # ------------------------------------------------------------------

    def _build_text(self) -> str:
        """
        Build a formatted, human-readable plain-text report.
        Uses only ASCII box characters — no dependencies, no encoding issues.
        """
        W     = 68     # total line width
        lines = []

        def hr(char="─"):   lines.append(char * W)
        def blank():        lines.append("")
        def title(t):       lines.append(f"  {t}")
        def row(label, val, width=28):
            lines.append(f"  {label:<{width}} {val}")

        stats   = _compute_stats(self._pages)
        seo_agg = _compute_seo_aggregates(self._pages)

        # ── Header ───────────────────────────────────────────────────────
        hr("═")
        title("AI WEB TESTER  —  REPORT")
        hr("═")
        row("Site:",         self.site_url or "(not set)")
        row("Generated:",    self.generated_at)
        row("Total pages:",  str(len(self._pages)))
        hr()
        blank()

        # ── Overall health ────────────────────────────────────────────────
        title("OVERALL HEALTH")
        hr()
        row("Pages passing UI tests:", f"{stats['ui_ok']} / {len(self._pages)}")
        row("Pages with errors:",      str(stats["pages_with_errors"]))
        row("Total console errors:",   str(stats["total_console_errors"]))
        row("Total JS exceptions:",    str(stats["total_js_exceptions"]))
        row("Avg load time:",          f"{stats['avg_load_ms']} ms")
        blank()
        row("Avg SEO score:",   f"{stats['avg_seo']} / 100")
        row("Best SEO score:",  f"{stats['max_seo']} / 100")
        row("Worst SEO score:", f"{stats['min_seo']} / 100")
        row("SEO errors:",      str(stats["total_seo_errors"]))
        row("SEO warnings:",    str(stats["total_seo_warnings"]))
        blank()

        # ── SEO summary ───────────────────────────────────────────────────
        title("SEO SUMMARY")
        hr()
        row("Missing <title>:",          f"{seo_agg['missing_title']} page(s)")
        row("Missing meta description:", f"{seo_agg['missing_meta']} page(s)")
        row("Missing <h1>:",             f"{seo_agg['missing_h1']} page(s)")
        row("Missing canonical tag:",    f"{seo_agg['missing_canonical']} page(s)")
        row("Images missing alt text:",  f"{seo_agg['missing_alt']} / {seo_agg['total_images']}")
        row("Thin content pages:",       f"{seo_agg['thin_content']} page(s) (< 300 words)")
        row("Avg word count:",           str(seo_agg["avg_words"]))
        blank()

        # ── Per-page details ──────────────────────────────────────────────
        title("PAGE-BY-PAGE BREAKDOWN")
        hr()

        for i, page in enumerate(self._pages, 1):
            blank()
            title(f"[{i}] {page.url}")

            # UI
            ui_status = "PASS" if page.ui_success else "FAIL"
            lines.append(f"      UI:  {ui_status}  |  Status {page.status_code}"
                         f"  |  Load {page.load_time_ms:.0f}ms"
                         f"  |  Console errors: {len(page.console_errors)}")

            if page.console_errors:
                for err in page.console_errors[:3]:
                    lines.append(f"          • {err[:80]}")
                if len(page.console_errors) > 3:
                    lines.append(f"          … +{len(page.console_errors)-3} more")

            # SEO
            seo_bar = _score_bar(page.seo_score)
            lines.append(f"      SEO: {page.seo_score:>3}/100  {seo_bar}")

            if page.seo_issues:
                errors   = [x for x in page.seo_issues if x.get("severity") == "error"]
                warnings = [x for x in page.seo_issues if x.get("severity") == "warning"]
                for issue in errors[:3]:
                    lines.append(f"          [ERROR]   {issue['message'][:70]}")
                for issue in warnings[:3]:
                    lines.append(f"          [WARNING] {issue['message'][:70]}")
                total_issues = len(page.seo_issues)
                shown = min(6, total_issues)
                if total_issues > shown:
                    lines.append(f"          … +{total_issues - shown} more issue(s)")

            if page.page_error:
                lines.append(f"      ERROR: {page.page_error[:80]}")

        blank()
        hr()

        # ── Issues summary ────────────────────────────────────────────────
        all_issues = [
            (page.url, issue)
            for page in self._pages
            for issue in page.seo_issues
            if issue.get("severity") == "error"
        ]
        if all_issues:
            blank()
            title("ALL CRITICAL SEO ERRORS")
            hr()
            for url, issue in all_issues[:20]:
                short_url = url.split("//")[-1][:45]
                lines.append(f"  {short_url:<45}  {issue['message'][:40]}")
            if len(all_issues) > 20:
                lines.append(f"  … +{len(all_issues) - 20} more")
            blank()

        # ── LLM report ────────────────────────────────────────────────────
        if self._llm and self._llm.get("success"):
            hr("═")
            title("AI ANALYSIS  (LLM-generated)")
            hr("═")
            blank()

            for section, key in [
                ("EXECUTIVE SUMMARY",  "summary"),
                ("BUG REPORT",         "bug_report"),
                ("SEO IMPROVEMENTS",   "seo_improvements"),
                ("QUICK WINS",         "quick_wins"),
            ]:
                content = (self._llm.get(key) or "").strip()
                if content:
                    title(section)
                    hr()
                    for line in content.splitlines():
                        lines.append(f"  {line}")
                    blank()

        # ── Footer ────────────────────────────────────────────────────────
        hr("═")
        title("END OF REPORT")
        hr("═")
        blank()

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _extract_page_summary(result) -> _PageSummary:
    """
    Convert a PageResult (dataclass or dict) into a flat _PageSummary.
    Accepts both live objects and dict-form (e.g. loaded from JSON).
    """
    # Support both dict and dataclass
    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    url   = _get(result, "url", "")
    error = _get(result, "error")

    ui  = _get(result, "ui")
    seo = _get(result, "seo")

    # UI fields
    status_code    = _get(ui, "status_code",    0)    if ui else 0
    load_time_ms   = _get(ui, "load_time_ms",   0.0)  if ui else 0.0
    ui_success     = _get(ui, "success",         False) if ui else False
    console_errors = _get(ui, "console_errors",  [])   if ui else []
    js_exceptions  = _get(ui, "js_exceptions",   [])   if ui else []

    # SEO fields
    seo_score    = _get(seo, "score",            0)   if seo else 0
    title        = _get(seo, "title",            "")  if seo else ""
    meta_desc    = _get(seo, "meta_description", "")  if seo else ""
    h1_count     = _get(seo, "h1_count",         0)   if seo else 0
    canonical    = _get(seo, "canonical_url",   None) if seo else None
    img_total    = _get(seo, "images_total",     0)   if seo else 0
    img_missing  = _get(seo, "images_missing_alt", 0) if seo else 0
    word_count   = _get(seo, "word_count",       0)   if seo else 0

    # SEO issues — handle both dataclass (with .to_dict()) and plain dict
    raw_issues = _get(seo, "issues", []) if seo else []
    seo_issues = []
    for iss in raw_issues:
        if isinstance(iss, dict):
            seo_issues.append(iss)
        elif hasattr(iss, "to_dict"):
            seo_issues.append(iss.to_dict())
        else:
            seo_issues.append({
                "severity": getattr(iss, "severity", ""),
                "field":    getattr(iss, "field",    ""),
                "message":  getattr(iss, "message",  ""),
            })

    return _PageSummary(
        url            = url,
        status_code    = status_code,
        load_time_ms   = load_time_ms,
        ui_success     = ui_success,
        console_errors = console_errors,
        js_exceptions  = js_exceptions,
        seo_score      = seo_score,
        seo_title      = title,
        seo_meta_desc  = meta_desc,
        seo_h1_count   = h1_count,
        seo_canonical  = canonical,
        seo_images_total  = img_total,
        seo_missing_alt   = img_missing,
        seo_word_count    = word_count,
        seo_issues        = seo_issues,
        page_error        = error,
    )


def _compute_stats(pages: list[_PageSummary]) -> dict:
    """Compute aggregate numeric stats across all pages."""
    if not pages:
        return {k: 0 for k in [
            "ui_ok","ui_failed","pages_with_errors","total_console_errors",
            "total_js_exceptions","avg_load_ms","avg_seo","min_seo",
            "max_seo","total_seo_errors","total_seo_warnings"
        ]}

    seo_scores = [p.seo_score for p in pages if p.seo_score > 0]

    return {
        "ui_ok":               sum(1 for p in pages if p.ui_success),
        "ui_failed":           sum(1 for p in pages if not p.ui_success),
        "pages_with_errors":   sum(1 for p in pages if p.console_errors or p.js_exceptions),
        "total_console_errors":sum(len(p.console_errors) for p in pages),
        "total_js_exceptions": sum(len(p.js_exceptions)  for p in pages),
        "avg_load_ms":         round(sum(p.load_time_ms for p in pages) / len(pages), 1),
        "avg_seo":             round(sum(seo_scores) / len(seo_scores), 1) if seo_scores else 0,
        "min_seo":             min(seo_scores, default=0),
        "max_seo":             max(seo_scores, default=0),
        "total_seo_errors":    sum(
            sum(1 for i in p.seo_issues if i.get("severity") == "error")
            for p in pages
        ),
        "total_seo_warnings":  sum(
            sum(1 for i in p.seo_issues if i.get("severity") == "warning")
            for p in pages
        ),
    }


def _compute_seo_aggregates(pages: list[_PageSummary]) -> dict:
    """Compute SEO-specific field-level aggregates."""
    if not pages:
        return {k: 0 for k in [
            "missing_title","missing_meta","missing_h1","missing_canonical",
            "total_images","missing_alt","thin_content","avg_words"
        ]}

    return {
        "missing_title":     sum(1 for p in pages if not p.seo_title),
        "missing_meta":      sum(1 for p in pages if not p.seo_meta_desc),
        "missing_h1":        sum(1 for p in pages if p.seo_h1_count == 0),
        "missing_canonical": sum(1 for p in pages if p.seo_canonical is None),
        "total_images":      sum(p.seo_images_total for p in pages),
        "missing_alt":       sum(p.seo_missing_alt  for p in pages),
        "thin_content":      sum(1 for p in pages if 0 < p.seo_word_count < 300),
        "avg_words":         round(
            sum(p.seo_word_count for p in pages) / len(pages), 1
        ),
    }


def _page_to_dict(p: _PageSummary) -> dict:
    """Convert _PageSummary to a JSON-serialisable dict."""
    return {
        "url":             p.url,
        "ui": {
            "success":        p.ui_success,
            "status_code":    p.status_code,
            "load_time_ms":   p.load_time_ms,
            "console_errors": p.console_errors,
            "js_exceptions":  p.js_exceptions,
        },
        "seo": {
            "score":          p.seo_score,
            "title":          p.seo_title,
            "meta_description": p.seo_meta_desc,
            "h1_count":       p.seo_h1_count,
            "canonical_url":  p.seo_canonical,
            "images_total":   p.seo_images_total,
            "images_missing_alt": p.seo_missing_alt,
            "word_count":     p.seo_word_count,
            "issues":         p.seo_issues,
        },
        "error": p.page_error,
    }


def _score_bar(score: int, width: int = 20) -> str:
    """Render a simple ASCII progress bar for an SEO score 0–100."""
    filled = round((score / 100) * width)
    bar    = "█" * filled + "░" * (width - filled)
    if score >= 80:   grade = "GOOD"
    elif score >= 60: grade = "FAIR"
    elif score >= 40: grade = "POOR"
    else:             grade = "CRITICAL"
    return f"|{bar}| {grade}"


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------

def generate_report(
    page_results: list,
    site_url:     str           = "",
    llm_report                  = None,
    output_dir:   str           = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    """
    Build and save both reports in one call.

    Args:
        page_results: list[PageResult] from pipeline/run_pipeline.py
        site_url:     Root URL (for display in the report header)
        llm_report:   Optional LLMReport from ai_analysis/analyzer.py
        output_dir:   Directory to write files into

    Returns:
        {"json": "<path>", "txt": "<path>"}

    Example:
        from reports.generate_report import generate_report
        paths = generate_report(results, site_url="https://example.com")
        print(paths["json"])
        print(paths["txt"])
    """
    builder = ReportBuilder(site_url=site_url, output_dir=output_dir)
    builder.add_pages(page_results)
    if llm_report:
        builder.add_llm_report(llm_report)
    return builder.save()


# ---------------------------------------------------------------------------
# CLI  (python reports/generate_report.py --json pipeline_results.json)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate JSON + text reports from saved pipeline results"
    )
    parser.add_argument("--json",   required=True, help="Path to pipeline_results.json")
    parser.add_argument("--url",    default="",    help="Site URL for display")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="Output directory")
    parser.add_argument("--print",  action="store_true", help="Print text summary to console")
    args = parser.parse_args()

    with open(args.json) as f:
        data = json.load(f)

    # Load pages from saved JSON (plain dicts — _extract_page_summary handles both)
    pages = data.get("pages", [])
    url   = args.url or data.get("meta", {}).get("site_url", "")

    builder = ReportBuilder(site_url=url, output_dir=args.output)
    builder.add_pages(pages)

    paths = builder.save()

    if args.print:
        builder.print_summary()

    print(f"\n  Done. Reports written to {args.output}/")