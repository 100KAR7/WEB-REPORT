"""
pipeline/runner.py
------------------
Orchestrates the full audit pipeline:
  Crawl → Tests → SEO → AI Analysis → Report
"""

from config.settings import settings
from config.logging_config import logger
from crawler.page_crawler import PageCrawler
from tests.link_checker import LinkChecker
from tests.performance_checker import PerformanceChecker
from seo.seo_checker import SEOChecker
from ai_analysis.ai_analyzer import AIAnalyzer
from reports.report_context import build_report_context
from reports.report_generator import ReportGenerator


class PipelineRunner:
    """Runs every audit module in sequence and produces a final report."""

    def __init__(self, url: str, max_pages: int = 10):
        self.url = url
        settings.target_url = url
        settings.max_pages = max_pages

    def run(self) -> str:
        """
        Execute the pipeline and return the path to the generated report.
        """
        return self.run_with_details()["report_path"]

    def run_with_details(self) -> dict:
        """
        Execute the pipeline and return full run details for API consumers.
        """
        logger.info(f"Starting AI Web Tester for: {self.url}")

        # ── Step 1: Crawl ──────────────────────────────────────────────
        logger.info("Step 1/5 — Crawling pages...")
        pages = PageCrawler().crawl(self.url)
        logger.info(f"  Crawled {len(pages)} page(s).")

        # ── Step 2: Performance ────────────────────────────────────────
        logger.info("Step 2/5 — Checking performance...")
        performance = []
        if settings.run_performance:
            performance = PerformanceChecker().check(pages)

        # ── Step 3: Broken links ───────────────────────────────────────
        logger.info("Step 3/5 — Checking links...")
        broken_links = LinkChecker().check(pages)

        # ── Step 4: SEO ────────────────────────────────────────────────
        logger.info("Step 4/5 — Running SEO audit...")
        seo = []
        sitewide_findings = []
        if settings.run_seo:
            seo_report = SEOChecker().check(pages)
            seo = seo_report["pages"]
            sitewide_findings = seo_report["sitewide_findings"]

        # ── Step 5: AI Analysis ────────────────────────────────────────
        logger.info("Step 5/5 — Running AI analysis...")
        ai_insights = []
        ai_status = {
            "enabled": settings.run_ai_analysis,
            "attempted": False,
            "status": "skipped",
            "provider": "",
            "model": "",
            "endpoint": "",
            "pages_considered": len(pages),
            "pages_eligible": 0,
            "insights_count": 0,
            "message": "AI analysis disabled by configuration.",
        }
        if settings.run_ai_analysis:
            try:
                analyzer = AIAnalyzer()
                ai_status.update(analyzer.backend_details())
                ai_status["attempted"] = True

                eligible_pages = analyzer.eligible_pages(pages)
                ai_status["pages_eligible"] = len(eligible_pages)

                if not eligible_pages:
                    ai_status["status"] = "no_content"
                    ai_status["message"] = (
                        "No crawled pages had a successful response and extractable text "
                        "for AI analysis."
                    )
                else:
                    ai_insights = analyzer.analyze(pages)
                    ai_status.update(analyzer.backend_details())
                    ai_status["insights_count"] = len(ai_insights)
                    if ai_insights:
                        ai_status["status"] = "completed"
                        ai_status["message"] = (
                            f"Generated {len(ai_insights)} AI insight(s) "
                            f"from {len(eligible_pages)} eligible page(s)."
                        )
                    else:
                        ai_status["status"] = "no_content"
                        ai_status["message"] = (
                            "The AI backend ran, but it did not return any insight text."
                        )
            except Exception as exc:
                logger.warning(f"AI analysis unavailable - {exc}")
                ai_status["attempted"] = True
                ai_status["status"] = "failed"
                ai_status["message"] = str(exc)
                ai_insights = [{
                    "url": "AI backend status",
                    "insight": f"Analysis unavailable: {exc}",
                }]

        # ── Report ─────────────────────────────────────────────────────
        logger.info("Generating report...")
        report_context = build_report_context(
            target_url=self.url,
            pages=pages,
            performance=performance,
            broken_links=broken_links,
            seo=seo,
            ai_insights=ai_insights,
            sitewide_findings=sitewide_findings,
        )
        report_path = ReportGenerator().generate(
            target_url=self.url,
            performance=performance,
            broken_links=broken_links,
            seo=seo,
            ai_insights=ai_insights,
            summary=report_context["summary"],
            seo_summary=report_context["seo_summary"],
            page_health=report_context["page_health"],
            sitewide_findings=report_context["sitewide_findings"],
            recommendations=report_context["recommendations"],
            ai_status=ai_status,
        )

        logger.info(f"Done. Report saved to: {report_path}")
        return {
            "report_path": report_path,
            "target_url": self.url,
            "performance": performance,
            "broken_links": broken_links,
            "seo": seo,
            "ai_insights": ai_insights,
            "ai_status": ai_status,
            "pages_crawled": len(pages),
        }
