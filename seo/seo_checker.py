"""
seo/seo_checker.py
------------------
Runs a suite of on-page SEO checks against crawled PageData objects.
Each check returns a list of issues with severity: "error" | "warning" | "info"
"""

from crawler.models import PageData
from config.logging_config import logger


class SEOChecker:
    """Runs SEO audits on a list of crawled pages."""

    def check(self, pages: list[PageData]) -> list[dict]:
        all_issues = []
        for page in pages:
            if not page.is_ok:
                continue
            issues = (
                self._check_title(page)
                + self._check_meta_description(page)
                + self._check_headings(page)
                + self._check_images(page)
            )
            if issues:
                all_issues.append({"url": page.url, "issues": issues})

        total = sum(len(r["issues"]) for r in all_issues)
        logger.info(f"SEO check complete. {total} issues found across {len(pages)} pages.")
        return all_issues

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_title(self, page: PageData) -> list[dict]:
        issues = []
        if not page.title:
            issues.append({"severity": "error", "message": "Missing <title> tag"})
        elif len(page.title) < 10:
            issues.append({"severity": "warning", "message": f"Title too short ({len(page.title)} chars)"})
        elif len(page.title) > 60:
            issues.append({"severity": "warning", "message": f"Title too long ({len(page.title)} chars)"})
        return issues

    def _check_meta_description(self, page: PageData) -> list[dict]:
        issues = []
        if not page.meta_description:
            issues.append({"severity": "error", "message": "Missing meta description"})
        elif len(page.meta_description) > 160:
            issues.append({"severity": "warning", "message": "Meta description exceeds 160 chars"})
        return issues

    def _check_headings(self, page: PageData) -> list[dict]:
        issues = []
        if not page.h1_tags:
            issues.append({"severity": "error", "message": "No <h1> tag found"})
        elif len(page.h1_tags) > 1:
            issues.append({"severity": "warning", "message": f"Multiple <h1> tags found ({len(page.h1_tags)})"})
        return issues

    def _check_images(self, page: PageData) -> list[dict]:
        issues = []
        missing_alt = [img["src"] for img in page.images if not img.get("alt")]
        if missing_alt:
            issues.append({
                "severity": "warning",
                "message": f"{len(missing_alt)} image(s) missing alt text",
            })
        return issues
