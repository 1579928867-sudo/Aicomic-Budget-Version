"""Test: find file input on Doubao video tab and try file upload."""
import sys
import time
from pathlib import Path

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
        # ── 1. Navigate ──
        print("1. 导航到图片生成页...")
        page.goto(browser.page_urls["image"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # ── 2. Switch to video tab ──
        print("\n2. 切换到视频 tab...")
        for attempt in range(3):
            box = page.evaluate("""() => {
                const tabs = document.querySelectorAll('[data-slot="tabs-trigger"]');
                for (const t of tabs) {
                    if ((t.textContent || '').trim() === '视频') {
                        const r = t.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                }
                return null;
            }""")
            if box:
                page.mouse.click(box["x"], box["y"])
                page.wait_for_timeout(2000)
                active = page.evaluate("""() => {
                    const tabs = document.querySelectorAll('[data-slot="tabs-trigger"]');
                    for (const t of tabs) {
                        if ((t.textContent || '').trim() === '视频')
                            return t.getAttribute('data-state');
                    }
                    return null;
                }""")
                print(f"   tab data-state = '{active}'")
                if active == "active":
                    break

        # ── 3. Find ALL file inputs on the page ──
        print("\n3. 查找所有 input[type=file] 元素:")
        file_inputs = page.evaluate("""() => {
            const inputs = document.querySelectorAll('input[type="file"]');
            const result = [];
            for (const inp of inputs) {
                const r = inp.getBoundingClientRect();
                const parent = inp.parentElement;
                const grandparent = parent ? parent.parentElement : null;
                result.push({
                    visible: r.width > 0 && r.height > 0,
                    rect: {x: r.x, y: r.y, w: r.width, h: r.height},
                    accept: inp.getAttribute('accept'),
                    multiple: inp.multiple,
                    id: inp.id,
                    className: inp.className,
                    parentClass: parent ? parent.className : null,
                    parentTag: parent ? parent.tagName : null,
                    gpClass: grandparent ? grandparent.className : null,
                    gpTag: grandparent ? grandparent.tagName : null,
                });
            }
            return result;
        }""")
        for i, fi in enumerate(file_inputs):
            print(f"   [{i}] visible={fi['visible']} accept={fi['accept']}")
            print(f"       rect=({fi['rect']['x']:.0f},{fi['rect']['y']:.0f}) "
                  f"{fi['rect']['w']:.0f}x{fi['rect']['h']:.0f}")
            print(f"       class={fi['className'][:80]}")
            print(f"       parent=({fi['parentTag']}) class={fi['parentClass'][:80]}")
            print(f"       grandparent=({fi['gpTag']}) class={fi['gpClass'][:80]}")

        # ── 4. Find the "参考图" label and its associated hidden input ──
        print("\n4. 查找 '参考图' 标签关联的元素:")
        ref_labels = page.evaluate("""() => {
            const result = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = (el.textContent || '').trim();
                if (text === '参考图' && el.children.length <= 2) {
                    const r = el.getBoundingClientRect();
                    // Walk up to find file input
                    let parent = el.parentElement;
                    for (let i = 0; i < 5 && parent; i++) {
                        const fi = parent.querySelector('input[type="file"]');
                        if (fi) {
                            result.push({
                                labelRect: {x: r.x, y: r.y, w: r.width, h: r.height},
                                labelTag: el.tagName,
                                labelClass: el.className,
                                fileInputTag: fi.tagName,
                                fileInputClass: fi.className,
                                fileInputAccept: fi.getAttribute('accept'),
                                fileInputMultiple: fi.multiple,
                                fileInputRect: (() => {
                                    const fr = fi.getBoundingClientRect();
                                    return {x: fr.x, y: fr.y, w: fr.width, h: fr.height};
                                })(),
                                wrapperTag: parent.tagName,
                                wrapperClass: parent.className,
                            });
                            break;
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return result;
        }""")
        for i, rl in enumerate(ref_labels):
            print(f"   [{i}] label rect=({rl['labelRect']['x']:.0f},{rl['labelRect']['y']:.0f})")
            print(f"       fileInput: class={rl['fileInputClass'][:80]}")
            print(f"       fileInput accept={rl['fileInputAccept']} "
                  f"multiple={rl['fileInputMultiple']}")
            print(f"       fileInput rect=({rl['fileInputRect']['x']:.0f},"
                  f"{rl['fileInputRect']['y']:.0f}) {rl['fileInputRect']['w']:.0f}x"
                  f"{rl['fileInputRect']['h']:.0f}")

        # ── 5. Try uploading a test image via set_input_files on each file input ──
        test_img = None
        for p in Path("data/images").glob("*.jpg"):
            test_img = str(p.resolve())
            break

        if test_img and file_inputs:
            print(f"\n5. 尝试上传测试图片: {Path(test_img).name}")
            # Use the first hidden file input found near "参考图"
            for fi_idx, fi in enumerate(file_inputs):
                if fi['accept'] and 'image' in (fi['accept'] or ''):
                    print(f"   尝试 input[{fi_idx}]..."
                          f" visible={fi['visible']}")
                    try:
                        # Build a selector targeting this specific file input
                        sel = 'input[type="file"]'
                        if fi['id']:
                            sel = f'input[type="file"]#{fi["id"]}'
                        page.set_input_files(sel, test_img)
                        page.wait_for_timeout(3000)
                        print(f"   ✓ set_input_files 完成，等待3秒观察DOM...")

                        # Check if any attachment appeared
                        count = page.evaluate("""() => {
                            const imgs = document.querySelectorAll('img[src]');
                            let c = 0;
                            for (const img of imgs) {
                                const src = img.getAttribute('src') || '';
                                if (img.naturalWidth > 40 && (src.startsWith('blob:')
                                    || src.startsWith('data:') || src.startsWith('http')))
                                    c++;
                            }
                            return c;
                        }""")
                        print(f"   页面中图片数(>40px): {count}")
                        break
                    except Exception as e:
                        print(f"   ✗ 失败: {e}")

        print("\n6. 等待15秒供人工观察...")
        time.sleep(15)

    finally:
        page.close()
        browser.close()


if __name__ == "__main__":
    main()
