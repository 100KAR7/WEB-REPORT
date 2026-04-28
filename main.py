"""
main.py
-------
CLI entry point for the AI Web Tester.

Usage:
    python main.py --url https://example.com
    python main.py --url https://example.com --max-pages 5 --format html
    python main.py --url https://example.com --no-ai
    python main.py --url https://example.com --no-seo --format json
"""

import argparse
import sys

from config.settings import settings
from config.logging_config import logger
from pipeline.runner import PipelineRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-Powered Website Testing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --url https://example.com
  python main.py --url https://example.com --max-pages 5 --format both
  python main.py --url https://example.com --no-ai --format json
        """,
    )
    parser.add_argument(
        "--url", required=True, help="Target website URL to audit"
    )
    parser.add_argument(
        "--max-pages", type=int, default=10,
        help="Maximum number of pages to crawl (default: 10)"
    )
    parser.add_argument(
        "--format", choices=["html", "json", "both"], default="html",
        help="Report output format (default: html)"
    )
    parser.add_argument(
        "--no-ai", action="store_true",
        help="Skip AI analysis (useful if no API key is set)"
    )
    parser.add_argument(
        "--no-seo", action="store_true",
        help="Skip SEO checks"
    )
    parser.add_argument(
        "--no-perf", action="store_true",
        help="Skip performance checks"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Apply CLI flags to the global settings singleton
    settings.report_format      = args.format
    settings.run_ai_analysis    = not args.no_ai
    settings.run_seo            = not args.no_seo
    settings.run_performance    = not args.no_perf
    settings.validate_runtime(args.url, args.max_pages)

    try:
        runner = PipelineRunner(url=args.url, max_pages=args.max_pages)
        report_path = runner.run()
        print(f"\nReport ready -> {report_path}\n")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Pipeline failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
