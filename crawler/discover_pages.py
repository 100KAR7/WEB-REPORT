"""
example_usage.py
----------------
Demonstrates every way to use discover_pages().

Run from the project root:
    python example_usage.py
"""

import sys
import os

# Allow running from the project root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from crawler.discover_pages import discover_pages


# ── Example 1 — Basic usage ────────────────────────────────────────────────
def example_basic():
    print("=" * 60)
    print("EXAMPLE 1 — Basic crawl (default settings)")
    print("=" * 60)

    pages = discover_pages("https://books.toscrape.com", max_pages=10)

    print(f"\nFound {len(pages)} pages:\n")
    for page in pages:
        print(f"  {page}")


# ── Example 2 — Quiet mode + inspect results ──────────────────────────────
def example_quiet():
    print("\n" + "=" * 60)
    print("EXAMPLE 2 — Quiet mode, inspect result list")
    print("=" * 60)

    pages = discover_pages(
        "https://books.toscrape.com",
        max_pages=5,
        verbose=False,   # ← no console noise
    )

    # Handy things you can do with the list:
    print(f"Total pages found : {len(pages)}")
    print(f"First page        : {pages[0]  if pages else 'none'}")
    print(f"Last page         : {pages[-1] if pages else 'none'}")

    # Filter by path pattern
    catalogue = [p for p in pages if "/catalogue/" in p]
    print(f"Catalogue pages   : {len(catalogue)}")


# ── Example 3 — Save to file ──────────────────────────────────────────────
def example_save_to_file():
    print("\n" + "=" * 60)
    print("EXAMPLE 3 — Save discovered URLs to a text file")
    print("=" * 60)

    pages = discover_pages(
        "https://books.toscrape.com",
        max_pages=10,
        verbose=False,
    )

    output_file = "discovered_urls.txt"
    with open(output_file, "w") as f:
        for url in pages:
            f.write(url + "\n")

    print(f"Saved {len(pages)} URLs → {output_file}")


# ── Example 4 — Integrate with the rest of the pipeline ──────────────────
def example_pipeline_integration():
    print("\n" + "=" * 60)
    print("EXAMPLE 4 — Feed results into another module")
    print("=" * 60)

    # Discover first, then hand the URL list to any downstream module.
    # Nothing in discover_pages cares about the rest of the project —
    # it just returns plain strings.

    urls = discover_pages(
        "https://books.toscrape.com",
        max_pages=5,
        verbose=False,
    )

    # Simulate handing off to a checker
    print(f"\nPassing {len(urls)} URLs to downstream checker...\n")
    for url in urls:
        # e.g. performance_checker, seo_checker, ai_analyzer …
        print(f"  → would audit: {url}")


# ── Run all examples ──────────────────────────────────────────────────────
if __name__ == "__main__":
    example_basic()
    example_quiet()
    example_save_to_file()
    example_pipeline_integration()