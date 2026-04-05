"""
reports/report_generator.py
---------------------------
Generates HTML and JSON reports from collected audit data.
"""

import json
import os
from datetime import datetime

from jinja2 import Environment

from config.settings import settings
from config.logging_config import logger

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Web Tester Report - {{ target_url }}</title>
  <style>
    :root {
      --bg: #f3efe5;
      --bg-accent: #e4dccb;
      --surface: rgba(255, 255, 255, 0.86);
      --surface-strong: #fffdfa;
      --ink: #1e2930;
      --muted: #617079;
      --line: #d8cfbc;
      --accent: #b55e24;
      --accent-soft: #f0d8be;
      --good: #24704c;
      --watch: #a66300;
      --critical: #a03c2f;
      --high: #8f2d23;
      --medium: #9f6200;
      --low: #356a82;
      --shadow: 0 18px 40px rgba(50, 44, 31, 0.12);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(181, 94, 36, 0.18), transparent 30%),
        radial-gradient(circle at top right, rgba(53, 106, 130, 0.12), transparent 24%),
        linear-gradient(180deg, var(--bg), var(--bg-accent));
      line-height: 1.55;
    }

    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 18px 44px;
    }

    .hero {
      background: linear-gradient(135deg, rgba(255, 253, 250, 0.96), rgba(246, 238, 223, 0.96));
      border: 1px solid rgba(181, 94, 36, 0.16);
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-columns: 1.4fr 0.8fr;
      gap: 20px;
      margin-bottom: 22px;
    }

    .eyebrow {
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted);
      font-size: 0.78rem;
      margin-bottom: 10px;
    }

    h1, h2, h3 {
      font-family: Georgia, "Times New Roman", serif;
      margin: 0 0 10px;
    }

    h1 {
      font-size: clamp(2rem, 4vw, 3.2rem);
      line-height: 1.05;
    }

    h2 {
      font-size: 1.55rem;
      margin-bottom: 16px;
    }

    h3 {
      font-size: 1.1rem;
    }

    .hero p {
      color: var(--muted);
      margin: 0;
      max-width: 66ch;
    }

    .score-panel {
      background: rgba(30, 41, 48, 0.96);
      color: #fff;
      border-radius: 24px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 210px;
    }

    .score-panel .label {
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-size: 0.72rem;
      opacity: 0.72;
    }

    .score-value {
      font-size: 4rem;
      line-height: 0.95;
      font-weight: 700;
      margin: 14px 0 8px;
    }

    .rating {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 14px;
      font-weight: 700;
      width: fit-content;
      background: rgba(255, 255, 255, 0.12);
    }

    .rating.healthy { color: #94e1b6; }
    .rating.watch { color: #ffd585; }
    .rating.critical { color: #ffaf9f; }

    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 22px;
    }

    .card {
      background: var(--surface);
      border: 1px solid rgba(30, 41, 48, 0.08);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(6px);
    }

    .metric-label {
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 10px;
    }

    .metric-value {
      font-size: 2rem;
      font-weight: 700;
      margin-bottom: 4px;
    }

    .metric-note {
      color: var(--muted);
      font-size: 0.92rem;
    }

    .section {
      margin-top: 22px;
    }

    .section-header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }

    .section-header p {
      margin: 0;
      color: var(--muted);
    }

    .recommendations {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }

    .recommendation {
      border-radius: 18px;
      padding: 18px;
      color: #fff;
      box-shadow: var(--shadow);
    }

    .recommendation.high { background: linear-gradient(140deg, #8f2d23, #c45945); }
    .recommendation.medium { background: linear-gradient(140deg, #8b5b00, #c28c18); }
    .recommendation.low { background: linear-gradient(140deg, #24536a, #3e7b98); }

    .recommendation .priority {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      opacity: 0.78;
      margin-bottom: 10px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 0.82rem;
      font-weight: 700;
      background: var(--accent-soft);
      color: var(--accent);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--surface-strong);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }

    th, td {
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }

    th {
      font-size: 0.82rem;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      background: rgba(30, 41, 48, 0.92);
      color: #fff;
    }

    tr:last-child td { border-bottom: 0; }
    tr.healthy td:first-child { border-left: 5px solid rgba(36, 112, 76, 0.55); }
    tr.watch td:first-child { border-left: 5px solid rgba(166, 99, 0, 0.55); }
    tr.critical td:first-child { border-left: 5px solid rgba(160, 60, 47, 0.55); }

    .health-badge,
    .perf-badge,
    .seo-badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: 0.82rem;
      font-weight: 700;
      white-space: nowrap;
    }

    .health-badge.healthy { background: rgba(36, 112, 76, 0.12); color: var(--good); }
    .health-badge.watch { background: rgba(166, 99, 0, 0.12); color: var(--watch); }
    .health-badge.critical { background: rgba(160, 60, 47, 0.12); color: var(--critical); }
    .perf-badge { background: rgba(53, 106, 130, 0.12); color: var(--low); }
    .seo-badge { background: rgba(181, 94, 36, 0.12); color: var(--accent); }

    .mini-list,
    .sources {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }

    .mini-list li,
    .sources li {
      margin-bottom: 6px;
    }

    .finding-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }

    .finding {
      background: var(--surface);
      border: 1px solid rgba(30, 41, 48, 0.08);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
    }

    .finding.warning { border-top: 6px solid rgba(166, 99, 0, 0.72); }

    .finding strong {
      display: block;
      margin-bottom: 8px;
    }

    .finding .meta {
      color: var(--muted);
      font-size: 0.92rem;
      margin-top: 8px;
    }

    .issue-groups {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }

    .issue-card {
      background: var(--surface);
      border-radius: 20px;
      padding: 18px;
      box-shadow: var(--shadow);
      border: 1px solid rgba(30, 41, 48, 0.08);
    }

    .issue-card ul {
      margin: 12px 0 0;
      padding-left: 18px;
    }

    .issue-card li {
      margin-bottom: 8px;
      color: var(--muted);
    }

    .empty {
      background: var(--surface);
      border-radius: 18px;
      padding: 18px;
      color: var(--muted);
      box-shadow: var(--shadow);
      border: 1px solid rgba(30, 41, 48, 0.08);
    }

    .footer {
      margin-top: 28px;
      color: var(--muted);
      text-align: center;
      font-size: 0.9rem;
    }

    @media (max-width: 900px) {
      .hero,
      .grid {
        grid-template-columns: 1fr;
      }

      .shell {
        padding: 18px 12px 36px;
      }

      table, thead, tbody, th, td, tr {
        display: block;
      }

      thead {
        display: none;
      }

      tr {
        margin-bottom: 12px;
        border-radius: 18px;
        overflow: hidden;
        box-shadow: var(--shadow);
      }

      td {
        background: var(--surface-strong);
      }

      td::before {
        content: attr(data-label);
        display: block;
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        margin-bottom: 6px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">AI Website Audit</div>
        <h1>Site health report for {{ target_url }}</h1>
        <p>
          Generated on {{ generated_at }}. This report combines crawl coverage,
          performance checks, broken-link validation, SEO findings, and AI insights
          into one audit-ready snapshot.
        </p>
      </div>
      <div class="score-panel">
        <div>
          <div class="label">Overall health score</div>
          <div class="score-value">{{ summary.overall_score }}</div>
        </div>
        <div class="rating {{ summary.overall_rating_class }}">{{ summary.overall_rating }}</div>
      </div>
    </section>

    <section class="grid">
      <div class="card">
        <div class="metric-label">Pages crawled</div>
        <div class="metric-value">{{ summary.total_pages }}</div>
        <div class="metric-note">{{ summary.successful_pages }} successful, {{ summary.failed_pages }} failed</div>
      </div>
      <div class="card">
        <div class="metric-label">Average load time</div>
        <div class="metric-value">{{ summary.average_load_time_ms }}ms</div>
        <div class="metric-note">{{ summary.slow_pages }} page(s) crossed 2000ms</div>
      </div>
      <div class="card">
        <div class="metric-label">Broken links</div>
        <div class="metric-value">{{ summary.broken_links }}</div>
        <div class="metric-note">{{ summary.broken_link_occurrences }} total page occurrence(s)</div>
      </div>
      <div class="card">
        <div class="metric-label">SEO issues</div>
        <div class="metric-value">{{ summary.total_seo_issues }}</div>
        <div class="metric-note">{{ summary.critical_seo_issues }} critical, {{ summary.duplicate_groups }} duplicate group(s)</div>
      </div>
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>Recommended next moves</h2>
          <p>Prioritized actions based on the strongest signals from the crawl.</p>
        </div>
        <span class="pill">{{ recommendations|length }} recommendation(s)</span>
      </div>
      <div class="recommendations">
        {% for item in recommendations %}
        <article class="recommendation {{ item.priority_class }}">
          <div class="priority">{{ item.priority }} priority</div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.message }}</p>
        </article>
        {% endfor %}
      </div>
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>Page health ranking</h2>
          <p>The lowest-scoring pages appear first so triage can start with the highest-risk areas.</p>
        </div>
        <span class="pill">{{ summary.healthy_pages }} healthy / {{ summary.watch_pages }} watch / {{ summary.critical_pages }} critical</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Page</th>
            <th>Health</th>
            <th>Load</th>
            <th>Broken links</th>
            <th>SEO</th>
            <th>Top issues</th>
          </tr>
        </thead>
        <tbody>
          {% for item in page_health %}
          <tr class="{{ item.health_class }}">
            <td data-label="Page">
              <strong>{{ item.title }}</strong><br>
              <span class="metric-note">{{ item.url }}</span>
            </td>
            <td data-label="Health">
              <span class="health-badge {{ item.health_class }}">{{ item.health_score }} · {{ item.health_status }}</span>
            </td>
            <td data-label="Load">
              {{ item.load_time_ms }}ms<br>
              <span class="perf-badge">{{ item.performance_label }}</span>
            </td>
            <td data-label="Broken links">{{ item.broken_links_count }}</td>
            <td data-label="SEO">
              <span class="seo-badge">{{ item.seo_score }}/100</span><br>
              <span class="metric-note">{{ item.seo_issue_count }} issue(s)</span>
            </td>
            <td data-label="Top issues">
              {% if item.top_issues %}
              <ul class="mini-list">
                {% for issue in item.top_issues %}
                <li>{{ issue }}</li>
                {% endfor %}
              </ul>
              {% else %}
              <span class="metric-note">No standout issues.</span>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>Sitewide duplicate signals</h2>
          <p>Duplicate titles, meta descriptions, and H1s often dilute relevance and cause confusing search snippets.</p>
        </div>
        <span class="pill">{{ sitewide_findings|length }} duplicate group(s)</span>
      </div>
      {% if sitewide_findings %}
      <div class="finding-list">
        {% for finding in sitewide_findings %}
        <article class="finding {{ finding.severity_class }}">
          <strong>{{ finding.message }}</strong>
          <div>{{ finding.value }}</div>
          <div class="meta">{{ finding.url_count }} page(s) share this {{ finding.field.replace('_', ' ') }}</div>
          <ul class="sources">
            {% for url in finding.urls %}
            <li>{{ url }}</li>
            {% endfor %}
          </ul>
        </article>
        {% endfor %}
      </div>
      {% else %}
      <div class="empty">No duplicate title, meta description, or H1 groups were detected in this crawl.</div>
      {% endif %}
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>Broken link details</h2>
          <p>Each broken destination includes the page(s) where it was referenced.</p>
        </div>
        <span class="pill">{{ broken_links|length }} broken URL(s)</span>
      </div>
      {% if broken_links %}
      <table>
        <thead>
          <tr>
            <th>Broken URL</th>
            <th>Status</th>
            <th>Occurrences</th>
            <th>Found on</th>
          </tr>
        </thead>
        <tbody>
          {% for item in broken_links %}
          <tr>
            <td data-label="Broken URL">{{ item.broken_url }}</td>
            <td data-label="Status">{{ item.status_code }}</td>
            <td data-label="Occurrences">{{ item.occurrences }}</td>
            <td data-label="Found on">
              <ul class="sources">
                {% for source in item.source_urls %}
                <li>{{ source }}</li>
                {% endfor %}
              </ul>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty">No broken links were found in the crawled pages.</div>
      {% endif %}
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>SEO issue groups</h2>
          <p>Page-level SEO findings are grouped so repeated patterns are easier to spot.</p>
        </div>
        <span class="pill">{{ seo|length }} page(s) analyzed</span>
      </div>
      {% if seo %}
      <div class="issue-groups">
        {% for page in seo %}
        <article class="issue-card">
          <h3>{{ page.title or page.url }}</h3>
          <div class="metric-note">{{ page.url }}</div>
          <p><span class="seo-badge">{{ page.score }}/100</span> {{ page.issue_counts.error }} error(s), {{ page.issue_counts.warning }} warning(s), {{ page.issue_counts.info }} info</p>
          {% if page.issues %}
          <ul>
            {% for issue in page.issues %}
            <li><strong>[{{ issue.severity|upper }}]</strong> {{ issue.message }}</li>
            {% endfor %}
          </ul>
          {% else %}
          <p class="metric-note">No page-level SEO issues detected.</p>
          {% endif %}
        </article>
        {% endfor %}
      </div>
      {% else %}
      <div class="empty">SEO analysis was skipped for this run.</div>
      {% endif %}
    </section>

    <section class="section">
      <div class="section-header">
        <div>
          <h2>AI insights</h2>
          <p>Generated only for pages that were successfully crawled and analyzed with the configured AI provider.</p>
        </div>
        <span class="pill">{{ ai_insights|length }} page(s)</span>
      </div>
      {% if ai_insights %}
      <div class="issue-groups">
        {% for item in ai_insights %}
        <article class="issue-card">
          <h3>{{ item.url }}</h3>
          <p>{{ item.insight }}</p>
        </article>
        {% endfor %}
      </div>
      {% else %}
      <div class="empty">No AI insights were generated for this run.</div>
      {% endif %}
    </section>

    <div class="footer">AI Web Tester report generated for {{ target_url }}</div>
  </div>
</body>
</html>
"""


class ReportGenerator:
    """Renders audit results into HTML and/or JSON reports."""

    def generate(
        self,
        target_url: str,
        performance: list[dict],
        broken_links: list[dict],
        seo: list[dict],
        ai_insights: list[dict],
        summary: dict | None = None,
        seo_summary: dict | None = None,
        page_health: list[dict] | None = None,
        sitewide_findings: list[dict] | None = None,
        recommendations: list[dict] | None = None,
    ) -> str:
        """Writes report file(s) and returns path to the primary report."""
        os.makedirs(settings.report_output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "target_url": target_url,
            "generated_at": generated_at,
            "performance": performance,
            "broken_links": broken_links,
            "seo": seo,
            "ai_insights": ai_insights,
            "summary": summary or {},
            "seo_summary": seo_summary or {},
            "page_health": page_health or [],
            "sitewide_findings": sitewide_findings or [],
            "recommendations": recommendations or [],
        }

        primary_path = ""
        fmt = settings.report_format

        if fmt in ("html", "both"):
            html_path = os.path.join(settings.report_output_dir, f"report_{timestamp}.html")
            html = Environment(autoescape=True).from_string(HTML_TEMPLATE).render(**data)
            with open(html_path, "w", encoding="utf-8") as file_handle:
                file_handle.write(html)
            logger.info(f"HTML report saved: {html_path}")
            primary_path = html_path

        if fmt in ("json", "both"):
            json_path = os.path.join(settings.report_output_dir, f"report_{timestamp}.json")
            with open(json_path, "w", encoding="utf-8") as file_handle:
                json.dump(data, file_handle, indent=2)
            logger.info(f"JSON report saved: {json_path}")
            if not primary_path:
                primary_path = json_path

        return primary_path
