#!/usr/bin/env python3
"""Export Doubao/即梦 cookies for use with DoubaoVideoGenerator.

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

    print("=" * 60)
    print("  Doubao Cookie Exporter")
    print("=" * 60)
    print()
    print("A browser window will open. Please:")
    print("  1. Log in to your Doubao/即梦 account")
    print("  2. Navigate to the video generation page")
    print("  3. Verify you can see the prompt input box")
    print("  4. Return here and press Enter")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Navigate to the video gen page
        page.goto("https://jimeng.jianying.com/ai-tool/video/generate")

        input("Press Enter after logging in...")

        # Get all cookies
        cookies = context.cookies()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        print(f"Cookies saved to {output_path}")
        print(f"Exported {len(cookies)} cookies")

        browser.close()


if __name__ == "__main__":
    main()
