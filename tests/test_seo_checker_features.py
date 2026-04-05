import unittest

from crawler.models import PageData
from seo.seo_checker import SEOChecker


class SEOCheckerFeatureTests(unittest.TestCase):
    def test_detects_duplicate_metadata_and_updates_page_scores(self):
        pages = [
            PageData(
                url="https://example.com/",
                status_code=200,
                title="Welcome to Example",
                meta_description="Example home page with strong positioning.",
                h1_tags=["Example Home"],
                images=[],
            ),
            PageData(
                url="https://example.com/about",
                status_code=200,
                title="Welcome to Example",
                meta_description="Example home page with strong positioning.",
                h1_tags=["Example Home"],
                images=[],
            ),
            PageData(
                url="https://example.com/contact",
                status_code=200,
                title="Contact Example",
                meta_description="Reach out to the Example team for support and sales.",
                h1_tags=["Contact us"],
                images=[],
            ),
        ]

        result = SEOChecker().check(pages)
        by_url = {item["url"]: item for item in result["pages"]}

        self.assertEqual(len(result["pages"]), 3)
        self.assertEqual(len(result["sitewide_findings"]), 3)

        duplicate_codes = {finding["code"] for finding in result["sitewide_findings"]}
        self.assertEqual(
            duplicate_codes,
            {"duplicate_title", "duplicate_meta_description", "duplicate_h1"},
        )

        home_codes = {issue["code"] for issue in by_url["https://example.com/"]["issues"]}
        about_codes = {issue["code"] for issue in by_url["https://example.com/about"]["issues"]}
        contact_codes = {issue["code"] for issue in by_url["https://example.com/contact"]["issues"]}

        self.assertTrue({"duplicate_title", "duplicate_meta_description", "duplicate_h1"} <= home_codes)
        self.assertTrue({"duplicate_title", "duplicate_meta_description", "duplicate_h1"} <= about_codes)
        self.assertEqual(contact_codes, set())

        self.assertEqual(by_url["https://example.com/"]["issue_counts"]["warning"], 3)
        self.assertEqual(by_url["https://example.com/"]["score"], 85)
        self.assertEqual(by_url["https://example.com/contact"]["score"], 100)


if __name__ == "__main__":
    unittest.main()
