"""
pipeline/automated_runner.py
-----------------------------
Production-grade automated runner for the AI Web Tester.

Adds on top of run_pipeline.py:
  • Structured file logging  (logs/runner_YYYY-MM-DD.log)
  • Per-site error isolation  (one site failing never kills the rest)
  • Multi-site support        (YAML config or CLI --sites flag)
  • Retry logic               (configurable attempts per site)
  • Run summary email hook    (optional — set SMTP env vars)
  • Exit codes for CI/CD      (0 = all passed, 1 = partial, 2 = all failed)
  • Cron-ready                (idempotent, lockfile prevents overlapping runs)

Typical cron setup (see bottom of this file for full examples):
  # Run every day at 2 AM
  0 2 * * * /usr/bin/python3 /path/to/pipeline/automated_runner.py --config sites.yaml

Usage:
  # Single site
  python pipeline/automated_runner.py --url https://example.com

  # Multiple sites via CLI
  python pipeline/automated_runner.py --urls https://example.com https://another.com

  # Multiple sites via YAML config file
  python pipeline/automated_runner.py --config pipeline/sites.yaml

  # Dry run (crawl only, no UI/SEO)
  python pipeline/automated_runner.py --config pipeline/sites.yaml --dry-run

File layout created on first run:
  logs/
    runner_2024-03-15.log     ← one log file per day
  output/
    example_com/
      report_20240315_020000.json
      report_20240315_020000.txt
    another_com/
      report_20240315_021532.json
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import smtplib
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

# ── Project root on sys.path ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Optional YAML support (falls back to JSON if PyYAML not installed) ─────
try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging setup — writes to both console and a rotating daily log file
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Configure logging to write to:
      • stdout        — human-readable, coloured (if rich is available)
      • logs/YYYY-MM-DD.log — plain text, one file per day

    Returns the root logger for this tool.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"runner_{datetime.now().strftime('%Y-%m-%d')}.log"

    fmt      = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger("ai_web_tester")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # ── File handler (always plain text) ─────────────────────────────────
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    logger.addHandler(fh)

    # ── Console handler (rich if available, else plain) ───────────────────
    try:
        from rich.logging import RichHandler
        ch = RichHandler(rich_tracebacks=True, show_path=False)
    except ImportError:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

    logger.addHandler(ch)
    logger.info(f"Logging to: {log_file}")
    return logger


# ---------------------------------------------------------------------------
# Site configuration
# ---------------------------------------------------------------------------

@dataclass
class SiteConfig:
    """Configuration for one website to test."""
    url:        str
    max_pages:  int   = 10
    run_ui:     bool  = True
    run_seo:    bool  = True
    retries:    int   = 2          # how many times to retry on failure
    label:      str   = ""         # friendly name (auto-derived if empty)
    enabled:    bool  = True       # set False to skip without deleting

    def __post_init__(self):
        if not self.label:
            from urllib.parse import urlparse
            self.label = urlparse(self.url).netloc or self.url


@dataclass
class RunnerConfig:
    """Top-level runner configuration."""
    sites:        list[SiteConfig] = field(default_factory=list)
    output_dir:   str  = "output"
    log_dir:      str  = "logs"
    log_level:    str  = "INFO"
    headless:     bool = True
    dry_run:      bool = False     # crawl only, skip UI/SEO
    notify_email: str  = ""        # send summary to this address when done
    lock_file:    str  = "/tmp/ai_web_tester.lock"


# ---------------------------------------------------------------------------
# Per-site run result
# ---------------------------------------------------------------------------

@dataclass
class SiteRunResult:
    """Outcome of running the full pipeline against one site."""
    site:         SiteConfig
    success:      bool           = False
    pages_found:  int            = 0
    report_paths: dict           = field(default_factory=dict)  # {json, txt}
    error:        Optional[str]  = None
    duration_s:   float          = 0.0
    attempts:     int            = 0
    started_at:   str            = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )

    def to_dict(self) -> dict:
        return {
            "url":          self.site.url,
            "label":        self.site.label,
            "success":      self.success,
            "pages_found":  self.pages_found,
            "report_paths": self.report_paths,
            "error":        self.error,
            "duration_s":   round(self.duration_s, 2),
            "attempts":     self.attempts,
            "started_at":   self.started_at,
        }


# ---------------------------------------------------------------------------
# Automated multi-site runner
# ---------------------------------------------------------------------------

class AutomatedRunner:
    """
    Runs the full pipeline against one or more sites with:
      - structured logging
      - per-site error isolation
      - retry logic
      - optional email notification
      - lockfile to prevent overlapping cron runs
    """

    def __init__(self, config: RunnerConfig):
        self.config = config
        self.logger = setup_logging(config.log_dir, config.log_level)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_all(self) -> list[SiteRunResult]:
        """
        Run the pipeline for every enabled site in config.sites.

        Returns:
            list[SiteRunResult] — one entry per site (including failed ones)

        Exit codes (set on sys.exit at the end of __main__):
            0 — all sites passed
            1 — some sites failed
            2 — all sites failed
        """
        sites = [s for s in self.config.sites if s.enabled]

        if not sites:
            self.logger.warning("No enabled sites found in config. Exiting.")
            return []

        self.logger.info(f"{'═'*60}")
        self.logger.info(f"AI Web Tester — Automated Run")
        self.logger.info(f"Sites to test : {len(sites)}")
        self.logger.info(f"Dry run       : {self.config.dry_run}")
        self.logger.info(f"{'═'*60}")

        with _Lockfile(self.config.lock_file, self.logger):
            run_started = time.perf_counter()
            results: list[SiteRunResult] = []

            for idx, site in enumerate(sites, 1):
                self.logger.info(f"[{idx}/{len(sites)}] Starting: {site.url}")
                result = self._run_with_retry(site)
                results.append(result)
                _log_site_result(result, self.logger)

            total_s = time.perf_counter() - run_started
            self._log_run_summary(results, total_s)
            self._save_run_manifest(results, total_s)

            if self.config.notify_email:
                self._send_email_summary(results, total_s)

        return results

    def run_single(self, site: SiteConfig) -> SiteRunResult:
        """Run one site (used directly from tests or other scripts)."""
        with _Lockfile(self.config.lock_file, self.logger):
            return self._run_with_retry(site)

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _run_with_retry(self, site: SiteConfig) -> SiteRunResult:
        """
        Attempt to run the pipeline for *site*, retrying up to site.retries
        times on failure.  Each attempt is fully isolated — a crash on
        attempt 1 will not affect attempt 2.
        """
        result = SiteRunResult(site=site)
        max_attempts = max(1, site.retries)

        for attempt in range(1, max_attempts + 1):
            result.attempts = attempt
            if attempt > 1:
                wait = 2 ** attempt   # exponential back-off: 4s, 8s, …
                self.logger.warning(
                    f"  Retry {attempt}/{max_attempts} for {site.url} "
                    f"(waiting {wait}s)"
                )
                time.sleep(wait)

            try:
                t0 = time.perf_counter()
                self._run_site(site, result)
                result.duration_s = time.perf_counter() - t0
                result.success    = True
                return result                  # ← success, stop retrying

            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
                self.logger.error(
                    f"  Attempt {attempt} failed for {site.url}: {exc}",
                    exc_info=True,
                )

        result.duration_s = time.perf_counter() - (
            time.perf_counter()               # approximate if all failed
        )
        return result   # all attempts exhausted

    # ------------------------------------------------------------------
    # Core pipeline call
    # ------------------------------------------------------------------

    def _run_site(self, site: SiteConfig, result: SiteRunResult) -> None:
        """
        Execute the full pipeline for one site and populate *result*.
        Any unhandled exception propagates up to _run_with_retry.
        """
        from pipeline.run_pipeline import Pipeline
        from reports.generate_report import ReportBuilder

        # Per-site output directory:  output/example_com/
        site_slug  = _url_to_slug(site.url)
        site_outdir = os.path.join(self.config.output_dir, site_slug)
        os.makedirs(site_outdir, exist_ok=True)

        self.logger.info(f"  Crawling: {site.url} (max {site.max_pages} pages)")

        # ── Run the pipeline ──────────────────────────────────────────────
        pipeline = Pipeline(
            url            = site.url,
            max_pages      = site.max_pages,
            run_ui         = site.run_ui  and not self.config.dry_run,
            run_seo        = site.run_seo and not self.config.dry_run,
            screenshot_dir = os.path.join(site_outdir, "screenshots"),
            headless       = self.config.headless,
        )
        page_results   = pipeline.run()
        result.pages_found = len(page_results)
        self.logger.info(f"  Pages found: {result.pages_found}")

        if self.config.dry_run:
            self.logger.info("  Dry run — skipping report generation.")
            return

        # ── Generate reports ──────────────────────────────────────────────
        self.logger.info(f"  Generating reports → {site_outdir}")
        builder = ReportBuilder(site_url=site.url, output_dir=site_outdir)
        builder.add_pages(page_results)
        paths = builder.save()
        result.report_paths = paths
        self.logger.info(f"  Reports saved: {list(paths.values())}")

    # ------------------------------------------------------------------
    # Summary + manifest
    # ------------------------------------------------------------------

    def _log_run_summary(self, results: list[SiteRunResult], total_s: float) -> None:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        self.logger.info(f"{'═'*60}")
        self.logger.info(f"RUN COMPLETE — {passed} passed / {failed} failed "
                         f"in {total_s:.1f}s")
        for r in results:
            status = "✓ PASS" if r.success else "✗ FAIL"
            self.logger.info(
                f"  {status}  {r.site.url}  "
                f"({r.pages_found} pages, {r.duration_s:.1f}s, "
                f"{r.attempts} attempt(s))"
            )
        self.logger.info(f"{'═'*60}")

    def _save_run_manifest(self, results: list[SiteRunResult], total_s: float) -> None:
        """
        Save a machine-readable manifest of the entire run.
        Useful for dashboards, CI checks, and audit trails.
        """
        os.makedirs(self.config.output_dir, exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest = {
            "run_at":      datetime.now().isoformat(timespec="seconds"),
            "total_s":     round(total_s, 2),
            "dry_run":     self.config.dry_run,
            "sites_total": len(results),
            "sites_passed":sum(1 for r in results if r.success),
            "sites_failed":sum(1 for r in results if not r.success),
            "sites":       [r.to_dict() for r in results],
        }
        path = os.path.join(self.config.output_dir, f"manifest_{ts}.json")
        with open(path, "w") as f:
            json.dump(manifest, f, indent=2)
        self.logger.info(f"Run manifest → {path}")

    # ------------------------------------------------------------------
    # Email notification (optional)
    # ------------------------------------------------------------------

    def _send_email_summary(
        self, results: list[SiteRunResult], total_s: float
    ) -> None:
        """
        Send a plain-text run summary to config.notify_email.

        Requires these environment variables:
            SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
        """
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASS", "")
        smtp_from = os.getenv("SMTP_FROM", smtp_user)

        if not smtp_host:
            self.logger.warning("SMTP_HOST not set — skipping email notification.")
            return

        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        subject = (
            f"[AI Web Tester] {'✓ All passed' if failed == 0 else f'⚠ {failed} site(s) failed'}"
            f" — {datetime.now().strftime('%Y-%m-%d')}"
        )

        lines = [
            f"AI Web Tester — Automated Run Summary",
            f"{'─'*50}",
            f"Date      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration  : {total_s:.1f}s",
            f"Passed    : {passed} / {len(results)}",
            f"Failed    : {failed}",
            "",
        ]
        for r in results:
            status = "PASS" if r.success else "FAIL"
            lines.append(f"  [{status}] {r.site.url}")
            if r.error:
                lines.append(f"         Error: {r.error}")
            if r.report_paths:
                lines.append(f"         Report: {r.report_paths.get('txt', '')}")
        body = "\n".join(lines)

        try:
            msg = MIMEMultipart()
            msg["From"]    = smtp_from
            msg["To"]      = self.config.notify_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            self.logger.info(f"Email summary sent to {self.config.notify_email}")
        except Exception as exc:
            self.logger.error(f"Failed to send email: {exc}")


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_config_from_yaml(path: str) -> RunnerConfig:
    """
    Load RunnerConfig from a YAML file.

    Example sites.yaml:
        output_dir: output
        log_dir: logs
        log_level: INFO
        headless: true
        notify_email: ""

        sites:
          - url: https://example.com
            max_pages: 20
            retries: 2
            label: "Example Site"

          - url: https://another.com
            max_pages: 10
            run_ui: false      # SEO only
            enabled: true
    """
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML not installed. Run: pip install pyyaml")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    sites = [
        SiteConfig(**{k: v for k, v in site.items() if k in SiteConfig.__dataclass_fields__})
        for site in data.pop("sites", [])
    ]
    config_fields = {
        k: v for k, v in data.items()
        if k in RunnerConfig.__dataclass_fields__
    }
    return RunnerConfig(sites=sites, **config_fields)


def load_config_from_json(path: str) -> RunnerConfig:
    """Load RunnerConfig from a JSON file (same structure as YAML)."""
    with open(path) as f:
        data = json.load(f)

    sites = [
        SiteConfig(**{k: v for k, v in site.items() if k in SiteConfig.__dataclass_fields__})
        for site in data.pop("sites", [])
    ]
    config_fields = {
        k: v for k, v in data.items()
        if k in RunnerConfig.__dataclass_fields__
    }
    return RunnerConfig(sites=sites, **config_fields)


def config_from_urls(
    urls: list[str],
    max_pages: int  = 10,
    run_ui:    bool = True,
    run_seo:   bool = True,
    retries:   int  = 2,
) -> RunnerConfig:
    """Build a RunnerConfig directly from a list of URL strings."""
    return RunnerConfig(
        sites=[
            SiteConfig(url=u, max_pages=max_pages, run_ui=run_ui,
                       run_seo=run_seo, retries=retries)
            for u in urls
        ]
    )


# ---------------------------------------------------------------------------
# Lockfile — prevents two cron jobs running at the same time
# ---------------------------------------------------------------------------

class _Lockfile:
    """
    Context manager that acquires an exclusive lock on a file.
    If the lock is already held (another run in progress), raises
    RuntimeError immediately instead of waiting — safe for cron.
    """

    def __init__(self, path: str, logger: logging.Logger):
        self.path   = path
        self.logger = logger
        self._fh    = None

    def __enter__(self):
        self._fh = open(self.path, "w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.write(str(os.getpid()))
            self._fh.flush()
            self.logger.debug(f"Lock acquired: {self.path}")
        except OSError:
            self._fh.close()
            raise RuntimeError(
                f"Another run is already in progress (lock: {self.path}). "
                "Exiting to avoid duplicate runs."
            )
        return self

    def __exit__(self, *_):
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            try:
                os.unlink(self.path)
            except OSError:
                pass
            self.logger.debug(f"Lock released: {self.path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_to_slug(url: str) -> str:
    """Turn a URL into a safe directory name: https://example.com → example_com"""
    import re
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    return re.sub(r"[^a-zA-Z0-9]+", "_", host).strip("_")[:50]


def _log_site_result(result: SiteRunResult, logger: logging.Logger) -> None:
    if result.success:
        logger.info(
            f"  ✓ {result.site.url} — {result.pages_found} pages "
            f"in {result.duration_s:.1f}s"
        )
    else:
        logger.error(
            f"  ✗ {result.site.url} — FAILED after {result.attempts} attempt(s): "
            f"{result.error}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AI Web Tester — Automated multi-site runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single site
  python pipeline/automated_runner.py --url https://example.com

  # Multiple sites
  python pipeline/automated_runner.py --urls https://a.com https://b.com

  # YAML config (recommended for cron)
  python pipeline/automated_runner.py --config pipeline/sites.yaml

  # Dry run (crawl only, no UI/SEO/reports)
  python pipeline/automated_runner.py --config pipeline/sites.yaml --dry-run

  # JSON config + custom output dir
  python pipeline/automated_runner.py --config pipeline/sites.json --output /var/reports
        """,
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--url",    help="Single site URL")
    group.add_argument("--urls",   nargs="+", help="Multiple site URLs")
    group.add_argument("--config", help="Path to YAML or JSON config file")

    p.add_argument("--max-pages",  type=int, default=10)
    p.add_argument("--output",     default="output")
    p.add_argument("--log-dir",    default="logs")
    p.add_argument("--log-level",  default="INFO",
                   choices=["DEBUG","INFO","WARNING","ERROR"])
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--no-ui",      action="store_true")
    p.add_argument("--no-seo",     action="store_true")
    p.add_argument("--retries",    type=int, default=2)
    p.add_argument("--no-headless",action="store_true")
    p.add_argument("--notify",     default="", metavar="EMAIL",
                   help="Email address for run summary")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # ── Build config ──────────────────────────────────────────────────────
    if args.config:
        ext = Path(args.config).suffix.lower()
        cfg = load_config_from_yaml(args.config) if ext in (".yml",".yaml") \
              else load_config_from_json(args.config)
        # CLI flags override config file values when explicitly passed
        if args.output   != "output": cfg.output_dir   = args.output
        if args.log_dir  != "logs":   cfg.log_dir       = args.log_dir
        if args.dry_run:              cfg.dry_run        = True
        if args.notify:               cfg.notify_email   = args.notify
    else:
        urls = [args.url] if args.url else args.urls
        cfg  = config_from_urls(
            urls,
            max_pages = args.max_pages,
            run_ui    = not args.no_ui,
            run_seo   = not args.no_seo,
            retries   = args.retries,
        )
        cfg.output_dir    = args.output
        cfg.log_dir       = args.log_dir
        cfg.log_level     = args.log_level
        cfg.dry_run       = args.dry_run
        cfg.headless      = not args.no_headless
        cfg.notify_email  = args.notify

    # ── Run ───────────────────────────────────────────────────────────────
    runner  = AutomatedRunner(cfg)
    results = runner.run_all()

    # ── Exit code for CI/CD and cron monitoring ───────────────────────────
    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed

    if   failed == 0:             sys.exit(0)   # all passed
    elif failed < len(results):   sys.exit(1)   # partial failure
    else:                         sys.exit(2)   # total failure
