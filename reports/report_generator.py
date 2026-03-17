"""
reports/report_generator.py
-----------------------------
Generates HTML and JSON reports from the collected audit data.
"""

import json
import os
from datetime import datetime
from jinja2 import Template

from config.settings import settings
from config.logging_config import logger

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AI Web Tester Report - {{ target_url }}</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1 { color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 8px; }
    h2 { color: #16213e; margin-top: 40px; }
    .meta { color: #666; font-size: 0.9rem; margin-bottom: 30px; }
    .card { background: #f8f9fa; border-left: 4px solid #e94560; padding: 16px 20px; margin: 12px 0; border-radius: 4px; }
    .card.warning { border-color: #f0a500; }
    .card.info    { border-color: #4ecca3; }
    .score-poor      { color: #e94560; font-weight: bold; }
    .score-fair      { color: #f0a500; font-weight: bold; }
    .score-good      { color: #4ecca3; font-weight: bold; }
    .score-excellent { color: #27ae60; font-weight: bold; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { background: #1a1a2e; color: #fff; padding: 10px; text-align: left; }
    td { padding: 10px; border-bottom: 1px solid #eee; }
    tr:hover td { background: #f1f1f1; }
    .ai-insight { background: #fff; border: 1px solid #ddd; padding: 16px; border-radius: 6px;
                  white-space: pre-wrap; font-size: 0.95rem; line-height: 1.6; }
  </style>
</head>
<body>
  <h1>🤖 AI Web Tester Report</h1>
  <p class="meta">Target: <strong>{{ target_url }}</strong> &nbsp;|&nbsp; Generated: {{ generated_at }}</p>

  <!-- PERFORMANCE -->
  <h2>📊 Performance</h2>
  <table>
    <tr><th>URL</th><th>Load Time (ms)</th><th>Score</th></tr>
    {% for r in performance %}
    <tr>
      <td>{{ r.url }}</td>
      <td>{{ r.load_time_ms }}</td>
      <td class="score-{{ r.score | lower }}">{{ r.score }}</td>
    </tr>
    {% endfor %}
  </table>

  <!-- BROKEN LINKS -->
  <h2>🔗 Broken Links</h2>
  {% if broken_links %}
  <table>
    <tr><th>Found On</th><th>Broken URL</th><th>Status</th></tr>
    {% for b in broken_links %}
    <tr><td>{{ b.source_url }}</td><td>{{ b.broken_url }}</td><td>{{ b.status_code }}</td></tr>
    {% endfor %}
  </table>
  {% else %}
  <div class="card info">✅ No broken links found.</div>
  {% endif %}

  <!-- SEO -->
  <h2>🔍 SEO Issues</h2>
  {% if seo %}
    {% for page in seo %}
    <h3>{{ page.url }}</h3>
    {% for issue in page.issues %}
    <div class="card {{ 'warning' if issue.severity == 'warning' else '' }}">
      <strong>[{{ issue.severity | upper }}]</strong> {{ issue.message }}
    </div>
    {% endfor %}
    {% endfor %}
  {% else %}
  <div class="card info">✅ No SEO issues found.</div>
  {% endif %}

  <!-- AI INSIGHTS -->
  <h2>🧠 AI Insights</h2>
  {% for item in ai_insights %}
  <h3>{{ item.url }}</h3>
  <div class="ai-insight">{{ item.insight }}</div>
  {% endfor %}

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
        }

        primary_path = ""
        fmt = settings.report_format

        if fmt in ("html", "both"):
            html_path = os.path.join(settings.report_output_dir, f"report_{timestamp}.html")
            html = Template(HTML_TEMPLATE).render(**data)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"HTML report saved: {html_path}")
            primary_path = html_path

        if fmt in ("json", "both"):
            json_path = os.path.join(settings.report_output_dir, f"report_{timestamp}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"JSON report saved: {json_path}")
            if not primary_path:
                primary_path = json_path

        return primary_path
