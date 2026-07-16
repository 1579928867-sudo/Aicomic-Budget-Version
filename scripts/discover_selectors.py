#!/usr/bin/env python3
"""Open Doubao pages and dump CSS selectors for manual inspection.

Usage:
    python scripts/discover_selectors.py

This opens a headed browser with your logged-in cookies so you can
inspect the Doubao image and video generation pages with DevTools.
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


COOKIE_FILE = Path("data/doubao_cookies.json")
IMAGE_PAGE = "https://www.doubao.com/chat/create-image"
VIDEO_PAGE = "https://www.doubao.com/chat/create-video"


def main():
    if not COOKIE_FILE.exists():
        print(f"Cookie file not found: {COOKIE_FILE}")
        print("Run scripts/export_cookies.py first to log in.")
        return

    cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        context.add_cookies(cookies)

        # ── Image generation page ──
        print("=" * 60)
        print("Opening Doubao IMAGE generation page...")
        print("Please inspect the page with DevTools to find selectors for:")
        print("  - Prompt input textarea")
        print("  - Generate button")
        print("  - Aspect ratio buttons (1:1, 16:9, 9:16)")
        print("  - Result image element")
        print("  - Loading/generating indicator")
        print("=" * 60)
        page1 = context.new_page()
        page1.goto(IMAGE_PAGE, wait_until="domcontentloaded")
        page1.pause()  # Open Playwright Inspector

        input("Press Enter to continue to video page...")

        # ── Video generation page ──
        print("=" * 60)
        print("Opening Doubao VIDEO generation page...")
        print("Please inspect the page with DevTools to find selectors for:")
        print("  - Prompt input textarea")
        print("  - Generate button")
        print("  - Result video element")
        print("  - Success/failed status indicators")
        print("=" * 60)
        page2 = context.new_page()
        page2.goto(VIDEO_PAGE, wait_until="domcontentloaded")
        page2.pause()  # Open Playwright Inspector

        input("Press Enter to close browser...")

        browser.close()

    print("Done. Update config/settings.yaml doubao.selectors with your findings.")


if __name__ == "__main__":
    main()
