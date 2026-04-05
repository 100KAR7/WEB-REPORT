"""
seo/seo_checker.py
------------------
Runs page-level and sitewide SEO checks against crawled PageData objects.
"""

from __future__ import annotations

from collections import defaultdict

from crawler.models import PageData
from config.logging_config import logger


class SEOChecker:
    """Runs SEO audits on a list of crawled pages."""

    def check(self, pages: list[PageData]) -> dict:
        """
        Returns a report structure with per-page issues and sitewide findings.
        """
        page_results = []
        results_by_url = {}

        for page in pages:
            if not page.is_ok:
                continue

            issues = (
                self._check_title(page)
                + self._check_meta_description(page)
                + self._check_headings(page)
                + self._check_images(page)
            )
            result = {
                "url": page.url,
                "title": page.title,
                "issues": issues,
            }
            page_results.append(result)
            results_by_url[page.url] = result

        sitewide_findings = self._check_duplicate_metadata(pages, results_by_url)

        for result in page_results:
            issue_counts = self._count_issues(result["issues"])
            result["issue_counts"] = issue_counts
            result["score"] = self._score(issue_counts)

        total = sum(r["issue_counts"]["total"] for r in page_results)
        logger.info(
            f"SEO check complete. {total} issues found across {len(page_results)} page(s)."
        )
        return {
            "pages": page_results,
            "sitewide_findings": sitewide_findings,
        }

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_title(self, page: PageData) -> list[dict]:
        issues = []
        if not page.title:
            issues.append(self._issue(
                "error", "title", "missing_title", "Missing <title> tag"
            ))
        elif len(page.title) < 10:
            issues.append(self._issue(
                "warning",
                "title",
                "short_title",
                f"Title too short ({len(page.title)} chars)",
            ))
        elif len(page.title) > 60:
            issues.append(self._issue(
                "warning",
                "title",
                "long_title",
                f"Title too long ({len(page.title)} chars)",
            ))
        return issues

    def _check_meta_description(self, page: PageData) -> list[dict]:
        issues = []
        if not page.meta_description:
            issues.append(self._issue(
                "error",
                "meta_description",
                "missing_meta_description",
                "Missing meta description",
            ))
        elif len(page.meta_description) > 160:
            issues.append(self._issue(
                "warning",
                "meta_description",
                "long_meta_description",
                "Meta description exceeds 160 chars",
            ))
        return issues

    def _check_headings(self, page: PageData) -> list[dict]:
        issues = []
        if not page.h1_tags:
            issues.append(self._issue(
                "error", "h1", "missing_h1", "No <h1> tag found"
            ))
        elif len(page.h1_tags) > 1:
            issues.append(self._issue(
                "warning",
                "h1",
                "multiple_h1",
                f"Multiple <h1> tags found ({len(page.h1_tags)})",
            ))
        return issues

    def _check_images(self, page: PageData) -> list[dict]:
        issues = []
        missing_alt = [img["src"] for img in page.images if not img.get("alt")]
        if missing_alt:
            issues.append(self._issue(
                "warning",
                "images",
                "missing_image_alt_text",
                f"{len(missing_alt)} image(s) missing alt text",
                affected_assets=missing_alt,
            ))
        return issues

    def _check_duplicate_metadata(
        self,
        pages: list[PageData],
        results_by_url: dict[str, dict],
    ) -> list[dict]:
        ok_pages = [page for page in pages if page.is_ok]
        findings = []

        specs = [
            ("title", "duplicate_title", lambda page: page.title),
            ("meta_description", "duplicate_meta_description", lambda page: page.meta_description),
            ("h1", "duplicate_h1", lambda page: page.h1_tags[0] if page.h1_tags else ""),
        ]

        for field, code, getter in specs:
            groups: dict[str, list[PageData]] = defaultdict(list)
            for page in ok_pages:
                value = getter(page)
                normalized = self._normalize(value)
                if normalized:
                    groups[normalized].append(page)

            for grouped_pages in groups.values():
                if len(grouped_pages) < 2:
                    continue

                urls = sorted(page.url for page in grouped_pages)
                sample_value = getter(grouped_pages[0]).strip()
                finding = {
                    "field": field,
                    "code": code,
                    "severity": "warning",
                    "value": self._truncate(sample_value),
                    "url_count": len(urls),
                    "urls": urls,
                    "message": self._duplicate_message(field, len(urls)),
                }
                findings.append(finding)

                for page in grouped_pages:
                    results_by_url[page.url]["issues"].append(self._issue(
                        "warning",
                        field,
                        code,
                        self._duplicate_message(field, len(urls)),
                        scope="sitewide",
                        related_urls=[url for url in urls if url != page.url],
                    ))

        findings.sort(key=lambda item: (item["field"], item["value"]))
        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_issues(self, issues: list[dict]) -> dict:
        errors = sum(1 for issue in issues if issue["severity"] == "error")
        warnings = sum(1 for issue in issues if issue["severity"] == "warning")
        info = sum(1 for issue in issues if issue["severity"] == "info")
        return {
            "error": errors,
            "warning": warnings,
            "info": info,
            "total": errors + warnings + info,
        }

    def _score(self, issue_counts: dict) -> int:
        deductions = (
            issue_counts["error"] * 15
            + issue_counts["warning"] * 5
            + issue_counts["info"] * 2
        )
        return max(0, 100 - deductions)

    def _duplicate_message(self, field: str, url_count: int) -> str:
        label = {
            "title": "<title>",
            "meta_description": "meta description",
            "h1": "<h1>",
        }[field]
        return f"Duplicate {label} shared across {url_count} pages"

    def _normalize(self, value: str) -> str:
        return " ".join(value.lower().split())

    def _truncate(self, value: str, limit: int = 80) -> str:
        value = " ".join(value.split())
        if len(value) <= limit:
            return value
        return value[: limit - 1] + "..."

    def _issue(
        self,
        severity: str,
        field: str,
        code: str,
        message: str,
        **extra,
    ) -> dict:
        issue = {
            "severity": severity,
            "field": field,
            "code": code,
            "message": message,
            "scope": "page",
        }
        issue.update(extra)
        return issue
