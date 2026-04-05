import unittest

from crawler.models import PageData
from reports.report_context import build_report_context


class ReportContextTests(unittest.TestCase):
    def test_builds_summary_page_health_and_recommendations(self):
        pages = [
            PageData(
                url="https://example.com/",
                status_code=200,
                title="Home",
                load_time_ms=850,
            ),
            PageData(
                url="https://example.com/about",
                status_code=200,
                title="About",
                load_time_ms=2450,
            ),
        ]
        performance = [
            {
                "url": "https://example.com/",
                "load_time_ms": 850,
                "is_slow": False,
                "score": "Good",
                "score_value": 84,
            },
            {
                "url": "https://example.com/about",
                "load_time_ms": 2450,
                "is_slow": True,
                "score": "Poor",
                "score_value": 42,
            },
        ]
        broken_links = [
            {
                "source_url": "https://example.com/about",
                "source_urls": ["https://example.com/", "https://example.com/about"],
                "broken_url": "https://example.com/missing",
                "status_code": 404,
                "occurrences": 2,
            }
        ]
        seo = [
            {
                "url": "https://example.com/",
                "title": "Home",
                "score": 95,
                "issue_counts": {"error": 0, "warning": 1, "info": 0, "total": 1},
                "issues": [
                    {
                        "severity": "warning",
                        "field": "title",
                        "code": "duplicate_title",
                        "message": "Duplicate <title> shared across 2 pages",
                        "scope": "sitewide",
                    }
                ],
            },
            {
                "url": "https://example.com/about",
                "title": "About",
                "score": 80,
                "issue_counts": {"error": 1, "warning": 1, "info": 0, "total": 2},
                "issues": [
                    {
                        "severity": "error",
                        "field": "meta_description",
                        "code": "missing_meta_description",
                        "message": "Missing meta description",
                        "scope": "page",
                    },
                    {
                        "severity": "warning",
                        "field": "title",
                        "code": "duplicate_title",
                        "message": "Duplicate <title> shared across 2 pages",
                        "scope": "sitewide",
                    },
                ],
            },
        ]
        sitewide_findings = [
            {
                "field": "title",
                "code": "duplicate_title",
                "severity": "warning",
                "value": "Home",
                "url_count": 2,
                "urls": ["https://example.com/", "https://example.com/about"],
                "message": "Duplicate <title> shared across 2 pages",
            }
        ]
        ai_insights = [{"url": "https://example.com/", "insight": "Clarify the hero copy."}]

        context = build_report_context(
            target_url="https://example.com",
            pages=pages,
            performance=performance,
            broken_links=broken_links,
            seo=seo,
            ai_insights=ai_insights,
            sitewide_findings=sitewide_findings,
        )

        self.assertEqual(context["summary"]["total_pages"], 2)
        self.assertEqual(context["summary"]["broken_links"], 1)
        self.assertEqual(context["summary"]["broken_link_occurrences"], 2)
        self.assertEqual(context["summary"]["duplicate_groups"], 1)
        self.assertEqual(context["summary"]["ai_insight_pages"], 1)
        self.assertEqual(context["seo_summary"]["pages_missing_meta_description"], 1)

        lowest_page = context["page_health"][0]
        self.assertEqual(lowest_page["url"], "https://example.com/about")
        self.assertEqual(lowest_page["health_status"], "Critical")
        self.assertGreaterEqual(len(context["recommendations"]), 3)
        self.assertEqual(context["recommendations"][0]["title"], "Repair broken links")


if __name__ == "__main__":
    unittest.main()
