#!/usr/bin/env python3
r"""Doubao 图片生成校准脚本 — 生成 + 逐张下载 4 张四宫格图片。

策略（按用户指导）：
  1. 输入 prompt → Enter → 等待 4 张四宫格图片生成完成
  2. 逐张点击图片进入详情页
  3. 详情页图片上方有一排图标，最后一个蓝色的是下载按钮
  4. 点击下载 → CDP + 文件系统轮询捕获文件
  5. Escape 返回 → 下一张

用法（从项目根目录）：
    python scripts/calibrate_image.py --check       # 环境检查
    python scripts/calibrate_image.py --discover    # 详细模式（含 DOM 导出）
    python scripts/calibrate_image.py --e2e         # 精简模式
    python scripts/calibrate_image.py --e2e --prompt "自定义 prompt"
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ── 强制 flush 避免 Windows 输出缓冲 ──
_print = print

def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _print(*args, **kwargs)


# ── 配置 ──
COOKIE_FILE = Path("data/doubao_cookies.json")
OUTPUT_DIR = Path("data/")
IMAGE_PAGE = "https://www.doubao.com/chat/create-image"
CALIBRATION_OUTPUT = Path("data/calibration_report.json")


def sep():
    print("\n" + "-" * 50)


def check_prerequisites():
    """快速环境检查。"""
    print("🔍 环境检查...")
    ok = True

    print(f"   Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        print("   Playwright: ✅")
    except ImportError:
        print("   Playwright: ❌ → pip install playwright && python -m playwright install chromium")
        ok = False

    if COOKIE_FILE.exists():
        try:
            cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
            print(f"   Cookie: ✅ ({len(cookies)} 条)")
        except Exception:
            print(f"   Cookie: ❌ 解析失败")
            ok = False
    else:
        print(f"   Cookie: ❌ 不存在 → python scripts/export_cookies.py")
        ok = False

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"   输出目录: ✅ ({OUTPUT_DIR.resolve()})")
    return ok


# ══════════════════════════════════════════════════════════════════════
# 主校准器
# ══════════════════════════════════════════════════════════════════════

class ImageCalibrator:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.cookies = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "page_url": IMAGE_PAGE,
        }

    # ── 唯一入口 ──

    def run(self, prompt: str, verbose: bool = False):
        """核心流程：生成 → 逐张下载。"""
        from playwright.sync_api import sync_playwright

        mode = "DISCOVER" if verbose else "E2E"
        print(f"🚀 启动浏览器 ({mode} 模式)...")
        print(f"   Prompt: {prompt}")

        dl_dir, img_dir = self._prepare_dirs()

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(accept_downloads=True)
            context.add_cookies(self.cookies)
            page = context.new_page()
            self._setup_cdp(context, page, dl_dir)

            try:
                # ── 1. 导航 ──
                sep()
                print("📌 [1/4] 导航")
                page.goto(IMAGE_PAGE, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    print("❌ Cookie 已过期 → python scripts/export_cookies.py")
                    return
                print("✅ 已登录")

                # ── 2. 输入 + 生成 ──
                sep()
                print("📌 [2/4] 输入 prompt + 触发")
                input_sel = 'div[contenteditable="true"][role="textbox"]'
                page.wait_for_selector(input_sel, timeout=15000)
                page.click(input_sel)
                page.wait_for_timeout(300)
                page.keyboard.insert_text(prompt)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                print("✅ 已触发")

                # ── 3. 等待完成 ──
                sep()
                print("📌 [3/4] 等待图片生成（最多5分钟）...")
                if not self._wait_done(page):
                    print("❌ 生成超时或失败")
                    return
                print("✅ 图片生成完成！")
                page.wait_for_timeout(2000)

                if verbose:
                    self._dump_dom(page)

                # ── 4. 逐张下载 ──
                sep()
                print("📌 [4/4] 逐张下载四宫格图片")
                grid = self._find_grid_images(page)
                if not grid:
                    print("❌ 未找到四宫格图片")
                    return

                print(f"   找到 {len(grid)} 张缩略图")
                downloaded = []
                for i, img in enumerate(grid):
                    print(f"\n--- 第 {i+1}/{len(grid)} 张 ---")
                    path = self._download_one(page, img, i, dl_dir, img_dir)
                    if path:
                        downloaded.append(path)

                sep()
                if downloaded:
                    print(f"🎉 完成 {len(downloaded)}/{len(grid)} 张:")
                    for d in downloaded:
                        size = Path(d).stat().st_size
                        print(f"   {d}  ({size:,} bytes)")
                else:
                    print("❌ 未能下载任何图片")

                if verbose:
                    self.report["downloaded"] = downloaded
                    self._save_report()

            finally:
                print("\n🔒 关闭浏览器...")
                browser.close()
                print("✅ 已关闭")

    # ── 子步骤 ──

    def _prepare_dirs(self):
        dl = OUTPUT_DIR / ".downloads"
        dl.mkdir(parents=True, exist_ok=True)
        for f in dl.iterdir():
            try: f.unlink()
            except Exception: pass
        img = OUTPUT_DIR / "images"
        img.mkdir(parents=True, exist_ok=True)
        return dl, img

    def _setup_cdp(self, context, page, dl_dir):
        try:
            cdp = context.new_cdp_session(page)
            cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": str(dl_dir.resolve()),
            })
            print("✅ CDP 下载路径已设置")
        except Exception as e:
            print(f"⚠️  CDP 失败: {e}")

    def _wait_done(self, page, timeout: int = 300) -> bool:
        done = ["已生成", "生成成功"]
        fail = ["无法生成", "生成失败", "违规"]
        t0 = time.time()
        last = 0
        while time.time() - t0 < timeout:
            try:
                body = page.inner_text("body")
                for kw in fail:
                    if kw in body:
                        print(f"   ❌ '{kw}'")
                        return False
                for kw in done:
                    if kw in body:
                        return True
            except Exception:
                pass
            time.sleep(3)
            elapsed = int(time.time() - t0)
            if elapsed - last >= 15:
                print(f"   ...已等待 {elapsed}s")
                last = elapsed
        return False

    # ── 找四宫格图片 ──

    def _find_grid_images(self, page) -> list[dict]:
        """找到生成结果中的 4 张图片缩略图。"""
        page.evaluate("window.scrollTo(0, 200)")
        page.wait_for_timeout(2000)

        imgs = page.evaluate("""() => {
            const found = [], seen = new Set();

            // <img> 标签
            document.querySelectorAll('img').forEach(img => {
                const r = img.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.width < 500 && r.height < 500) {
                    const key = `${Math.round(r.x)}_${Math.round(r.y)}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        found.push({x: r.x, y: r.y, w: r.width, h: r.height,
                                    area: r.width * r.height, tag: 'IMG'});
                    }
                }
            });

            // DIV CSS background-image (豆包可能用这种渲染)
            document.querySelectorAll('div').forEach(div => {
                const r = div.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.width < 500 && r.height < 500) {
                    const bg = window.getComputedStyle(div).backgroundImage;
                    if (!bg || bg === 'none') return;
                    const key = `${Math.round(r.x)}_${Math.round(r.y)}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        found.push({x: r.x, y: r.y, w: r.width, h: r.height,
                                    area: r.width * r.height, tag: 'DIV(bg)'});
                    }
                }
            });

            found.sort((a, b) => b.area - a.area);
            return found.slice(0, 8);
        }""")

        if imgs and len(imgs) > 0:
            deduped = self._dedup_by_position(imgs)
            return deduped[:4]

        print("   ❌ 未找到生成图片")
        return []

    def _dedup_by_position(self, items: list[dict]) -> list[dict]:
        """去除坐标重叠的重复项（IMG 和 DIV(bg) 指向同一张图）。"""
        result = []
        for item in items:
            is_dup = False
            for existing in result:
                # x 和 y 差距都 < 5px 则视为同一位置
                if (abs(item["x"] - existing["x"]) < 5 and
                    abs(item["y"] - existing["y"]) < 5):
                    is_dup = True
                    break
            if not is_dup:
                result.append(item)
        return result

    # ── 下载单张 ──

    def _download_one(self, page, img: dict, idx: int,
                       dl_dir: Path, out_dir: Path) -> str | None:
        """点击缩略图 → 详情页找下载图标 → 下载 → 返回。"""
        img_id = uuid.uuid4().hex[:8]
        before = set(f.name for f in dl_dir.iterdir())
        orig_url = page.url

        # 点击缩略图进入详情
        cx, cy = img["x"] + img["w"] / 2, img["y"] + img["h"] / 2
        print(f"   📍 点击缩略图 ({cx:.0f}, {cy:.0f})")
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        # 找详情页的蓝色下载图标
        dl_coords = self._find_download_icon_in_detail(page)
        if not dl_coords:
            print("   ❌ 未找到详情页下载图标")
            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
            return None

        print(f"   📥 点击下载图标 ({dl_coords['x']:.0f}, {dl_coords['y']:.0f})"
              f" color={dl_coords.get('colorHint','')}")
        page.mouse.click(dl_coords["x"], dl_coords["y"])
        page.wait_for_timeout(500)

        # 轮询文件
        print("   ⏳ 等待下载...")
        result = None
        file_path, _ = self._poll_file(dl_dir, before)
        if file_path:
            result = self._move_to_images(file_path, out_dir, img_id)
            if result:
                print(f"   ✅ {Path(result).name} ({Path(result).stat().st_size:,} bytes)")
        else:
            # fallback: expect_download
            print("   ⚠️  文件系统未捕获，尝试 expect_download...")
            try:
                with page.expect_download(timeout=20000) as dl_info:
                    page.mouse.click(dl_coords["x"], dl_coords["y"])
                download = dl_info.value
                suffix = Path(download.suggested_filename).suffix
                result = str(out_dir / f"doubao_{img_id}{suffix}")
                download.save_as(result)
                print(f"   ✅ expect_download: {Path(result).name}")
            except Exception as e:
                print(f"   ❌ expect_download 也失败: {e}")

        # 返回
        print("   ↩️  返回四宫格...")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        if page.url == orig_url:
            return result
        # 再试
        try:
            page.mouse.click(50, 50)
            page.wait_for_timeout(1000)
        except Exception:
            pass

        return result

    def _find_download_icon_in_detail(self, page) -> dict | None:
        """在详情页找到蓝色下载/保存按钮。

        根据实际 DOM 分析：
          - <button class="... bg-dbx-text-highlight ..." data-dbx-name="button">
          - 内含 SVG 下箭头（下载图标）
          - 在页面顶部 y<200 的工具栏中
          - 文本为空，aria-label 为空，只能靠 CSS class 和 SVG 定位
        """
        coords = page.evaluate("""() => {
            // 策略1: 按 data-dbx-name="button" + bg-dbx-text-highlight 定位
            // 这是豆包专用 class，蓝色高亮按钮
            const all = document.querySelectorAll('[data-dbx-name="button"]');
            for (const el of all) {
                const r = el.getBoundingClientRect();
                if (r.y > 200 || r.width < 10) continue;

                const cls = el.className || '';
                // 只有蓝色按钮有 bg-dbx-text-highlight
                if (cls.includes('bg-dbx-text-highlight') ||
                    cls.includes('bg-dbx-fill-highlight')) {

                    // 确认含下载 SVG（向下箭头）
                    const svg = el.querySelector('svg');
                    const hasDownloadIcon = svg &&
                        (svg.innerHTML.includes('M20.375') ||
                         svg.innerHTML.includes('19.2168'));

                    return {
                        x: r.x + r.width / 2,
                        y: r.y + r.height / 2,
                        w: r.width, h: r.height,
                        colorHint: 'dbx-highlight-blue',
                        label: '保存按钮(蓝色+下载图标)',
                        match: 'data-dbx-name=button + bg-dbx-text-highlight',
                    };
                }
            }

            // 策略2: 找 bg-dbx-text-highlight 类的任意 button
            const btns = document.querySelectorAll('button');
            for (const el of btns) {
                const r = el.getBoundingClientRect();
                if (r.y > 200) continue;
                const cls = el.className || '';
                if (cls.includes('bg-dbx-text-highlight')) {
                    return {
                        x: r.x + r.width / 2,
                        y: r.y + r.height / 2,
                        w: r.width, h: r.height,
                        colorHint: 'dbx-highlight-blue',
                        label: 'bg-dbx-text-highlight button',
                        match: 'button.bg-dbx-text-highlight',
                    };
                }
            }

            // 策略3: 找 y<200 含向下箭头 SVG 的按钮
            for (const el of btns) {
                const r = el.getBoundingClientRect();
                if (r.y > 200 || r.y < 20) continue;
                const svg = el.querySelector('svg');
                if (svg) {
                    const path = svg.querySelector('path[d]');
                    const d = path ? path.getAttribute('d') || '' : '';
                    // 下载图标的特征是向下箭头 + 底部横线
                    if (d.includes('V18') && d.includes('V15') && d.length > 100) {
                        return {
                            x: r.x + r.width / 2,
                            y: r.y + r.height / 2,
                            w: r.width, h: r.height,
                            colorHint: 'download-svg-icon',
                            label: '下载图标按钮(SVG path 匹配)',
                            match: 'svg download arrow',
                        };
                    }
                }
            }

            // 策略4: 兜底 — 所有 y<200 的 button 最后一个
            const allTopBtns = [];
            for (const el of btns) {
                const r = el.getBoundingClientRect();
                if (r.y < 200 && r.y > 20 && r.width > 10) {
                    allTopBtns.push({ cx: r.x + r.width/2, cy: r.y + r.height/2 });
                }
            }
            if (allTopBtns.length > 0) {
                allTopBtns.sort((a, b) => a.cx - b.cx);
                const last = allTopBtns[allTopBtns.length - 1];
                return {
                    x: last.cx, y: last.cy,
                    colorHint: 'fallback-last-top-button',
                    label: `兜底: 顶部第${allTopBtns.length}个按钮`,
                    match: 'last top button',
                };
            }

            return null;
        }""")

        if coords:
            print(f"   ✅ 下载按钮: {coords.get('label','?')} "
                  f"({coords['x']:.0f}, {coords['y']:.0f}) "
                  f"match={coords.get('match','')}")
        return coords

    # ── 文件轮询 ──

    def _poll_file(self, dl_dir: Path, before: set) -> tuple[str | None, int]:
        """轮询直到新文件出现并稳定。返回 (path, size)。"""
        t0 = time.time()
        while time.time() - t0 < 60:
            time.sleep(1)
            try:
                now = set(f.name for f in dl_dir.iterdir() if f.is_file())
                new = now - before
                real = [f for f in new if not f.endswith(".crdownload")]
                if real:
                    newest = max(real, key=lambda n: (dl_dir / n).stat().st_mtime)
                    src = dl_dir / newest
                    if src.stat().st_size > 0:
                        s1 = src.stat().st_size
                        time.sleep(1)
                        if src.exists() and src.stat().st_size == s1:
                            return str(src), s1
            except Exception:
                pass
        return None, 0

    def _move_to_images(self, src: str, out_dir: Path, img_id: str) -> str | None:
        try:
            suffix = Path(src).suffix or ".png"
            dest = str(out_dir / f"doubao_{img_id}{suffix}")
            Path(src).rename(dest)
            return dest
        except Exception:
            return src

    # ── 调试工具 ──

    def _dump_dom(self, page):
        f = Path("data/dom_snapshot.html")
        try:
            html = page.content()
            f.write_text(html, encoding="utf-8")
            print(f"   ✅ DOM 快照: {f} ({len(html):,} 字符)")
        except Exception as e:
            print(f"   ❌ DOM 导出失败: {e}")

    def _save_report(self):
        p = CALIBRATION_OUTPUT.resolve()
        p.write_text(json.dumps(self.report, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"\n📄 报告: {p}")


# ══════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════

def main():
    if not check_prerequisites():
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description="Doubao 图片生成校准工具",
        epilog="""
示例:
  python scripts/calibrate_image.py --check
  python scripts/calibrate_image.py --discover
  python scripts/calibrate_image.py --e2e
  python scripts/calibrate_image.py --e2e --prompt "古代仙侠风格"
        """,
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--e2e", action="store_true")
    parser.add_argument("--prompt", type=str,
                        default="一只可爱的橘猫坐在窗台上，阳光洒落，写实摄影风格")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.check:
        print("✅ 环境 OK")
        return

    if not args.discover and not args.e2e:
        parser.print_help()
        print("\n💡 用 --discover 或 --e2e")
        return

    c = ImageCalibrator(headless=args.headless)
    c.run(prompt=args.prompt, verbose=args.discover)


if __name__ == "__main__":
    main()
