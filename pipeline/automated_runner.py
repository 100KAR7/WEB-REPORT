"""
pipeline/automated_runner.py
-----------------------------
Production-grade automated runner — now with:
  • Ollama LLM analysis (local, free, no API key)
  • PDF report generation (via ReportLab)
  • Structured file logging
  • Per-site error isolation + retry logic
  • Multi-site support (YAML config or CLI flags)
  • Lockfile prevents overlapping cron runs
  • Exit codes for CI/CD (0=all pass, 1=partial, 2=all fail)

Cron examples (add with: crontab -e):
  # Full run daily at 2 AM
  0 2 * * * cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml >> logs/cron.log 2>&1

  # SEO-only every 6 hours
  0 */6 * * * cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml --no-ui >> logs/cron.log 2>&1

  # Full run + LLM + PDF every Monday at 6 AM
  0 6 * * 1  cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml --llm --pdf >> logs/cron.log 2>&1

Usage:
  python pipeline/automated_runner.py --url https://example.com
  python pipeline/automated_runner.py --url https://example.com --llm --pdf
  python pipeline/automated_runner.py --urls https://a.com https://b.com --llm --pdf
  python pipeline/automated_runner.py --config pipeline/sites.yaml
  python pipeline/automated_runner.py --config pipeline/sites.yaml --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import os
import smtplib
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

# ── Project root on sys.path ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


_configure_stdio()

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging — writes to console + daily log file
# ---------------------------------------------------------------------------

def setup_logging(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Configure logging to:
      • stdout        — coloured via rich (if installed) or plain text
      • logs/runner_YYYY-MM-DD.log — one file per day, never truncated
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"runner_{datetime.now().strftime('%Y-%m-%d')}.log"

    fmt      = "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger("ai_web_tester")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    # File handler (always plain text — cron-safe)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    logger.addHandler(fh)

    # Console handler (rich if available, else plain)
    try:
        from rich.logging import RichHandler
        ch = RichHandler(rich_tracebacks=True, show_path=False)
    except ImportError:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))
    logger.addHandler(ch)

    logger.info(f"Log file: {log_file}")
    return logger


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SiteConfig:
    """Configuration for one website to test."""
    url:        str
    max_pages:  int   = 10
    run_ui:     bool  = True
    run_seo:    bool  = True
    run_llm:    bool  = False     # Ollama LLM analysis
    run_pdf:    bool  = False     # PDF report output
    retries:    int   = 2
    label:      str   = ""
    enabled:    bool  = True

    def __post_init__(self):
        if not self.label:
            from urllib.parse import urlparse
            self.label = urlparse(self.url).netloc or self.url


@dataclass
class RunnerConfig:
    """Top-level runner configuration."""
    sites:         list[SiteConfig] = field(default_factory=list)
    output_dir:    str  = "output"
    log_dir:       str  = "logs"
    log_level:     str  = "INFO"
    headless:      bool = True
    dry_run:       bool = False
    run_llm:       bool = False   # global LLM toggle (overrides per-site)
    run_pdf:       bool = False   # global PDF toggle
    ollama_model:  str  = "llama3"
    ollama_url:    str  = "http://localhost:11434"
    notify_email:  str  = ""
    lock_file:     str  = str(Path(tempfile.gettempdir()) / "ai_web_tester.lock")


# ---------------------------------------------------------------------------
# Per-site run result
# ---------------------------------------------------------------------------

@dataclass
class SiteRunResult:
    """Outcome of running the full pipeline against one site."""
    site:         SiteConfig
    success:      bool           = False
    pages_found:  int            = 0
    report_paths: dict           = field(default_factory=dict)
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
# Automated runner
# ---------------------------------------------------------------------------

class AutomatedRunner:
    """
    Runs the full pipeline against one or more sites with:
      - Ollama LLM analysis
      - PDF report generation
      - Structured logging to file
      - Per-site error isolation
      - Exponential retry back-off
      - Lockfile for cron safety
      - Email notification hook
    """

    def __init__(self, config: RunnerConfig):
        self.config = config
        self.logger = setup_logging(config.log_dir, config.log_level)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_all(self) -> list[SiteRunResult]:
        """Run all enabled sites and return results."""
        sites = [s for s in self.config.sites if s.enabled]

        if not sites:
            self.logger.warning("No enabled sites found. Exiting.")
            return []

        self.logger.info("=" * 60)
        self.logger.info("AI Web Tester — Automated Run")
        self.logger.info(f"Sites      : {len(sites)}")
        self.logger.info(f"LLM        : {'ollama/' + self.config.ollama_model if self.config.run_llm else 'disabled'}")
        self.logger.info(f"PDF reports: {'yes' if self.config.run_pdf else 'no'}")
        self.logger.info(f"Dry run    : {self.config.dry_run}")
        self.logger.info("=" * 60)

        with _Lockfile(self.config.lock_file, self.logger):
            t0      = time.perf_counter()
            results = []

            for idx, site in enumerate(sites, 1):
                self.logger.info(f"[{idx}/{len(sites)}] {site.url}")
                result = self._run_with_retry(site)
                results.append(result)
                _log_result(result, self.logger)

            total_s = time.perf_counter() - t0
            self._log_summary(results, total_s)
            self._save_manifest(results, total_s)

            if self.config.notify_email:
                self._send_email(results, total_s)

        return results

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _run_with_retry(self, site: SiteConfig) -> SiteRunResult:
        result      = SiteRunResult(site=site)
        max_attempts = max(1, site.retries)

        for attempt in range(1, max_attempts + 1):
            result.attempts = attempt
            if attempt > 1:
                wait = 2 ** attempt
                self.logger.warning(f"  Retry {attempt}/{max_attempts} (wait {wait}s)")
                time.sleep(wait)

            try:
                t0 = time.perf_counter()
                self._run_site(site, result)
                result.duration_s = time.perf_counter() - t0
                result.success    = True
                return result

            except Exception as exc:
                result.error = f"{type(exc).__name__}: {exc}"
                self.logger.error(f"  Attempt {attempt} failed: {exc}", exc_info=True)

        return result

    # ------------------------------------------------------------------
    # Core pipeline execution for one site
    # ------------------------------------------------------------------

    def _run_site(self, site: SiteConfig, result: SiteRunResult) -> None:
        """
        Full pipeline for one site:
          Crawl → UI tests → SEO → Ollama LLM → PDF + JSON reports
        """
        from pipeline.run_pipeline import Pipeline
        from reports.generate_report import ReportBuilder
        from reports.pdf_report import PDFReportBuilder

        # Per-site output dir:  output/example_com/
        site_slug   = _url_to_slug(site.url)
        site_outdir = os.path.join(self.config.output_dir, site_slug)
        os.makedirs(site_outdir, exist_ok=True)

        # Determine whether to run LLM and PDF for this site
        do_llm = (site.run_llm or self.config.run_llm) and not self.config.dry_run
        do_pdf = (site.run_pdf or self.config.run_pdf) and not self.config.dry_run

        # ── Step 1: Crawl + UI + SEO ──────────────────────────────────────
        self.logger.info(f"  Crawling: {site.url} (max {site.max_pages} pages)")
        pipeline = Pipeline(
            url            = site.url,
            max_pages      = site.max_pages,
            run_ui         = site.run_ui  and not self.config.dry_run,
            run_seo        = site.run_seo and not self.config.dry_run,
            screenshot_dir = os.path.join(site_outdir, "screenshots"),
            headless       = self.config.headless,
        )
        page_results       = pipeline.run()
        result.pages_found = len(page_results)
        self.logger.info(f"  Pages found: {result.pages_found}")

        if not page_results:
            raise RuntimeError(
                f"No pages could be fetched from {site.url}. "
                "Check the URL and network access."
            )

        page_errors = [page for page in page_results if page.error]
        if page_errors and len(page_errors) == len(page_results):
            sample_errors = "; ".join(
                f"{page.url}: {page.error}"
                for page in page_errors[:3]
            )
            raise RuntimeError(
                "All analyzed pages failed. "
                f"Sample errors: {sample_errors}"
            )

        if self.config.dry_run:
            self.logger.info("  Dry run — skipping analysis and reports.")
            return

        # ── Step 2: Ollama LLM analysis (optional) ────────────────────────
        llm_report = None
        if do_llm:
            self.logger.info(f"  Running Ollama LLM analysis ({self.config.ollama_model})...")
            try:
                from ai_analysis.analyzer import LLMAnalyzer
                llm_report = LLMAnalyzer(
                    model    = self.config.ollama_model,
                    base_url = self.config.ollama_url,
                ).analyze(page_results, site_url=site.url)

                if llm_report.success:
                    self.logger.info("  LLM analysis complete.")
                else:
                    self.logger.warning(f"  LLM analysis failed: {llm_report.error}")
            except Exception as exc:
                self.logger.error(f"  LLM analysis error: {exc}")

        # ── Step 3: Reports ───────────────────────────────────────────────
        self.logger.info(f"  Generating reports → {site_outdir}")

        # Always generate JSON + TXT
        builder = ReportBuilder(site_url=site.url, output_dir=site_outdir)
        builder.add_pages(page_results)
        if llm_report:
            builder.add_llm_report(llm_report)
        paths = builder.save()
        result.report_paths.update(paths)

        # Generate PDF if requested
        if do_pdf:
            self.logger.info("  Generating PDF report...")
            try:
                pdf_builder = PDFReportBuilder(
                    site_url   = site.url,
                    output_dir = site_outdir,
                )
                pdf_builder.add_pages(page_results)
                if llm_report:
                    pdf_builder.add_llm_report(llm_report)
                pdf_path = pdf_builder.save()
                result.report_paths["pdf"] = pdf_path
                self.logger.info(f"  PDF saved: {pdf_path}")
            except Exception as exc:
                self.logger.error(f"  PDF generation failed: {exc}")

        self.logger.info(f"  Reports: {list(result.report_paths.values())}")

    # ------------------------------------------------------------------
    # Summary + manifest
    # ------------------------------------------------------------------

    def _log_summary(self, results: list[SiteRunResult], total_s: float) -> None:
        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed
        self.logger.info("=" * 60)
        self.logger.info(
            f"RUN COMPLETE — {passed} passed / {failed} failed in {total_s:.1f}s"
        )
        for r in results:
            status = "PASS" if r.success else "FAIL"
            pdfs   = "  [PDF]" if "pdf" in r.report_paths else ""
            self.logger.info(
                f"  [{status}] {r.site.url}  "
                f"({r.pages_found} pages, {r.duration_s:.1f}s){pdfs}"
            )
        self.logger.info("=" * 60)

    def _save_manifest(self, results: list[SiteRunResult], total_s: float) -> None:
        os.makedirs(self.config.output_dir, exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        manifest = {
            "run_at":       datetime.now().isoformat(timespec="seconds"),
            "total_s":      round(total_s, 2),
            "dry_run":      self.config.dry_run,
            "llm_enabled":  self.config.run_llm,
            "pdf_enabled":  self.config.run_pdf,
            "ollama_model": self.config.ollama_model,
            "sites_total":  len(results),
            "sites_passed": sum(1 for r in results if r.success),
            "sites_failed": sum(1 for r in results if not r.success),
            "sites":        [r.to_dict() for r in results],
        }
        path = os.path.join(self.config.output_dir, f"manifest_{ts}.json")
        with open(path, "w") as f:
            json.dump(manifest, f, indent=2)
        self.logger.info(f"Run manifest → {path}")

    # ------------------------------------------------------------------
    # Email notification (optional)
    # ------------------------------------------------------------------

    def _send_email(self, results: list[SiteRunResult], total_s: float) -> None:
        smtp_host = os.getenv("SMTP_HOST", "")
        if not smtp_host:
            self.logger.warning("SMTP_HOST not set — skipping email.")
            return

        passed  = sum(1 for r in results if r.success)
        failed  = len(results) - passed
        subject = (
            f"[AI Web Tester] {'All passed' if failed == 0 else f'{failed} failed'}"
            f" — {datetime.now().strftime('%Y-%m-%d')}"
        )
        lines = [
            "AI Web Tester — Run Summary",
            f"Date    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Duration: {total_s:.1f}s",
            f"Passed  : {passed}/{len(results)}",
            "",
        ]
        for r in results:
            lines.append(f"  [{'PASS' if r.success else 'FAIL'}] {r.site.url}")
            if r.error:
                lines.append(f"        Error: {r.error}")
            for k, v in r.report_paths.items():
                lines.append(f"        {k.upper()}: {v}")
        body = "\n".join(lines)

        try:
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASS", "")
            smtp_from = os.getenv("SMTP_FROM", smtp_user)

            msg            = MIMEMultipart()
            msg["From"]    = smtp_from
            msg["To"]      = self.config.notify_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_host, smtp_port) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)

            self.logger.info(f"Email sent to {self.config.notify_email}")
        except Exception as exc:
            self.logger.error(f"Email failed: {exc}")


# ---------------------------------------------------------------------------
# Config loaders
# ---------------------------------------------------------------------------

def load_config_from_yaml(path: str) -> RunnerConfig:
    if not _YAML_AVAILABLE:
        raise ImportError("PyYAML not installed. Run: pip install pyyaml")
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    sites = [
        SiteConfig(**{k: v for k, v in s.items() if k in SiteConfig.__dataclass_fields__})
        for s in data.pop("sites", [])
    ]
    cfg_fields = {k: v for k, v in data.items() if k in RunnerConfig.__dataclass_fields__}
    return RunnerConfig(sites=sites, **cfg_fields)


def load_config_from_json(path: str) -> RunnerConfig:
    with open(path) as f:
        data = json.load(f)
    sites = [
        SiteConfig(**{k: v for k, v in s.items() if k in SiteConfig.__dataclass_fields__})
        for s in data.pop("sites", [])
    ]
    cfg_fields = {k: v for k, v in data.items() if k in RunnerConfig.__dataclass_fields__}
    return RunnerConfig(sites=sites, **cfg_fields)


def config_from_urls(urls: list[str], **kwargs) -> RunnerConfig:
    return RunnerConfig(
        sites=[SiteConfig(url=u, **{k: v for k, v in kwargs.items()
                                    if k in SiteConfig.__dataclass_fields__})
               for u in urls],
        **{k: v for k, v in kwargs.items() if k in RunnerConfig.__dataclass_fields__},
    )


# ---------------------------------------------------------------------------
# Lockfile — prevents overlapping cron runs
# ---------------------------------------------------------------------------

class _Lockfile:
    def __init__(self, path: str, logger: logging.Logger):
        self.path   = path
        self.logger = logger
        self._fh    = None

    def __enter__(self):
        lock_path = Path(self.path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(lock_path, "a+")
        try:
            if fcntl is not None:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            elif msvcrt is not None:
                self._fh.seek(0)
                self._fh.write(" ")
                self._fh.flush()
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                raise RuntimeError("No supported file locking primitive is available.")

            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(str(os.getpid()))
            self._fh.flush()
        except OSError:
            self._fh.close()
            raise RuntimeError(
                f"Another run already in progress (lock: {self.path}). Skipping."
            )
        return self

    def __exit__(self, *_):
        if self._fh:
            try:
                if fcntl is not None:
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
                elif msvcrt is not None:
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self._fh.close()
            try:
                os.unlink(self.path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_to_slug(url: str) -> str:
    import re
    from urllib.parse import urlparse
    return re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(url).netloc).strip("_")[:50]


def _log_result(result: SiteRunResult, logger: logging.Logger) -> None:
    if result.success:
        pdfs = "  PDF generated" if "pdf" in result.report_paths else ""
        logger.info(
            f"  PASS  {result.site.url}  "
            f"({result.pages_found} pages, {result.duration_s:.1f}s){pdfs}"
        )
    else:
        logger.error(
            f"  FAIL  {result.site.url}  "
            f"after {result.attempts} attempt(s): {result.error}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AI Web Tester — Automated runner with Ollama LLM + PDF reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single site, basic
  python pipeline/automated_runner.py --url https://example.com

  # Single site with LLM analysis and PDF report
  python pipeline/automated_runner.py --url https://example.com --llm --pdf

  # Multiple sites
  python pipeline/automated_runner.py --urls https://a.com https://b.com --llm --pdf

  # YAML config (recommended for cron)
  python pipeline/automated_runner.py --config pipeline/sites.yaml

  # Dry run (crawl only)
  python pipeline/automated_runner.py --config pipeline/sites.yaml --dry-run

Cron examples (crontab -e):
  # Daily at 2 AM
  0 2 * * * cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml --llm --pdf >> logs/cron.log 2>&1

  # Every 6 hours, SEO only
  0 */6 * * * cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml --no-ui >> logs/cron.log 2>&1

  # Weekly deep audit every Monday
  0 6 * * 1 cd /path/to/ai_web_tester && python pipeline/automated_runner.py --config pipeline/sites.yaml --llm --pdf --notify you@email.com >> logs/cron.log 2>&1
        """,
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--url",    help="Single URL")
    group.add_argument("--urls",   nargs="+", help="Multiple URLs")
    group.add_argument("--config", help="YAML or JSON config file")

    p.add_argument("--max-pages",    type=int,  default=10)
    p.add_argument("--output",       default="output")
    p.add_argument("--log-dir",      default="logs")
    p.add_argument("--log-level",    default="INFO",
                   choices=["DEBUG","INFO","WARNING","ERROR"])
    p.add_argument("--dry-run",      action="store_true")
    p.add_argument("--no-ui",        action="store_true")
    p.add_argument("--no-seo",       action="store_true")
    p.add_argument("--llm",          action="store_true", help="Enable Ollama LLM analysis")
    p.add_argument("--pdf",          action="store_true", help="Generate PDF report")
    p.add_argument("--ollama-model", default="llama3",    help="Ollama model name")
    p.add_argument("--ollama-url",   default="http://localhost:11434")
    p.add_argument("--retries",      type=int, default=2)
    p.add_argument("--no-headless",  action="store_true")
    p.add_argument("--notify",       default="", metavar="EMAIL")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.config:
        ext = Path(args.config).suffix.lower()
        cfg = (load_config_from_yaml(args.config)
               if ext in (".yml", ".yaml")
               else load_config_from_json(args.config))
        if args.output != "output":
            cfg.output_dir = args.output
        if args.log_dir != "logs":
            cfg.log_dir = args.log_dir
        if args.log_level != "INFO":
            cfg.log_level = args.log_level
        if args.dry_run:
            cfg.dry_run = True
        if args.llm:
            cfg.run_llm = True
        if args.pdf:
            cfg.run_pdf = True
        if args.no_headless:
            cfg.headless = False
        if args.notify:
            cfg.notify_email = args.notify
        cfg.ollama_model = args.ollama_model
        cfg.ollama_url   = args.ollama_url

        for site in cfg.sites:
            if args.max_pages != 10:
                site.max_pages = args.max_pages
            if args.no_ui:
                site.run_ui = False
            if args.no_seo:
                site.run_seo = False
            if args.retries != 2:
                site.retries = args.retries
    else:
        urls = [args.url] if args.url else args.urls
        cfg  = config_from_urls(
            urls,
            max_pages  = args.max_pages,
            run_ui     = not args.no_ui,
            run_seo    = not args.no_seo,
            run_llm    = args.llm,
            run_pdf    = args.pdf,
            retries    = args.retries,
        )
        cfg.output_dir   = args.output
        cfg.log_dir      = args.log_dir
        cfg.log_level    = args.log_level
        cfg.dry_run      = args.dry_run
        cfg.headless     = not args.no_headless
        cfg.notify_email = args.notify
        cfg.run_llm      = args.llm
        cfg.run_pdf      = args.pdf
        cfg.ollama_model = args.ollama_model
        cfg.ollama_url   = args.ollama_url

    runner  = AutomatedRunner(cfg)
    results = runner.run_all()

    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed
    sys.exit(0 if failed == 0 else (1 if failed < len(results) else 2))
