import json
import os
import shutil
import tempfile
import unittest

from config.settings import settings
from reports.report_generator import ReportGenerator


class ReportGeneratorFeatureTests(unittest.TestCase):
    def test_writes_enhanced_html_and_json_reports(self):
        temp_dir = tempfile.mkdtemp(prefix="web-report-")
        original_output_dir = settings.report_output_dir
        original_format = settings.report_format

        try:
            settings.report_output_dir = temp_dir
            settings.report_format = "both"

            path = ReportGenerator().generate(
                target_url="https://example.com",
                performance=[],
                broken_links=[
                    {
                        "source_url": "https://example.com/",
                        "source_urls": ["https://example.com/"],
                        "broken_url": "https://example.com/missing",
                        "status_code": 404,
                        "occurrences": 1,
                    }
                ],
                seo=[
                    {
                        "url": "https://example.com/",
                        "title": "Example",
                        "score": 95,
                        "issue_counts": {"error": 0, "warning": 1, "info": 0, "total": 1},
                        "issues": [
                            {
                                "severity": "warning",
                                "field": "title",
                                "code": "duplicate_title",
                                "message": "Duplicate <title> shared across 2 pages",
                            }
                        ],
                    }
                ],
                ai_insights=[],
                summary={
                    "overall_score": 82,
                    "overall_rating": "Watch",
                    "overall_rating_class": "watch",
                    "total_pages": 1,
                    "successful_pages": 1,
                    "failed_pages": 0,
                    "average_load_time_ms": 760,
                    "slow_pages": 0,
                    "broken_links": 1,
                    "broken_link_occurrences": 1,
                    "pages_with_broken_links": 1,
                    "total_seo_issues": 1,
                    "critical_seo_issues": 0,
                    "duplicate_groups": 1,
                    "pages_with_duplicates": 1,
                    "ai_insight_pages": 0,
                    "healthy_pages": 0,
                    "watch_pages": 1,
                    "critical_pages": 0,
                },
                seo_summary={
                    "total_issues": 1,
                    "errors": 0,
                    "warnings": 1,
                    "info": 0,
                    "pages_missing_title": 0,
                    "pages_missing_meta_description": 0,
                    "pages_missing_h1": 0,
                    "pages_missing_alt_text": 0,
                    "duplicate_title_groups": 1,
                    "duplicate_meta_description_groups": 0,
                    "duplicate_h1_groups": 0,
                    "pages_with_duplicate_titles": 1,
                    "pages_with_duplicate_meta_descriptions": 0,
                    "pages_with_duplicate_h1s": 0,
                    "top_issue_fields": [{"field": "title", "count": 1}],
                },
                page_health=[
                    {
                        "url": "https://example.com/",
                        "title": "Example",
                        "status_code": 200,
                        "load_time_ms": 760,
                        "performance_label": "Good",
                        "performance_score_value": 84,
                        "health_score": 82,
                        "health_status": "Watch",
                        "health_class": "watch",
                        "seo_score": 95,
                        "seo_issue_count": 1,
                        "critical_issue_count": 0,
                        "broken_links_count": 1,
                        "has_ai_insight": False,
                        "top_issues": ["Duplicate <title> shared across 2 pages"],
                    }
                ],
                sitewide_findings=[
                    {
                        "field": "title",
                        "code": "duplicate_title",
                        "severity": "warning",
                        "severity_class": "warning",
                        "value": "Example",
                        "url_count": 2,
                        "urls": ["https://example.com/", "https://example.com/about"],
                        "message": "Duplicate <title> shared across 2 pages",
                    }
                ],
                recommendations=[
                    {
                        "priority": "Medium",
                        "priority_class": "medium",
                        "title": "Consolidate duplicate metadata",
                        "message": "1 duplicate metadata group was detected.",
                    }
                ],
            )

            html_path = path
            json_path = html_path.replace(".html", ".json")

            self.assertTrue(os.path.exists(html_path))
            self.assertTrue(os.path.exists(json_path))

            with open(html_path, encoding="utf-8") as file_handle:
                html = file_handle.read()
            with open(json_path, encoding="utf-8") as file_handle:
                payload = json.load(file_handle)

            self.assertIn("Recommended next moves", html)
            self.assertIn("Page health ranking", html)
            self.assertIn("Duplicate &lt;title&gt; shared across 2 pages", html)
            self.assertEqual(payload["summary"]["overall_score"], 82)
            self.assertEqual(payload["page_health"][0]["health_status"], "Watch")
            self.assertEqual(payload["sitewide_findings"][0]["code"], "duplicate_title")

        finally:
            settings.report_output_dir = original_output_dir
            settings.report_format = original_format
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    unittest.main()
