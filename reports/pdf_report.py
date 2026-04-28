"""
reports/pdf_report.py
----------------------
Generates a professional PDF report from pipeline + LLM analysis results.

Uses ReportLab (pure Python, no external tools needed).

Install:
    pip install reportlab

Output:
    output/report_<timestamp>.pdf

Usage:
    from reports.pdf_report import PDFReportBuilder, generate_pdf_report

    # Simple one-liner
    path = generate_pdf_report(
        page_results,
        site_url   = "https://example.com",
        llm_report = llm_report,         # optional
    )

    # Full builder (more control)
    builder = PDFReportBuilder(site_url="https://example.com")
    builder.add_pages(page_results)
    builder.add_llm_report(llm_report)
    path = builder.save("output/my_report.pdf")
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

try:
    from reportlab.lib import colors as rl_colors
    _DARK_BLUE  = rl_colors.HexColor("#1a1a2e")
    _ACCENT     = rl_colors.HexColor("#e94560")
    _MID_GRAY   = rl_colors.HexColor("#555555")
    _LIGHT_GRAY = rl_colors.HexColor("#f4f4f4")
    _GREEN      = rl_colors.HexColor("#27ae60")
    _ORANGE     = rl_colors.HexColor("#f0a500")
    _WHITE      = rl_colors.white
    _BLACK      = rl_colors.black
except ImportError:
    pass   # ImportError raised at build time with a helpful message


# ---------------------------------------------------------------------------
# PDF Builder
# ---------------------------------------------------------------------------

class PDFReportBuilder:
    """
    Builds a multi-page PDF report from pipeline + LLM results.

    Pages:
      1. Cover page       — site URL, date, summary stats
      2. Overview table   — per-page UI status + SEO score
      3. SEO details      — issues breakdown per page
      4. LLM analysis     — executive summary, bug report, quick wins
      5. Appendix         — full issue list
    """

    def __init__(
        self,
        site_url:   str = "",
        output_dir: str = "output",
    ):
        self.site_url   = site_url
        self.output_dir = output_dir
        self._pages:    list        = []      # raw PageResult / dict objects
        self._llm:      Optional[dict] = None

    # ------------------------------------------------------------------
    # Data ingestion (same API as ReportBuilder)
    # ------------------------------------------------------------------

    def add_pages(self, page_results: list) -> "PDFReportBuilder":
        self._pages = list(page_results)
        return self

    def add_llm_report(self, llm_report) -> "PDFReportBuilder":
        if llm_report is None:
            return self
        self._llm = (
            llm_report.to_dict()
            if hasattr(llm_report, "to_dict")
            else llm_report
        )
        return self

    # ------------------------------------------------------------------
    # Build and save
    # ------------------------------------------------------------------

    def save(self, path: Optional[str] = None) -> str:
        """Build the PDF and write it to *path*. Returns the file path."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import (
                SimpleDocTemplate, PageBreak,
            )
            from reportlab.lib.units import cm
        except ImportError:
            raise ImportError(
                "ReportLab is not installed.\n"
                "Run:  pip install reportlab"
            )

        os.makedirs(self.output_dir, exist_ok=True)
        if not path:
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.output_dir, f"report_{ts}.pdf")

        doc   = SimpleDocTemplate(
            path,
            pagesize    = A4,
            rightMargin = 2 * cm,
            leftMargin  = 2 * cm,
            topMargin   = 2 * cm,
            bottomMargin= 2 * cm,
            title       = f"AI Web Tester — {self.site_url}",
            author      = "AI Web Tester",
        )

        styles = self._make_styles()
        story  = []

        # ── Pages ─────────────────────────────────────────────────────────
        story += self._cover_page(styles)
        story += [PageBreak()]
        story += self._overview_table(styles)
        story += [PageBreak()]
        story += self._seo_details(styles)

        if self._llm and self._llm.get("success"):
            story += [PageBreak()]
            story += self._llm_section(styles)

        story += [PageBreak()]
        story += self._appendix(styles)

        doc.build(story, onFirstPage=self._header_footer, onLaterPages=self._header_footer)
        print(f"  PDF report saved -> {path}")
        return path

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    def _cover_page(self, styles: dict) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import cm

        stats = self._compute_stats()
        story = []

        story.append(Spacer(1, 2 * cm))
        story.append(Paragraph("AI Web Tester", styles["cover_title"]))
        story.append(Paragraph("Automated Website Audit Report", styles["cover_sub"]))
        story.append(Spacer(1, 0.5 * cm))
        story.append(HRFlowable(width="100%", thickness=2, color=_ACCENT))
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph(f"Site: {self.site_url}", styles["cover_url"]))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            styles["cover_meta"]
        ))
        story.append(Spacer(1, 1.5 * cm))

        # Summary stat boxes
        data = [
            ["Pages Tested", "UI Passed", "Avg SEO Score", "Total Issues"],
            [
                str(stats["total"]),
                f"{stats['ui_ok']} / {stats['total']}",
                f"{stats['avg_seo']} / 100",
                str(stats["total_issues"]),
            ],
        ]
        t = Table(data, colWidths=["25%", "25%", "25%", "25%"])
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), _DARK_BLUE),
            ("TEXTCOLOR",    (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0), 10),
            ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 1), (-1, 1), 22),
            ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS",(0, 1), (-1, 1), [_LIGHT_GRAY]),
            ("GRID",         (0, 0), (-1, -1), 0.5, _MID_GRAY),
            ("TOPPADDING",   (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ]))
        story.append(t)

        if self._llm and self._llm.get("summary"):
            story.append(Spacer(1, 1 * cm))
            story.append(Paragraph("Executive Summary", styles["section_h"]))
            story.append(Paragraph(self._llm["summary"], styles["body"]))

        return story

    def _overview_table(self, styles: dict) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import cm

        story = [
            Paragraph("Page Overview", styles["section_h"]),
            Spacer(1, 0.3 * cm),
        ]

        header = ["URL", "Status", "Load (ms)", "Console Errors", "SEO Score"]
        rows   = [header]

        for r in self._pages:
            url  = _get(r, "url", "")
            ui   = _get(r, "ui")
            seo  = _get(r, "seo")

            status = str(_get(ui, "status_code", "—")) if ui else "—"
            load   = f"{_get(ui, 'load_time_ms', 0):.0f}" if ui else "—"
            errs   = str(len(_get(ui, "console_errors", []))) if ui else "—"
            score  = f"{_get(seo, 'score', 0)}/100" if seo else "—"

            # Truncate long URLs
            display_url = url if len(url) <= 55 else url[:52] + "..."
            rows.append([display_url, status, load, errs, score])

        col_w = ["45%", "12%", "13%", "15%", "15%"]
        t = Table(rows, colWidths=col_w, repeatRows=1)

        style = [
            ("BACKGROUND",   (0, 0), (-1, 0), _DARK_BLUE),
            ("TEXTCOLOR",    (0, 0), (-1, 0), _WHITE),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, -1), 8),
            ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",         (0, 0), (-1, -1), 0.4, _MID_GRAY),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_WHITE, _LIGHT_GRAY]),
            ("TOPPADDING",   (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
            ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ]
        # Highlight failed rows in light red
        for i, row in enumerate(rows[1:], 1):
            if row[1] not in ("200", "—") or row[3] not in ("0", "—"):
                style.append(("BACKGROUND", (0, i), (-1, i), rl_colors.HexColor("#fdecea")))

        t.setStyle(TableStyle(style))
        story.append(t)
        return story

    def _seo_details(self, styles: dict) -> list:
        from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.units import cm

        story = [
            Paragraph("SEO Details", styles["section_h"]),
            Spacer(1, 0.3 * cm),
        ]

        for r in self._pages:
            url = _get(r, "url", "")
            seo = _get(r, "seo")
            if not seo:
                continue

            score  = _get(seo, "score", 0)
            issues = _get(seo, "issues", [])
            errors   = [i for i in issues if _get(i, "severity") == "error"]
            warnings = [i for i in issues if _get(i, "severity") == "warning"]

            # Score colour
            score_color = _GREEN if score >= 80 else (_ORANGE if score >= 60 else _ACCENT)

            story.append(Paragraph(url, styles["page_url"]))
            story.append(Paragraph(
                f'SEO Score: <font color="{score_color.hexval() if hasattr(score_color,"hexval") else "#000"}">'
                f'<b>{score}/100</b></font>   '
                f'Errors: {len(errors)}   Warnings: {len(warnings)}',
                styles["body"]
            ))

            if issues:
                data = [["Severity", "Field", "Issue"]]
                for iss in issues[:15]:
                    data.append([
                        _get(iss, "severity", "").upper(),
                        _get(iss, "field", ""),
                        _get(iss, "message", ""),
                    ])
                t = Table(data, colWidths=["15%", "15%", "70%"], repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND",   (0, 0), (-1, 0), _DARK_BLUE),
                    ("TEXTCOLOR",    (0, 0), (-1, 0), _WHITE),
                    ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",     (0, 0), (-1, -1), 8),
                    ("GRID",         (0, 0), (-1, -1), 0.4, _MID_GRAY),
                    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_WHITE, _LIGHT_GRAY]),
                    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING",   (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
                    ("LEFTPADDING",  (0, 0), (-1, -1), 5),
                ]))
                story.append(Spacer(1, 0.2 * cm))
                story.append(t)

            story.append(HRFlowable(width="100%", thickness=0.5, color=_MID_GRAY))
            story.append(Spacer(1, 0.3 * cm))

        return story

    def _llm_section(self, styles: dict) -> list:
        from reportlab.platypus import Paragraph, Spacer
        from reportlab.lib.units import cm

        story = [
            Paragraph("AI Analysis (Ollama LLM)", styles["section_h"]),
            Paragraph(
                f"Model: {self._llm.get('model_used', 'unknown')}  |  "
                f"Backend: {self._llm.get('backend', 'ollama')}",
                styles["meta"]
            ),
            Spacer(1, 0.3 * cm),
        ]

        for section_title, key in [
            ("Executive Summary",  "summary"),
            ("Bug Report",         "bug_report"),
            ("SEO Improvements",   "seo_improvements"),
            ("Quick Wins",         "quick_wins"),
        ]:
            content = (self._llm.get(key) or "").strip()
            if content:
                story.append(Paragraph(section_title, styles["subsection_h"]))
                # Split into paragraphs on double newline
                for para in content.split("\n\n"):
                    para = para.strip()
                    if para:
                        # Escape XML special chars for ReportLab
                        para = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        story.append(Paragraph(para, styles["body"]))
                        story.append(Spacer(1, 0.15 * cm))
                story.append(Spacer(1, 0.3 * cm))

        return story

    def _appendix(self, styles: dict) -> list:
        from reportlab.platypus import Paragraph, Spacer
        from reportlab.lib.units import cm

        story = [
            Paragraph("Appendix — All SEO Issues", styles["section_h"]),
            Spacer(1, 0.3 * cm),
        ]

        all_issues = []
        for r in self._pages:
            seo    = _get(r, "seo")
            url    = _get(r, "url", "")
            issues = _get(seo, "issues", []) if seo else []
            for iss in issues:
                all_issues.append({
                    "url":      url,
                    "severity": _get(iss, "severity", ""),
                    "field":    _get(iss, "field",    ""),
                    "message":  _get(iss, "message",  ""),
                })

        if not all_issues:
            story.append(Paragraph("No SEO issues found.", styles["body"]))
            return story

        story.append(Paragraph(f"Total: {len(all_issues)} issue(s) across {len(self._pages)} page(s)", styles["meta"]))
        story.append(Spacer(1, 0.2 * cm))

        for iss in all_issues:
            sev = iss["severity"].upper()
            story.append(Paragraph(
                f'[{sev}] <b>{iss["field"]}</b> — {iss["message"]}',
                styles["issue_line"]
            ))
            story.append(Paragraph(iss["url"], styles["issue_url"]))
            story.append(Spacer(1, 0.1 * cm))

        return story

    # ------------------------------------------------------------------
    # Page decorations (header + footer on every page)
    # ------------------------------------------------------------------

    def _header_footer(self, canvas, doc):
        from reportlab.lib.units import cm

        canvas.saveState()
        w, h = doc.pagesize

        # Header line
        canvas.setStrokeColor(_ACCENT)
        canvas.setLineWidth(2)
        canvas.line(2 * cm, h - 1.5 * cm, w - 2 * cm, h - 1.5 * cm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(_DARK_BLUE)
        canvas.drawString(2 * cm, h - 1.2 * cm, "AI Web Tester")
        canvas.setFillColor(_MID_GRAY)
        canvas.drawRightString(w - 2 * cm, h - 1.2 * cm, self.site_url)

        # Footer
        canvas.setStrokeColor(_LIGHT_GRAY)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.5 * cm, w - 2 * cm, 1.5 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_MID_GRAY)
        canvas.drawString(2 * cm, 1.1 * cm,
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        canvas.drawRightString(w - 2 * cm, 1.1 * cm, f"Page {doc.page}")

        canvas.restoreState()

    # ------------------------------------------------------------------
    # Style definitions
    # ------------------------------------------------------------------

    def _make_styles(self) -> dict:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        return {
            "cover_title":  ParagraphStyle("cover_title",
                fontName="Helvetica-Bold", fontSize=32,
                textColor=_DARK_BLUE, alignment=TA_CENTER, spaceAfter=8),
            "cover_sub":    ParagraphStyle("cover_sub",
                fontName="Helvetica", fontSize=16,
                textColor=_MID_GRAY, alignment=TA_CENTER, spaceAfter=20),
            "cover_url":    ParagraphStyle("cover_url",
                fontName="Helvetica-Bold", fontSize=12,
                textColor=_ACCENT, alignment=TA_CENTER, spaceAfter=4),
            "cover_meta":   ParagraphStyle("cover_meta",
                fontName="Helvetica", fontSize=9,
                textColor=_MID_GRAY, alignment=TA_CENTER, spaceAfter=20),
            "section_h":    ParagraphStyle("section_h",
                fontName="Helvetica-Bold", fontSize=16,
                textColor=_DARK_BLUE, spaceBefore=12, spaceAfter=6,
                borderPad=4),
            "subsection_h": ParagraphStyle("subsection_h",
                fontName="Helvetica-Bold", fontSize=12,
                textColor=_ACCENT, spaceBefore=8, spaceAfter=4),
            "page_url":     ParagraphStyle("page_url",
                fontName="Helvetica-Bold", fontSize=9,
                textColor=_DARK_BLUE, spaceBefore=6, spaceAfter=2),
            "body":         ParagraphStyle("body",
                fontName="Helvetica", fontSize=9,
                textColor=_BLACK, leading=14, spaceAfter=4),
            "meta":         ParagraphStyle("meta",
                fontName="Helvetica", fontSize=8,
                textColor=_MID_GRAY, spaceAfter=4),
            "issue_line":   ParagraphStyle("issue_line",
                fontName="Helvetica", fontSize=8,
                textColor=_BLACK, leading=12),
            "issue_url":    ParagraphStyle("issue_url",
                fontName="Helvetica", fontSize=7,
                textColor=_MID_GRAY, leftIndent=10),
        }

    # ------------------------------------------------------------------
    # Stats helper
    # ------------------------------------------------------------------

    def _compute_stats(self) -> dict:
        total      = len(self._pages)
        ui_ok      = 0
        seo_scores = []
        issues     = 0

        for r in self._pages:
            ui  = _get(r, "ui")
            seo = _get(r, "seo")
            if ui and _get(ui, "success"):
                ui_ok += 1
            if seo:
                seo_scores.append(_get(seo, "score", 0))
                issues += len(_get(seo, "issues", []))

        return {
            "total":       total,
            "ui_ok":       ui_ok,
            "avg_seo":     round(sum(seo_scores) / len(seo_scores), 1) if seo_scores else 0,
            "total_issues":issues,
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get(obj, key, default=None):
    """Get a value from a dict or dataclass attribute."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Convenience one-liner
# ---------------------------------------------------------------------------

def generate_pdf_report(
    page_results: list,
    site_url:     str           = "",
    llm_report                  = None,
    output_dir:   str           = "output",
    path:         Optional[str] = None,
) -> str:
    """
    Build and save a PDF report in one call.

    Args:
        page_results: list[PageResult] from pipeline/run_pipeline.py
        site_url:     Root URL (shown in the report header)
        llm_report:   Optional LLMReport from ai_analysis/analyzer.py
        output_dir:   Directory to write the PDF into
        path:         Override the full output path

    Returns:
        Path to the generated PDF file.

    Example:
        from reports.pdf_report import generate_pdf_report
        path = generate_pdf_report(results, site_url="https://example.com")
        print(path)   # output/report_20240315_143022.pdf
    """
    builder = PDFReportBuilder(site_url=site_url, output_dir=output_dir)
    builder.add_pages(page_results)
    if llm_report:
        builder.add_llm_report(llm_report)
    return builder.save(path)


# ---------------------------------------------------------------------------
# CLI  (python reports/pdf_report.py --json output/pipeline_results.json)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Generate PDF report from saved pipeline results")
    parser.add_argument("--json",   required=True, help="Path to pipeline_results.json")
    parser.add_argument("--url",    default="",    help="Site URL for display")
    parser.add_argument("--output", default="output", help="Output directory")
    args = parser.parse_args()

    with open(args.json) as f:
        data = json.load(f)

    pages = data.get("pages", [])
    url   = args.url or data.get("meta", {}).get("site_url", "")

    path = generate_pdf_report(pages, site_url=url, output_dir=args.output)
    print(f"Done -> {path}")
