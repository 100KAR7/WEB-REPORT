"""
reports/report_context.py
-------------------------
Builds higher-level reporting context from raw crawl, test, SEO, and AI data.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


PERFORMANCE_PENALTIES = {
    "Excellent": 0,
    "Good": 4,
    "Fair": 12,
    "Poor": 25,
    "Not run": 0,
}

SEVERITY_WEIGHTS = {
    "error": 14,
    "warning": 5,
    "info": 2,
}

SEVERITY_ORDER = {
    "error": 0,
    "warning": 1,
    "info": 2,
}


def build_report_context(
    target_url: str,
    pages: list[Any],
    performance: list[dict],
    broken_links: list[dict],
    seo: list[dict],
    ai_insights: list[dict],
    sitewide_findings: list[dict] | None = None,
) -> dict:
    """
    Assemble user-facing report context from lower-level pipeline outputs.
    """
    sitewide_findings = sitewide_findings or []

    performance_by_url = {item["url"]: item for item in performance}
    seo_by_url = {item["url"]: item for item in seo}
    ai_urls = {item["url"] for item in ai_insights}
    broken_counts = _count_broken_links_by_page(broken_links)

    page_health = [
        _build_page_health_entry(
            page=page,
            performance=performance_by_url.get(page.url),
            seo_entry=seo_by_url.get(page.url),
            broken_links_count=broken_counts.get(page.url, 0),
            has_ai_insight=page.url in ai_urls,
        )
        for page in pages
    ]
    page_health.sort(
        key=lambda item: (
            item["health_score"],
            -item["critical_issue_count"],
            -item["broken_links_count"],
            item["url"],
        )
    )

    seo_summary = _build_seo_summary(seo, sitewide_findings)
    summary = _build_summary(
        target_url=target_url,
        pages=pages,
        page_health=page_health,
        broken_links=broken_links,
        ai_insights=ai_insights,
        sitewide_findings=sitewide_findings,
        seo_summary=seo_summary,
    )
    recommendations = _build_recommendations(summary, seo_summary, sitewide_findings)

    return {
        "summary": summary,
        "seo_summary": seo_summary,
        "page_health": page_health,
        "sitewide_findings": _decorate_sitewide_findings(sitewide_findings),
        "recommendations": recommendations,
    }


def _count_broken_links_by_page(broken_links: list[dict]) -> Counter:
    counts: Counter = Counter()
    for item in broken_links:
        sources = item.get("source_urls") or []
        if not sources and item.get("source_url"):
            sources = [item["source_url"]]
        for source in set(sources):
            counts[source] += 1
    return counts


def _build_page_health_entry(
    page: Any,
    performance: dict | None,
    seo_entry: dict | None,
    broken_links_count: int,
    has_ai_insight: bool,
) -> dict:
    seo_entry = seo_entry or {
        "score": 0,
        "issue_counts": {"error": 0, "warning": 0, "info": 0, "total": 0},
        "issues": [],
    }
    issue_counts = seo_entry.get("issue_counts") or {}
    issues = seo_entry.get("issues") or []
    load_time_ms = (
        performance.get("load_time_ms", page.load_time_ms)
        if performance else page.load_time_ms
    )
    performance_label = performance.get("score", "Not run") if performance else "Not run"
    performance_value = performance.get("score_value", 0) if performance else 0

    top_issues = []
    if getattr(page, "error", None):
        top_issues.append(page.error)

    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            SEVERITY_ORDER.get(issue.get("severity", "info"), 99),
            issue.get("scope") == "sitewide",
            issue.get("message", ""),
        ),
    )
    for issue in sorted_issues[:3]:
        top_issues.append(issue.get("message", ""))

    health_score = 100
    if getattr(page, "error", None):
        health_score -= 35
    elif getattr(page, "status_code", 0) >= 400:
        health_score -= 25

    health_score -= PERFORMANCE_PENALTIES.get(performance_label, 0)
    health_score -= min(24, broken_links_count * 8)
    for severity, weight in SEVERITY_WEIGHTS.items():
        health_score -= issue_counts.get(severity, 0) * weight
    health_score = max(0, min(100, health_score))

    status = _health_status(health_score)
    return {
        "url": page.url,
        "title": page.title or page.url,
        "status_code": page.status_code,
        "load_time_ms": round(load_time_ms, 2),
        "performance_label": performance_label,
        "performance_score_value": performance_value,
        "health_score": round(health_score),
        "health_status": status,
        "health_class": _health_class(status),
        "seo_score": seo_entry.get("score", 0),
        "seo_issue_count": issue_counts.get("total", 0),
        "critical_issue_count": issue_counts.get("error", 0) + broken_links_count + int(bool(page.error)),
        "broken_links_count": broken_links_count,
        "has_ai_insight": has_ai_insight,
        "top_issues": [issue for issue in top_issues if issue],
    }


def _build_summary(
    target_url: str,
    pages: list[Any],
    page_health: list[dict],
    broken_links: list[dict],
    ai_insights: list[dict],
    sitewide_findings: list[dict],
    seo_summary: dict,
) -> dict:
    total_pages = len(pages)
    duplicate_urls = {
        url
        for finding in sitewide_findings
        for url in finding.get("urls", [])
    }
    average_load = round(
        sum(item["load_time_ms"] for item in page_health) / max(total_pages, 1),
        1,
    )
    overall_score = round(
        sum(item["health_score"] for item in page_health) / max(total_pages, 1),
        1,
    )
    slow_pages = sum(1 for item in page_health if item["load_time_ms"] >= 2000)

    summary = {
        "target_url": target_url,
        "overall_score": overall_score,
        "overall_rating": _health_status(overall_score),
        "overall_rating_class": _health_class(_health_status(overall_score)),
        "total_pages": total_pages,
        "successful_pages": sum(1 for page in pages if page.is_ok),
        "failed_pages": sum(1 for page in pages if not page.is_ok),
        "average_load_time_ms": average_load,
        "slow_pages": slow_pages,
        "broken_links": len(broken_links),
        "broken_link_occurrences": sum(_broken_link_occurrences(item) for item in broken_links),
        "pages_with_broken_links": sum(1 for item in page_health if item["broken_links_count"] > 0),
        "total_seo_issues": seo_summary["total_issues"],
        "critical_seo_issues": seo_summary["errors"],
        "duplicate_groups": len(sitewide_findings),
        "pages_with_duplicates": len(duplicate_urls),
        "ai_insight_pages": len(ai_insights),
        "healthy_pages": sum(1 for item in page_health if item["health_status"] == "Healthy"),
        "watch_pages": sum(1 for item in page_health if item["health_status"] == "Watch"),
        "critical_pages": sum(1 for item in page_health if item["health_status"] == "Critical"),
    }
    return summary


def _build_seo_summary(seo: list[dict], sitewide_findings: list[dict]) -> dict:
    issue_codes = Counter()
    field_counts = Counter()
    errors = warnings = info = 0
    pages_with_issues = 0

    for entry in seo:
        issues = entry.get("issues") or []
        if issues:
            pages_with_issues += 1
        for issue in issues:
            issue_codes[issue.get("code", "unknown")] += 1
            field_counts[issue.get("field", "other")] += 1
            severity = issue.get("severity")
            if severity == "error":
                errors += 1
            elif severity == "warning":
                warnings += 1
            else:
                info += 1

    duplicate_group_counts = Counter(finding.get("field", "other") for finding in sitewide_findings)
    duplicate_page_counts = Counter()
    for finding in sitewide_findings:
        duplicate_page_counts[finding.get("field", "other")] += len(finding.get("urls", []))

    return {
        "pages_with_issues": pages_with_issues,
        "total_issues": errors + warnings + info,
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "pages_missing_title": issue_codes["missing_title"],
        "pages_missing_meta_description": issue_codes["missing_meta_description"],
        "pages_missing_h1": issue_codes["missing_h1"],
        "pages_missing_alt_text": issue_codes["missing_image_alt_text"],
        "duplicate_title_groups": duplicate_group_counts["title"],
        "duplicate_meta_description_groups": duplicate_group_counts["meta_description"],
        "duplicate_h1_groups": duplicate_group_counts["h1"],
        "pages_with_duplicate_titles": duplicate_page_counts["title"],
        "pages_with_duplicate_meta_descriptions": duplicate_page_counts["meta_description"],
        "pages_with_duplicate_h1s": duplicate_page_counts["h1"],
        "top_issue_fields": [
            {"field": field, "count": count}
            for field, count in field_counts.most_common(5)
        ],
    }


def _build_recommendations(
    summary: dict,
    seo_summary: dict,
    sitewide_findings: list[dict],
) -> list[dict]:
    recommendations = []

    if summary["broken_links"] > 0:
        recommendations.append({
            "priority": "High",
            "priority_class": "high",
            "title": "Repair broken links",
            "message": (
                f"{summary['broken_links']} broken URL(s) were found across "
                f"{summary['pages_with_broken_links']} page(s). Fixing these links will "
                "remove dead ends for visitors and search crawlers."
            ),
        })

    if summary["critical_seo_issues"] > 0 or seo_summary["pages_missing_title"] > 0:
        recommendations.append({
            "priority": "High",
            "priority_class": "high",
            "title": "Resolve missing core SEO tags",
            "message": (
                f"{summary['critical_seo_issues']} critical SEO issue(s) remain, including "
                f"{seo_summary['pages_missing_title']} page(s) without titles and "
                f"{seo_summary['pages_missing_meta_description']} without meta descriptions."
            ),
        })

    if sitewide_findings:
        duplicate_fields = sorted({finding["field"].replace("_", " ") for finding in sitewide_findings})
        recommendations.append({
            "priority": "Medium",
            "priority_class": "medium",
            "title": "Consolidate duplicate metadata",
            "message": (
                f"{summary['duplicate_groups']} duplicate metadata group(s) were found across "
                f"{summary['pages_with_duplicates']} page(s), including {', '.join(duplicate_fields)}."
            ),
        })

    if summary["slow_pages"] > 0:
        recommendations.append({
            "priority": "Medium",
            "priority_class": "medium",
            "title": "Improve slower pages",
            "message": (
                f"{summary['slow_pages']} page(s) took at least 2000ms to respond during the crawl. "
                "Review image weight, third-party scripts, and server response time."
            ),
        })

    if seo_summary["pages_missing_alt_text"] > 0:
        recommendations.append({
            "priority": "Low",
            "priority_class": "low",
            "title": "Fill in missing image alt text",
            "message": (
                f"{seo_summary['pages_missing_alt_text']} page(s) contain images without alt text, "
                "which weakens accessibility and image SEO."
            ),
        })

    if not recommendations:
        recommendations.append({
            "priority": "Low",
            "priority_class": "low",
            "title": "Maintain the current baseline",
            "message": "No major gaps stood out in the crawl. Keep monitoring performance and metadata consistency.",
        })

    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    recommendations.sort(key=lambda item: priority_order[item["priority"]])
    return recommendations[:4]


def _decorate_sitewide_findings(sitewide_findings: list[dict]) -> list[dict]:
    decorated = []
    for finding in sitewide_findings:
        severity = finding.get("severity", "warning")
        decorated.append({
            **finding,
            "severity_class": severity.lower(),
        })
    return decorated


def _broken_link_occurrences(item: dict) -> int:
    sources = item.get("source_urls") or []
    if sources:
        return len(sources)
    return 1 if item.get("source_url") else 0


def _health_status(score: float) -> str:
    if score >= 85:
        return "Healthy"
    if score >= 65:
        return "Watch"
    return "Critical"


def _health_class(status: str) -> str:
    if status == "Healthy":
        return "healthy"
    if status == "Watch":
        return "watch"
    return "critical"
