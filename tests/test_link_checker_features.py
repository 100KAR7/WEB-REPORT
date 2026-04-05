import unittest

from crawler.models import PageData
from tests.link_checker import LinkChecker


class StubLinkChecker(LinkChecker):
    def _get_status(self, url: str) -> int:
        return 404 if "missing" in url else 200


class LinkCheckerFeatureTests(unittest.TestCase):
    def test_tracks_all_source_pages_for_each_broken_link(self):
        pages = [
            PageData(
                url="https://example.com/",
                status_code=200,
                links=[
                    "https://example.com/missing",
                    "https://example.com/good",
                ],
            ),
            PageData(
                url="https://example.com/about",
                status_code=200,
                links=["https://example.com/missing"],
            ),
        ]

        broken_links = StubLinkChecker().check(pages)

        self.assertEqual(len(broken_links), 1)
        self.assertEqual(broken_links[0]["broken_url"], "https://example.com/missing")
        self.assertEqual(
            broken_links[0]["source_urls"],
            ["https://example.com/", "https://example.com/about"],
        )
        self.assertEqual(broken_links[0]["occurrences"], 2)


if __name__ == "__main__":
    unittest.main()
