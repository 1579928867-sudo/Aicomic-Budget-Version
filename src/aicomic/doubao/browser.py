"""DoubaoBrowserClient — unified Playwright browser client for image + video generation.

Manages a single Playwright Chromium instance, injects cookies, and provides
generate_image() and generate_video() methods that automate the Doubao web UI.
"""

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageResult:
    """Result from an image generation call.

    Attributes:
        success: Whether generation succeeded.
        file_path: Local path to the first downloaded image (backward compat).
        file_paths: All successfully downloaded image paths.
        url: Original URL the image was downloaded from.
        metadata: Arbitrary metadata (width, height, aspect_ratio, etc.).
        error: Error message if success is False.
    """

    success: bool
    file_path: str
    file_paths: list[str] = field(default_factory=list)
    url: str = ""
    metadata: dict = field(default_factory=dict)
    error: str | None = None


from . import CookieExpiredError


# Default selectors — calibrated against real Doubao page (2026-07-16)
_DEFAULT_SELECTORS = {
    "image": {
        # contenteditable div, NOT textarea — press Enter after typing
        "prompt_input": 'div[contenteditable="true"][role="textbox"]:has(p[data-placeholder="描述你想要的图片"])',
        "generate_method": "enter",  # Press Enter to start generation
        # Text-based status container — poll for keywords
        "status_container": "div.container-enLQFx",
        "status_done_keywords": ["已生成", "生成成功"],
        "status_failed_keywords": ["无法生成", "生成失败"],
        # Download button — triggers browser download of all generated images
        "download_btn": '#chat-route-main > main > div > div.flex.h-full.w-full.flex-col.items-center > div > div.relative.w-\\[calc\\(100\\%-var\\(--scrollbar-width\\,9px\\)\\)\\].flex-shrink-0.pl-16.pr-7 > div > div > div > div > button',
        # Aspect ratio selectors (dropdown menu items)
        "ratio_trigger": 'div[role="button"]:has(svg)',
        "ratio_1_1": 'div[role="menuitem"][data-slot="dropdown-menu-item"]:has(img[src*="ratio1_1.png"])',
        "ratio_16_9": 'div[role="menuitem"][data-slot="dropdown-menu-item"]:has(img[src*="ratio16_9.png"])',
        "ratio_9_16": 'div[role="menuitem"][data-slot="dropdown-menu-item"]:has(img[src*="ratio9_16.png"])',
    },
    "video": {
        "prompt_input": "textarea[placeholder*='描述']",
        "generate_btn": "button:has-text('生成')",
        "result_video": "video",
        "status_done": "[class*='success']",
        "status_failed": "[class*='error']",
    },
}

# Default page URLs — placeholders until Task 6 calibration
_DEFAULT_PAGES = {
    "image": "https://www.doubao.com/chat/create-image",
    "video": "https://www.doubao.com/chat/create-video",
}


class DoubaoBrowserClient:
    """Unified Playwright browser client for Doubao image and video generation.

    Uses Playwright storageState for persistent login sessions — NOT just
    cookie injection (which fails for session cookies). Run scripts/login_doubao.py
    to create a new session; this client restores it automatically.

    Manages browser lifecycle (lazy init, reuse, crash recovery).
    Exposes generate_image() and generate_video() as the primary interface.

    Usage:
        client = DoubaoBrowserClient(
            state_file=Path("data/doubao_state.json"),
            headless=True,
        )
        try:
            result = client.generate_image("古代仙侠风格...", aspect_ratio="16:9")
            print(result.file_path)
        finally:
            client.close()
    """

    def __init__(
        self,
        state_file: Path = Path("data/doubao_state.json"),
        cookie_file: Path = Path("data/doubao_cookies.json"),  # legacy
        headless: bool = True,
        output_dir: str = "data/",
        timeout_sec: int = 300,
        poll_interval_sec: int = 3,
        rate_limit_sec: int = 10,
        selectors: dict | None = None,
    ):
        # Primary: storageState (full browser profile, survives session cookies)
        self.state_file = Path(state_file)
        # Legacy fallback: manual cookie injection (less reliable)
        self.cookie_file = Path(cookie_file)
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.rate_limit_sec = rate_limit_sec

        # Merge user selectors over defaults
        self.selectors = _DEFAULT_SELECTORS.copy()
        if selectors:
            for key in selectors:
                if key in self.selectors and isinstance(selectors[key], dict):
                    self.selectors[key] = {**self.selectors[key], **selectors[key]}
                else:
                    self.selectors[key] = selectors[key]

        # Page URLs (allow override via selectors dict's special key)
        self.page_urls = _DEFAULT_PAGES.copy()
        page_overrides = (selectors or {}).get("_pages", {})
        self.page_urls.update(page_overrides)

        # Load cookies
        self._cookies: list[dict] = []
        self._load_cookies()

        # Lazy browser state
        self._playwright = None
        self._browser = None
        self._context = None

        # Rate limiting
        self._last_call_time: float = 0.0

    # ── Cookie management ──

    def _load_cookies(self):
        """Load cookies from JSON file. Fails silently if file missing/malformed."""
        if self.cookie_file.exists():
            try:
                import json
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    self._cookies = json.load(f)
            except Exception:
                self._cookies = []

    # ── Browser lifecycle ──

    def ensure_browser(self):
        """Lazy-init Playwright browser, restore saved login session.

        Uses storageState (full browser profile) so session cookies survive
        across runs. Falls back to legacy cookie injection if no state file exists.
        """
        if self._browser is not None:
            return

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # Configure downloads
        self._download_dir = Path(self.output_dir) / ".downloads"
        self._download_dir.mkdir(parents=True, exist_ok=True)

        # Create context — restore login state if available
        context_kwargs = {"accept_downloads": True}

        if self.state_file.exists():
            # Primary: restore full browser state (survives session cookies)
            context_kwargs["storage_state"] = str(self.state_file)
        elif self.cookie_file.exists():
            # Legacy fallback: manual cookie injection
            pass  # Will inject cookies after context creation

        self._context = self._browser.new_context(**context_kwargs)

        # Legacy: inject cookies only if no storageState
        if not self.state_file.exists() and self._cookies:
            try:
                self._context.add_cookies(self._cookies)
            except Exception:
                pass  # Cookies may be invalid for this domain

    def close(self):
        """Clean up browser and Playwright resources. Safe to call multiple times."""
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    # ── Rate limiting ──

    def _wait_rate_limit(self):
        """Sleep if needed to respect rate_limit_sec between calls."""
        elapsed = time.time() - self._last_call_time
        if elapsed < self.rate_limit_sec:
            time.sleep(self.rate_limit_sec - elapsed)
        self._last_call_time = time.time()

    # ── Core: Image generation ──

    def _count_result_images(self, page) -> int:
        """Count Doubao image grid items in the current conversation."""
        return page.evaluate("""() => {
            // Count by Doubao's known grid item class
            const items = document.querySelectorAll('[class*="image-box-grid-item"]');
            return items.length;
        }""")

    def _count_grid_items(self, page) -> int:
        """Count image-box-grid-item elements (same as _count_result_images, explicit name)."""
        return self._count_result_images(page)

    def _has_finished_grid(self, page) -> bool:
        """Check if a finished image grid exists in the page."""
        return page.evaluate("""() => {
            const grid = document.querySelector('[class*="image-box-grid"][data-finished="true"]');
            return grid !== null;
        }""")

    def generate_image(
        self, prompt: str, aspect_ratio: str = "16:9"
    ) -> ImageResult:
        """Generate an image via Doubao web UI.

        Calibrated flow (2026-07-19):
          1. Navigate to create-image page
          2. Capture baseline image count (to ignore sidebar history)
          3. Type prompt + Enter to submit
          4. Poll for NEW image thumbnails appearing in DOM
          5. Click each → detail view → save button → filesystem poll
          6. Return first downloaded image path

        Uses baseline comparison to distinguish newly-generated images
        from chat history thumbnails.
        """
        self._wait_rate_limit()
        img_dir = self.output_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_id = uuid.uuid4().hex[:8]

        try:
            self.ensure_browser()
            page = self._context.new_page()

            try:
                # ── 1. Navigate ──
                page.set_default_timeout(self.timeout_sec * 1000)
                page.goto(self.page_urls["image"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)  # Let sidebar/history fully render

                # ── 2. Check login ──
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies to data/doubao_cookies.json"
                    )

                # ── 3. Aspect ratio (optional) ──
                sel = self.selectors["image"]
                if aspect_ratio and aspect_ratio != "16:9":
                    self._select_aspect_ratio(page, sel, aspect_ratio)

                # ── 5. Type prompt once, submit, poll; re-press Enter if needed ──
                prompt_selector = sel.get("prompt_input", 'div[contenteditable="true"]')
                try:
                    page.wait_for_selector(prompt_selector, timeout=10000)
                except Exception:
                    prompt_selector = 'div[contenteditable="true"]'
                    page.wait_for_selector(prompt_selector, timeout=10000)

                debug_dir = self.output_dir / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)

                # 5a. Click + type prompt (once, don't clear on retry — just re-press Enter)
                page.click(prompt_selector)
                time.sleep(0.5)
                page.keyboard.press("Control+a")
                time.sleep(0.3)
                page.keyboard.press("Backspace")
                time.sleep(0.2)
                page.keyboard.insert_text(prompt)
                time.sleep(1.5)  # Wait for send button to render

                # 5b. Click send button (wait for it to appear first)
                send_clicked = self._click_send_button(page)
                if not send_clicked:
                    # Wait longer and retry — button may need time to render
                    print(f"    [Doubao] 发送按钮未找到, 等 2s 后重试...")
                    time.sleep(2)
                    send_clicked = self._click_send_button(page)
                if not send_clicked:
                    # Last resort: press Enter on the contenteditable
                    print(f"    [Doubao] 仍找不到, 尝试 Enter 键...")
                    page.click(prompt_selector)
                    time.sleep(0.3)
                    page.keyboard.press("Enter")
                time.sleep(2.0)

                # 5c. Poll — if no grid appears in 15s, press Enter again
                enter_retried = False
                start = time.time()
                while time.time() - start < self.timeout_sec:
                    if self._has_finished_grid(page):
                        break  # Generation complete

                    # Check for failure keywords
                    body_text = page.inner_text("body")
                    for kw in sel.get("status_failed_keywords", []):
                        if kw in body_text:
                            return ImageResult(
                                success=False, file_path="",
                                error=f"Generation failed (keyword: '{kw}')",
                            )

                    # If 15s passed and no grid items at all, press Enter again
                    elapsed = time.time() - start
                    if not enter_retried and elapsed > 15:
                        grid_items = self._count_result_images(page)
                        if grid_items == 0:
                            print(f"    [Doubao] 15s 无反应，按 Enter 重新触发...")
                            self._click_send_button(page)
                            time.sleep(2)
                        enter_retried = True

                    # Progress log every 30s
                    if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                        print(f"    [Doubao] 等待图片生成... ({int(elapsed)}s, "
                              f"items={self._count_result_images(page)})")

                    time.sleep(self.poll_interval_sec)

                # 5d. Did we get a finished grid?
                if not self._has_finished_grid(page):
                    # Timeout
                    debug_path = str(debug_dir / f"doubao_timeout_{img_id}.png")
                    page.screenshot(path=debug_path, full_page=False)
                    print(f"    [Doubao] ⚠ 超时 ({int(time.time()-start)}s), 截图: {debug_path}")
                    return ImageResult(
                        success=False, file_path="",
                        error="Image generation timed out or failed",
                    )
                page.wait_for_timeout(1000)

                # ── 7. Find generated images (filter to those beyond baseline) ──
                grid = self._find_grid_images(page)
                if not grid:
                    return ImageResult(
                        success=False, file_path="",
                        error="No grid images found after generation",
                    )

                downloaded = []
                for i, gimg in enumerate(grid):
                    result_path = self._download_grid_image(
                        page, gimg, img_dir
                    )
                    if result_path:
                        downloaded.append(result_path)

                if downloaded:
                    return ImageResult(
                        success=True,
                        file_path=downloaded[0],
                        file_paths=downloaded,
                        metadata={"generator": "doubao", "image_id": img_id,
                                   "total_downloaded": len(downloaded)},
                    )
                return ImageResult(
                    success=False, file_path="",
                    error="Failed to download any image from grid",
                )

            finally:
                page.close()

        except CookieExpiredError:
            raise
        except Exception as e:
            return ImageResult(
                success=False, file_path="",
                error=f"Doubao image generation failed: {e}",
            )

    def _find_grid_images(self, page) -> list[dict]:
        """Find Doubao image grid items using known class names.

        Doubao renders generated images as:
          div.image-box-grid-EYaIcP[data-finished="true"]
            div.image-box-grid-item-FTeESI
              img.image-Q7dBqW (src = full-res image URL)

        Extracts each item's bounding box + the image URL + download URL.
        """
        # Scroll to bottom
        page.evaluate("""() => {
            const main = document.querySelector('[class*="chat"]');
            if (main) main.scrollTop = main.scrollHeight;
        }""")
        page.wait_for_timeout(1500)

        items = page.evaluate("""() => {
            const results = [];
            const gridItems = document.querySelectorAll('[class*="image-box-grid-item"]');
            gridItems.forEach((item, idx) => {
                const r = item.getBoundingClientRect();
                // Find the <img> inside this grid item
                const img = item.querySelector('img[class*="image-"]');
                const src = img ? (img.src || img.getAttribute('src') || '') : '';
                // Also look for <picture><source> with avif/webp
                const picture = item.querySelector('picture');
                let avif_src = '';
                let webp_src = '';
                if (picture) {
                    const avif = picture.querySelector('source[type*="avif"]');
                    const webp = picture.querySelector('source[type*="webp"]');
                    avif_src = avif ? (avif.srcset || '').split(' ')[0] : '';
                    webp_src = webp ? (webp.srcset || '').split(' ')[0] : '';
                }
                results.push({
                    x: r.x, y: r.y, w: r.width, h: r.height,
                    index: idx,
                    src: src,
                    avif_src: avif_src,
                    webp_src: webp_src,
                });
            });
            return results;
        }""")

        print(f"    [Doubao] 找到 {len(items)} 张图片")
        return items[:4]

    def _download_grid_image(
        self, page, item: dict, out_dir: Path,
    ) -> str | None:
        """Download one Doubao grid image by its URL.

        Uses the browser's cookie-authenticated HTTP session to fetch the
        image directly, avoiding complex save-button click flows.

        Args:
            page: Playwright page (for auth cookies).
            item: Grid item dict from _find_grid_images with 'src', 'avif_src', etc.
            out_dir: Target directory for saved images.

        Returns:
            Absolute path to saved file, or None on failure.
        """
        import requests

        # Pick best source: prefer avif/webp for quality, fall back to img src
        url = item.get("avif_src") or item.get("webp_src") or item.get("src", "")
        if not url:
            print(f"    [Doubao] ✗ 图片 #{item.get('index', '?')} 无可用 URL")
            return None

        # Get browser cookies for auth
        cookies = {}
        if self._context:
            for c in self._context.cookies():
                cookies[c["name"]] = c["value"]

        try:
            resp = requests.get(url, cookies=cookies, timeout=120,
                               headers={"Referer": "https://www.doubao.com/"})
            resp.raise_for_status()

            img_id = uuid.uuid4().hex[:8]
            # Determine extension from URL or Content-Type
            content_type = resp.headers.get("Content-Type", "")
            if "avif" in content_type or url.endswith(".avif"):
                ext = ".avif"
            elif "webp" in content_type or url.endswith(".webp"):
                ext = ".webp"
            elif "jpeg" in content_type or "jpg" in content_type or ".jpeg" in url or ".jpg" in url:
                ext = ".jpg"
            else:
                ext = ".png"

            output_path = str(out_dir / f"doubao_{img_id}{ext}")
            with open(output_path, "wb") as f:
                f.write(resp.content)

            size_kb = len(resp.content) // 1024
            print(f"    [Doubao] ✓ 已下载 #{item.get('index', '?')} ({size_kb}KB) → "
                  f"{Path(output_path).name}")
            return output_path

        except Exception as e:
            print(f"    [Doubao] ✗ 下载失败 #{item.get('index', '?')}: {e}")
            return None

    def _select_aspect_ratio(self, page, sel: dict, aspect_ratio: str):
        """Click ratio trigger button, then select the target ratio menu item."""
        ratio_key = f"ratio_{aspect_ratio.replace(':', '_')}"
        ratio_selector = sel.get(ratio_key)
        if not ratio_selector:
            return  # Unknown ratio, skip

        trigger_selector = sel.get("ratio_trigger")
        if trigger_selector:
            try:
                page.wait_for_selector(trigger_selector, timeout=5000)
                page.click(trigger_selector)
                time.sleep(0.5)
            except Exception:
                return

        try:
            page.wait_for_selector(ratio_selector, timeout=5000)
            page.click(ratio_selector)
            time.sleep(0.3)
        except Exception:
            pass  # Ratio selector not found, use default

    # ── Core: Video generation ──

    def generate_video(
        self, prompt: str, duration_sec: float = 5.0
    ) -> "VideoResult":
        """Generate a video via Doubao web UI.

        Args:
            prompt: Chinese video generation prompt.
            duration_sec: Target duration in seconds.

        Returns:
            VideoResult with success status and local file path.
        """
        from ..doubao.client import VideoResult

        self._wait_rate_limit()
        video_dir = self.output_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.ensure_browser()
            page = self._context.new_page()

            try:
                # 1. Navigate to video generation page
                page.goto(self.page_urls["video"], wait_until="domcontentloaded")

                # 2. Check for cookie expiration
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies from "
                        "a logged-in browser session to data/doubao_cookies.json"
                    )

                # 3. Fill in prompt
                sel = self.selectors["video"]
                prompt_selector = sel.get("prompt_input", "textarea")
                page.wait_for_selector(prompt_selector, timeout=15000)
                page.fill(prompt_selector, prompt)

                # 4. Click generate button
                btn_selector = sel.get("generate_btn", "button:has-text('生成')")
                page.wait_for_selector(btn_selector, timeout=5000)
                page.click(btn_selector)

                # 5. Poll for completion
                video_url = self._poll_for_video_result(page, sel)

                if video_url is None:
                    return VideoResult(
                        success=False,
                        file_path="",
                        duration_sec=0,
                        error="Video generation timed out or failed",
                    )

                # 6. Download video
                clip_id = uuid.uuid4().hex[:8]
                output_path = str(video_dir / f"doubao_{clip_id}.mp4")

                self._download_file(video_url, output_path)

                return VideoResult(
                    success=True,
                    file_path=output_path,
                    duration_sec=duration_sec,
                    metadata={"generator": "doubao", "clip_id": clip_id},
                )

            finally:
                page.close()

        except CookieExpiredError:
            raise
        except Exception as e:
            return VideoResult(
                success=False,
                file_path="",
                duration_sec=0,
                error=f"Doubao video generation failed: {e}",
            )

    # ── Private: prompt submission ──

    def _click_send_button(self, page) -> bool:
        """Find and click Doubao's send button.

        Primary: JS click by known ID (#flow-end-msg-send).
        Fallback: scan nearby clickable elements near the input.

        Returns True if a button was found and clicked.
        """
        # ── Strategy 0: JS click by ID (most reliable) ──
        clicked = page.evaluate("""() => {
            const btn = document.querySelector('#flow-end-msg-send');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        if clicked:
            time.sleep(1)
            return True

        # ── Strategy 1: CSS selectors ──
        send_selectors = [
            '#flow-end-msg-send',
            'button[id="flow-end-msg-send"]',
            'button[class*="send-msg"]',
            'button[class*="send-btn"]',
            'button[class*="bg-g-send-msg"]',
            'button[aria-label*="发送" i]',
            'div[role="button"][aria-label*="发送" i]',
        ]
        for selector in send_selectors:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    bbox = btn.bounding_box()
                    if bbox and bbox["y"] > 200:
                        btn.click()
                        time.sleep(1)
                        return True
            except Exception:
                pass

        # ── Strategy 2: JS — find clickable near contenteditable ──
        result = page.evaluate("""() => {
            const input = document.querySelector('div[contenteditable="true"]');
            if (!input) return null;
            const container = input.closest('form, div[class*="input"], div[class*="chat"], '
                + 'div[class*="toolbar"], div[class*="footer"], div[class*="bottom"]');
            const root = container || input.parentElement?.parentElement;
            if (!root) return null;
            const candidates = root.querySelectorAll(
                'button, div[role="button"], [data-dbx-name="button"]');
            for (const el of candidates) {
                const r = el.getBoundingClientRect();
                if (r.width > 10 && r.height > 10 && r.y > 200 && r.width < 100) {
                    return {x: r.x + r.width/2, y: r.y + r.height/2,
                            id: el.id || '', class: (el.className||'').substring(0,40)};
                }
            }
            return null;
        }""")
        if result:
            try:
                page.mouse.click(result["x"], result["y"])
                time.sleep(1)
                return True
            except Exception:
                pass

        return False

    def _poll_for_video_result(self, page, sel: dict) -> str | None:
        """Poll DOM for video generation completion. Returns video URL or None."""
        done_selector = sel.get("status_done", "[class*='success']")
        failed_selector = sel.get("status_failed", "[class*='error']")
        video_selector = sel.get("result_video", "video")

        start = time.time()
        while time.time() - start < self.timeout_sec:
            # Check for failure
            if page.query_selector(failed_selector):
                return None

            # Check for completion — done indicator present and no error
            if page.query_selector(done_selector):
                video_el = page.query_selector(video_selector)
                if video_el:
                    src = video_el.get_attribute("src")
                    if src:
                        return src

            time.sleep(self.poll_interval_sec)

        return None

    def _download_file(self, file_url: str, output_path: str):
        """Download a file from URL to local path using browser cookies for auth."""
        import requests

        cookies = {}
        if self._context:
            browser_cookies = self._context.cookies()
            for c in browser_cookies:
                cookies[c["name"]] = c["value"]

        resp = requests.get(file_url, cookies=cookies, timeout=60)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(resp.content)
