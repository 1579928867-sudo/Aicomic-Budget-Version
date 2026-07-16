#!/usr/bin/env python3
"""Quick smoke test: generate one image via Doubao (real).

Usage (run from project root):
    python scripts/test_image_gen.py
"""

import sys
from pathlib import Path

# Add src to path so we can import aicomic
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicomic.doubao.browser import DoubaoBrowserClient, CookieExpiredError


def main():
    cookie_file = Path("data/doubao_cookies.json")
    if not cookie_file.exists():
        print("Cookie file not found. Run export_cookies.py first.")
        return

    client = DoubaoBrowserClient(
        cookie_file=cookie_file,
        headless=False,             # Show browser for debugging
        output_dir="data/",
        timeout_sec=300,            # 5 min max wait
        poll_interval_sec=3,
    )

    try:
        print("Starting image generation...")
        print('  Prompt: "一只可爱的橘猫坐在窗台上，阳光洒落"')
        print("  Ratio: 16:9")
        print()

        result = client.generate_image(
            prompt="一只可爱的橘猫坐在窗台上，阳光洒落，写实摄影风格",
            aspect_ratio="16:9",
        )

        print(f"Success: {result.success}")
        if result.success:
            print(f"File:    {result.file_path}")
            print(f"Meta:    {result.metadata}")
        else:
            print(f"Error:   {result.error}")

    except CookieExpiredError:
        print("Cookies expired! Re-run export_cookies.py to re-login.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
