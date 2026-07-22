"""Test: switch to 视频 tab on Doubao image page and verify data-state=active."""
import sys
import time
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aicomic.doubao.browser import DoubaoBrowserClient


def main():
    browser = DoubaoBrowserClient(
        state_file=Path("data/doubao_state.json"),
        cookie_file=Path("data/doubao_cookies.json"),
        headless=False,
        output_dir="data/",
        timeout_sec=60,
        poll_interval_sec=3,
        rate_limit_sec=10,
    )
    browser.ensure_browser()
    page = browser._context.new_page()

    try:
        # ── 1. Navigate to image page ──
        print("1. 导航到图片生成页...")
        page.goto(browser.page_urls["image"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # ── 2. Dump initial tab state ──
        state = page.evaluate("""() => {
            const tabs = document.querySelectorAll('[data-slot="tabs-trigger"]');
            const result = [];
            for (const t of tabs) {
                result.push({
                    text: (t.textContent || '').trim(),
                    tagName: t.tagName,
                    role: t.getAttribute('role'),
                    dataState: t.getAttribute('data-state'),
                    ariaSelected: t.getAttribute('aria-selected'),
                });
            }
            return result;
        }""")
        print(f"   初始 tab 状态: {state}")

        # ── 3. Try Playwright mouse.click() ──
        print("\n2. 尝试 Playwright mouse.click()...")
        for attempt in range(3):
            box = page.evaluate("""() => {
                const tabs = document.querySelectorAll(
                    '[data-slot="tabs-trigger"]');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '视频') {
                        const r = t.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                }
                return null;
            }""")
            if not box:
                print(f"   ✗ 未找到「视频」tab")
                break

            print(f"   点击坐标: ({box['x']:.0f}, {box['y']:.0f})")
            page.mouse.click(box["x"], box["y"])
            page.wait_for_timeout(2000)

            # Verify
            state = page.evaluate("""() => {
                const tabs = document.querySelectorAll(
                    '[data-slot="tabs-trigger"]');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '视频') {
                        return t.getAttribute('data-state');
                    }
                }
                return null;
            }""")
            print(f"   视频 tab data-state = '{state}'")
            if state == "active":
                print(f"   ✓ 切换成功! (attempt {attempt+1})")
                break
            else:
                print(f"   ⚠ 未激活，重试...")

        # ── 4. Try JS dispatchEvent as fallback ──
        active = page.evaluate("""() => {
            const tabs = document.querySelectorAll(
                '[data-slot="tabs-trigger"]');
            for (const t of tabs) {
                if ((t.textContent || '').trim() === '视频') {
                    return t.getAttribute('data-state');
                }
            }
            return null;
        }""")
        if active != "active":
            print("\n3. 尝试 JS dispatchEvent(MouseEvent)...")
            page.evaluate("""() => {
                const tabs = document.querySelectorAll(
                    '[data-slot="tabs-trigger"]');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '视频') {
                        t.dispatchEvent(new MouseEvent('click', {
                            bubbles: true, cancelable: true, view: window
                        }));
                    }
                }
            }""")
            page.wait_for_timeout(2000)
            active = page.evaluate("""() => {
                const tabs = document.querySelectorAll(
                    '[data-slot="tabs-trigger"]');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '视频') {
                        return t.getAttribute('data-state');
                    }
                }
                return null;
            }""")
            print(f"   视频 tab data-state = '{active}'")

        # ── 5. Final state dump ──
        print("\n4. 最终 tab 状态:")
        final = page.evaluate("""() => {
            const tabs = document.querySelectorAll('[data-slot="tabs-trigger"]');
            const result = [];
            for (const t of tabs) {
                result.push({
                    text: (t.textContent || '').trim(),
                    dataState: t.getAttribute('data-state'),
                });
            }
            return result;
        }""")
        for t in final:
            print(f"   tab='{t['text']}' state='{t['dataState']}'")

        print("\n5. 等待10秒供人工观察...")
        time.sleep(10)

    finally:
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
