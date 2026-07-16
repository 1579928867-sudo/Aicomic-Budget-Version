#!/usr/bin/env python3
"""Export Doubao cookies for use with DoubaoBrowserClient.

Usage:
    python scripts/export_cookies.py

This will:
1. Open a Chromium browser window
2. Navigate to the Doubao login page
3. Wait for you to log in manually
4. Save cookies to data/doubao_cookies.json
5. Close the browser
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    output_path = Path("data/doubao_cookies.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60, flush=True)
    print("  Doubao Cookie Exporter", flush=True)
    print("=" * 60, flush=True)
    print(flush=True)
    print("A browser window will open. Please:", flush=True)
    print("  1. Log in to your Doubao account", flush=True)
    print("  2. Verify you can see the main page", flush=True)
    print("  3. Return here and press Enter", flush=True)
    print(flush=True)

    with sync_playwright() as p:
        print("Launching browser...", flush=True)
        browser = p.chromium.launch(headless=False)
        print("Browser launched. Creating context...", flush=True)
        context = browser.new_context()
        page = context.new_page()

        # Navigate to Doubao main page
        print("Navigating to https://www.doubao.com/ ...", flush=True)
        page.goto("https://www.doubao.com/")
        print("Page loaded. Switch to the browser window to log in.", flush=True)

        print("Waiting for you to log in...", flush=True)
        input("\n>>> Press Enter after logging in: ")

        # Get all cookies
        cookies = context.cookies()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"Cookies saved to {output_path}")
        print(f"Exported {len(cookies)} cookies")

        browser.close()


if __name__ == "__main__":
    main()
