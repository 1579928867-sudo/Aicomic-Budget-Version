"""DoubaoBrowserClient — unified Playwright browser client for image + video generation.

Manages a single Playwright Chromium instance, injects cookies, and provides
generate_image() and generate_video() methods that automate the Doubao web UI.
"""
import sys
import time
import uuid

# Fix GBK encoding errors for emoji characters on Windows Chinese consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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

        # Clean up old debug files (keep last 20)
        self._trim_debug_dir()

    @staticmethod
    def _trim_debug_dir(max_files: int = 20) -> None:
        """Delete oldest files in debug/ directory, keeping at most max_files."""
        debug_dir = Path("data/debug")
        if not debug_dir.is_dir():
            return
        files = sorted(debug_dir.iterdir(), key=lambda p: p.stat().st_mtime)
        excess = len(files) - max_files
        for f in files[:excess]:
            try:
                f.unlink()
            except Exception:
                pass

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

        Includes crash recovery: if the browser or context was closed externally
        (e.g. user manually closed the window), the stale references are cleared
        and a fresh browser is launched.
        """
        if self._browser is not None and self._context is not None:
            try:
                # Health check — accessing .pages fails if context is dead
                self._context.pages
                return
            except Exception:
                print("    [Browser] ⚠ 检测到浏览器已关闭，正在重建...")
                self._browser = None
                self._context = None
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except Exception:
                        pass
                    self._playwright = None

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

    def _has_finished_grid(self, page) -> bool:
        """Check if a finished image grid exists in the page."""
        return page.evaluate("""() => {
            const grid = document.querySelector('[class*="image-box-grid"][data-finished="true"]');
            return grid !== null;
        }""")

    def generate_image(
        self, prompt: str, aspect_ratio: str = "16:9",
        reference_images: list[str] | None = None,
    ) -> ImageResult:
        """Generate an image via Doubao web UI.

        Calibrated flow (2026-07-21):
          1. Navigate to create-image page
          2. Check for login redirect
          3. Optionally select aspect ratio
          4. If reference_images provided, paste them first (for face-consistent
             three-view or other reference-based generation)
          5. Type prompt into contenteditable, click send button
          6. Poll for finished image grid (data-finished="true")
          7. Extract grid image URLs, download via HTTP (requests)
          8. Return all downloaded paths as ImageResult (file_path + file_paths)
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
                page.wait_for_timeout(2000)

                # ── 2. Check login ──
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies to data/doubao_cookies.json"
                    )

                # Grant clipboard permission (must be after nav to doubao.com origin)
                if reference_images:
                    try:
                        self._context.grant_permissions(
                            ["clipboard-read", "clipboard-write"]
                        )
                    except Exception:
                        pass

                # ── 3. Aspect ratio (optional) ──
                sel = self.selectors["image"]
                if aspect_ratio and aspect_ratio != "16:9":
                    self._select_aspect_ratio(page, sel, aspect_ratio)

                # ── 4. Find prompt input ──
                prompt_selector = sel.get("prompt_input", 'div[contenteditable="true"]')
                try:
                    page.wait_for_selector(prompt_selector, timeout=10000)
                except Exception:
                    prompt_selector = 'div[contenteditable="true"]'
                    page.wait_for_selector(prompt_selector, timeout=10000)

                debug_dir = self.output_dir / "debug"
                debug_dir.mkdir(parents=True, exist_ok=True)

                # ── 4b. Paste reference images (optional, for face-consistent three-view) ──
                refs = reference_images or []
                valid_refs = [p for p in refs if Path(p).exists()]
                if valid_refs:
                    self._paste_images_to_input(page, prompt_selector, valid_refs)

                # ── 5. Type prompt, submit, poll ──
                # When reference_images were pasted, DO NOT clear — images are
                # already in the input as attachments. Just click and type.
                # Without reference images: clear the placeholder first.
                page.click(prompt_selector)
                time.sleep(0.3)
                if not valid_refs:
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

    # ── Core: Shot video generation (image-to-video on image page) ──

    def generate_video_from_images(
        self, prompt: str, reference_images: list[str], duration_sec: float = 5.0
    ) -> ImageResult:
        """Generate a video from reference images + prompt via Doubao image page.

        Reuses the text-to-image page (create-image), pasting reference images
        and a "生成视频，Xs，..." prompt. Doubao detects the video prefix and
        switches to its video generation model (Seedance), returning an mp4.

        Download strategy (v0.10):
          1. Register Playwright download listener BEFORE clicking send
          2. Poll for video/player element (not just http-src <video>)
          3. If a download event was captured → save it
          4. Else, find & click a "下载" button → catch download event
          5. Else, extract video blob URL → fetch in-page → base64 → save
          6. Else, try legacy <video src="http://..."> extraction

        Args:
            prompt: Chinese video generation prompt, typically "生成视频，Xs，...".
            reference_images: Local file paths to paste as visual reference.
            duration_sec: Target duration in seconds (for metadata only).

        Returns:
            ImageResult with success status and downloaded mp4 file paths.
        """
        import base64

        self._wait_rate_limit()
        video_dir = self.output_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        vid_id = uuid.uuid4().hex[:8]

        try:
            self.ensure_browser()
            page = self._context.new_page()

            # ── Playwright download listener (must be set BEFORE send) ──
            download_future: list[Any] = []

            def _on_download(download):
                download_future.append(download)

            page.on("download", _on_download)

            try:
                # ── 1. Navigate to image creation page ──
                page.set_default_timeout(self.timeout_sec * 1000)
                page.goto(self.page_urls["image"], wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)

                # ── 2. Check login ──
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies."
                    )

                # ── 2.5 Switch to "视频" tab ──
                # The image page defaults to 图片 (image) tab. We MUST
                # switch to 视频 (video) tab before typing the prompt,
                # or Doubao generates still images. The tab is a
                # Radix UI tabs-trigger button inside a carousel-item.
                # Retry up to 3 times, verifying data-state="active".
                tab_switched = False
                for attempt in range(3):
                    try:
                        # Find the tab button's bounding box, click it
                        # via Playwright (full mouse event sequence), then
                        # verify data-state is "active".
                        box = page.evaluate("""() => {
                            const tabs = document.querySelectorAll(
                                '[data-slot="tabs-trigger"]');
                            for (const t of tabs) {
                                if ((t.textContent || '').trim() === '视频') {
                                    const r = t.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2,
                                            w: r.width, h: r.height};
                                }
                            }
                            return null;
                        }""")
                        if box:
                            page.mouse.click(box["x"], box["y"])
                            page.wait_for_timeout(1500)
                            # Verify: did the tab actually activate?
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
                            if active == "active":
                                print(f"    [Doubao] ✓ 已切换到「视频」tab "
                                      f"(data-state=active)")
                                tab_switched = True
                                break
                            else:
                                print(f"    [Doubao] 「视频」tab state={active}, "
                                      f"重试 ({attempt+1}/3)...")
                                page.wait_for_timeout(1000)
                        else:
                            if attempt < 2:
                                page.wait_for_timeout(1500)
                            else:
                                print(f"    [Doubao] ⚠ 未找到「视频」tab")
                    except Exception as e:
                        if attempt < 2:
                            page.wait_for_timeout(1000)
                        else:
                            print(f"    [Doubao] ⚠ 切换视频tab异常: {e}")

                if not tab_switched:
                    print(f"    [Doubao] ⚠ 无法切换到视频tab，"
                          f"依赖prompt中的'生成视频'关键词兜底")

                # ── 3. Find the actual active input (changes after tab switch) ──
                # After switching to 视频 tab, the image-page input is hidden.
                # Scan for the real input element and record its selector.
                prompt_selector = self._find_video_prompt_input(page)

                # Grant clipboard permission (must be after nav to doubao.com origin)
                try:
                    self._context.grant_permissions(
                        ["clipboard-read", "clipboard-write"]
                    )
                except Exception:
                    pass

                # ── 4. Paste reference images into input ──
                valid_images = [p for p in reference_images if Path(p).exists()]
                paste_ok = True
                if valid_images:
                    attached = self._paste_images_to_input(
                        page, prompt_selector, valid_images
                    )
                    if attached == 0:
                        paste_ok = False
                        # Don't proceed — images didn't attach, typing
                        # prompt and sending will produce wrong results
                        debug_screenshot = str(
                            self.output_dir / "debug"
                            / f"doubao_paste_fail_{vid_id}.png"
                        )
                        try:
                            Path(debug_screenshot).parent.mkdir(
                                parents=True, exist_ok=True
                            )
                            page.screenshot(path=debug_screenshot, full_page=False)
                        except Exception:
                            pass
                        print(
                            f"    [Doubao] ✗ 图片粘贴失败，附件数=0，"
                            f"截图: {debug_screenshot}"
                        )
                else:
                    print(f"    [Doubao] ⚠ 无有效参考图片，继续纯文本生成")

                if valid_images and not paste_ok:
                    return ImageResult(
                        success=False, file_path="",
                        error="Image paste failed — no attachments detected",
                        metadata={"paste_failed": True},
                    )

                # ── 5. Type video prompt AFTER images, clear nothing ──
                page.click(prompt_selector)
                time.sleep(0.3)
                page.keyboard.insert_text(prompt)
                time.sleep(1.5)

                # ── 6. Click send ONCE ──
                send_clicked = self._click_send_button(page)
                if not send_clicked:
                    time.sleep(2)
                    send_clicked = self._click_send_button(page)
                if not send_clicked:
                    page.click(prompt_selector)
                    time.sleep(0.3)
                    page.keyboard.press("Enter")
                time.sleep(2.0)

                # ── 7. Poll for video/player element (broad detection) ──
                start = time.time()
                found_content = False
                content_type = "UNKNOWN"  # Track what was generated: VIDEO, IMAGE, UNKNOWN
                moderation_grace_period = 25  # seconds — our prompt text is still on the page
                while time.time() - start < self.timeout_sec:
                    elapsed = time.time() - start
                    # Check: any video element (including blob-src), player container,
                    # or download button = generation complete
                    has_content = page.evaluate("""() => {
                        // Video element with any src (including blob:)
                        const v = document.querySelector('video');
                        if (v && (v.src || v.querySelector('source'))) return true;
                        // Download button
                        const btns = document.querySelectorAll(
                            'button, [role="button"], a, div[class*="download"]');
                        for (const b of btns) {
                            const t = (b.textContent || '').trim();
                            const aria = (b.getAttribute('aria-label') || '').trim();
                            if (t.includes('下载') || t.includes('Download')
                                || aria.includes('下载') || aria.includes('Download'))
                                return true;
                        }
                        // Player container (Doubao-specific class fragments)
                        const player = document.querySelector(
                            '[class*="video-player"], [class*="player-wrapper"], '
                            + '[class*="seedance"], [class*="Seedance"], '
                            + '[class*="generated-video"]');
                        if (player) return true;
                        return false;
                    }""")
                    if has_content:
                        found_content = True
                        # ── v0.10: Verify this is actually a video, not an image ──
                        # Doubao sometimes misinterprets "生成视频" on the image page
                        # and generates still images instead. Detect this early.
                        content_type = page.evaluate("""() => {
                            const video = document.querySelector('video');
                            const videoSrc = video ? (video.src || '') : '';
                            const player = document.querySelector(
                                '[class*="video-player"], [class*="player-wrapper"], '
                                + '[class*="seedance"], [class*="Seedance"], '
                                + '[class*="generated-video"]');
                            if (videoSrc || player) return 'VIDEO';
                            // Check for image-only: doubao image grid, save-to-kb button
                            const imgs = document.querySelectorAll(
                                'img[src*="doubao"], img[class*="result"], '
                                + 'img[class*="generated"], [class*="image-result"], '
                                + '[class*="gallery"]');
                            const saveBtn = document.querySelector(
                                '[class*="save-to-knowledge"], '
                                + '[class*="knowledge-base"]');
                            if ((imgs.length > 0 || saveBtn) && !videoSrc && !player)
                                return 'IMAGE';
                            return 'UNKNOWN';
                        }""")
                        if content_type == 'IMAGE':
                            print(f"    [Doubao] ⚠ 豆包误解意图：生成了图片而非视频")
                        break

                    # ── Moderation / rejection detection (skip early — our prompt text is still visible) ──
                    if elapsed > moderation_grace_period:
                        body_text = page.inner_text("body")
                        blocked = self._check_moderation_block(body_text)
                        if blocked:
                            # Save debug HTML for post-mortem analysis
                            debug_html = str(
                                self.output_dir / "debug"
                                / f"doubao_moderation_{vid_id}.html"
                            )
                            try:
                                Path(debug_html).parent.mkdir(parents=True, exist_ok=True)
                                with open(debug_html, "w", encoding="utf-8") as f:
                                    f.write(page.content())
                            except Exception:
                                pass
                            return ImageResult(
                                success=False, file_path="",
                                error=blocked["error"],
                                metadata={
                                    "reason": blocked["reason"],
                                    "suggestion": blocked["suggestion"],
                                    "page_text": body_text[:2000],
                                    "debug_html": debug_html,
                                },
                            )

                    if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                        print(f"    [Doubao] 等待视频生成... ({int(elapsed)}s)")

                    time.sleep(self.poll_interval_sec)

                if not found_content:
                    debug_dir = self.output_dir / "debug"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    debug_path = str(debug_dir / f"doubao_video_timeout_{vid_id}.png")
                    page.screenshot(path=debug_path, full_page=False)
                    html_path = str(debug_dir / f"doubao_video_timeout_{vid_id}.html")
                    try:
                        html_content = page.content()
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                    except Exception:
                        pass
                    print(f"    [Doubao] ⚠ 视频超时 ({int(time.time()-start)}s), "
                          f"截图: {debug_path}, HTML: {html_path}")
                    return ImageResult(
                        success=False, file_path="",
                        error="Video generation timed out or failed",
                    )

                # ── v0.10: If Doubao generated an image instead of video ──
                # (even after clicking "视频" tab, the model may still misread
                # intent — return a specific error so caller can retry with
                # stronger prompt wording)
                if found_content and content_type == "IMAGE":
                    debug_screenshot = str(
                        self.output_dir / "debug"
                        / f"doubao_wrong_type_image_{vid_id}.png"
                    )
                    try:
                        Path(debug_screenshot).parent.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=debug_screenshot, full_page=False)
                    except Exception:
                        pass
                    print(
                        f"    [Doubao] ✗ 生成结果为图片而非视频（豆包误解意图），"
                        f"截图: {debug_screenshot}"
                    )
                    return ImageResult(
                        success=False, file_path="",
                        error="Model generated image instead of video — "
                              "intent misinterpreted by Doubao",
                        metadata={
                            "wrong_type": "image",
                            "retry_strategy": "force_video_mode",
                        },
                    )

                # Small wait for DOM to settle after video appears
                time.sleep(2.0)

                # ── 8. Download: strategy cascade ──
                downloaded: list[str] = []

                # 8a. Download already captured by listener (auto-download)
                if download_future:
                    dl = download_future[0]
                    save_path = str(video_dir / f"doubao_{vid_id}.mp4")
                    dl.save_as(save_path)
                    print(f"    [Doubao] ✓ 捕获自动下载 → {Path(save_path).name}")
                    downloaded.append(save_path)

                # 8b. Click "下载" button to trigger download
                if not downloaded:
                    btn_clicked = page.evaluate("""() => {
                        const all = document.querySelectorAll(
                            'button, [role="button"], a, div[class*="download"]');
                        for (const el of all) {
                            const t = (el.textContent || '').trim();
                            const aria = (el.getAttribute('aria-label') || '').trim();
                            if (t.includes('下载') || t.includes('Download')
                                || aria.includes('下载') || aria.includes('Download')) {
                                el.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    if btn_clicked:
                        time.sleep(3.0)
                        if download_future:
                            dl = download_future[0]
                            save_path = str(video_dir / f"doubao_{vid_id}.mp4")
                            dl.save_as(save_path)
                            print(f"    [Doubao] ✓ 点击下载按钮 → {Path(save_path).name}")
                            downloaded.append(save_path)

                # 8c. Extract blob URL and download via in-page fetch
                if not downloaded:
                    blob_data = page.evaluate("""async () => {
                        const v = document.querySelector('video');
                        if (!v) return null;
                        const src = v.src || v.getAttribute('src') || '';
                        if (!src || !src.startsWith('blob:')) return null;
                        try {
                            const resp = await fetch(src);
                            const blob = await resp.blob();
                            const buffer = await blob.arrayBuffer();
                            const bytes = new Uint8Array(buffer);
                            let binary = '';
                            for (let i = 0; i < bytes.length; i++)
                                binary += String.fromCharCode(bytes[i]);
                            return { base64: btoa(binary), size: bytes.length,
                                     type: blob.type };
                        } catch(e) { return {error: e.message}; }
                    }""")
                    if blob_data and blob_data.get("base64"):
                        raw = base64.b64decode(blob_data["base64"])
                        ext = ".mp4"
                        if "webm" in blob_data.get("type", ""):
                            ext = ".webm"
                        save_path = str(video_dir / f"doubao_{vid_id}{ext}")
                        with open(save_path, "wb") as f:
                            f.write(raw)
                        size_mb = len(raw) / (1024 * 1024)
                        print(f"    [Doubao] ✓ blob下载 ({size_mb:.1f}MB) → {Path(save_path).name}")
                        downloaded.append(save_path)
                    elif blob_data and blob_data.get("error"):
                        print(f"    [Doubao] ⚠ blob提取失败: {blob_data['error']}")

                # 8d. Legacy: <video src="http://..."> extraction
                if not downloaded:
                    video_urls = self._find_video_urls(page)
                    # Filter to http(s) only (not blob)
                    http_urls = [u for u in video_urls if u.startswith("http")]
                    for i, vurl in enumerate(http_urls):
                        result_path = self._download_video_url(page, vurl, video_dir, i)
                        if result_path:
                            downloaded.append(result_path)

                if downloaded:
                    return ImageResult(
                        success=True,
                        file_path=downloaded[0],
                        file_paths=downloaded,
                        metadata={"generator": "doubao", "video_id": vid_id,
                                   "duration_sec": duration_sec,
                                   "total_downloaded": len(downloaded)},
                    )
                return ImageResult(
                    success=False, file_path="",
                    error="Failed to download any generated video",
                )

            finally:
                page.close()

        except CookieExpiredError:
            raise
        except Exception as e:
            # Build error message safely (emoji in exception text can fail on GBK)
            try:
                err_msg = str(e)
            except Exception:
                err_msg = repr(e)
            return ImageResult(
                success=False, file_path="",
                error=f"Doubao video-from-images generation failed: {err_msg}",
            )
    @staticmethod
    def _find_video_prompt_input(page) -> str:
        """Find the currently-visible prompt input after tab switch.

        The video tab's input may be a textarea or a contenteditable div.
        Returns a CSS selector string suitable for page.wait_for_selector /
        page.click. Falls back to generic contenteditable div.
        """
        candidates = page.evaluate("""() => {
            // Priority 1: visible textarea with placeholder (video tab)
            const textareas = document.querySelectorAll('textarea');
            for (const t of textareas) {
                if (t.offsetParent !== null) {
                    const ph = t.getAttribute('placeholder') || '';
                    if (ph.includes('描述') || ph.includes('描述')) {
                        return {type: 'textarea', selector: 'textarea[placeholder*="描述"]'};
                    }
                }
            }
            // Priority 2: visible textarea (any)
            for (const t of textareas) {
                if (t.offsetParent !== null) {
                    return {type: 'textarea', selector: 'textarea'};
                }
            }
            // Priority 3: visible contenteditable div (image tab)
            const divs = document.querySelectorAll('div[contenteditable="true"]');
            for (const d of divs) {
                if (d.offsetParent !== null) {
                    return {type: 'contenteditable', selector: 'div[contenteditable="true"]'};
                }
            }
            return null;
        }""") or {}
        selector = candidates.get("selector", 'div[contenteditable="true"]')
        typ = candidates.get("type", "unknown")
        print(f"    [Doubao] 检测到输入框: {selector} (type={typ})")
        # Wait for it
        try:
            page.wait_for_selector(selector, timeout=8000)
        except Exception:
            selector = 'div[contenteditable="true"]'
            page.wait_for_selector(selector, timeout=8000)
        return selector

    def _paste_images_to_input(
        self, page, prompt_selector: str, image_paths: list[str]
    ) -> int:
        """Upload reference images via the hidden file input.

        The video tab has a hidden <input type="file" class="hidden"> near the
        "参考图" label. We use Playwright's set_input_files() to upload all
        images at once (the input supports multiple).

        Returns the number of attached images detected in the DOM after upload.
        """
        import base64

        valid = [p for p in image_paths if Path(p).exists()]
        if not valid:
            print(f"    [Doubao] ⚠ 无有效参考图片")
            return 0

        print(f"    [Doubao] 上传 {len(valid)} 张参考图...")
        for i, img_path in enumerate(valid):
            img_p = Path(img_path)
            size_kb = img_p.stat().st_size // 1024
            print(f"    [Doubao] [{i+1}/{len(valid)}] {img_p.name} ({size_kb}KB)")

        # ── Strategy 1: set_input_files on the hidden file input ──
        abs_paths = [str(Path(p).resolve()) for p in valid]
        try:
            # The video tab's file input: hidden, multiple, accepts images
            page.set_input_files(
                'input[type="file"][accept*=".jpg"]', abs_paths
            )
            print(f"    [Doubao] ✓ set_input_files({len(abs_paths)} files)")
        except Exception as e:
            print(f"    [Doubao] ✗ set_input_files 失败: {e}")
            return 0

        # Wait for upload processing
        time.sleep(3.0)

        # ── Verify: count uploaded reference images in the DOM ──
        # File upload renders as <img> with class*="image-" and blob: src.
        # Doubao's component: <img class="image-Q7dBqW" src="blob:...">
        attachment_count = page.evaluate(f"""() => {{
            const imgs = document.querySelectorAll('img[src]');
            let count = 0;
            for (const img of imgs) {{
                const src = img.getAttribute('src') || '';
                const cls = img.className || '';
                // Doubao renders uploaded ref images with
                // class*="image-" and blob: src
                if (cls.includes('image-') && src.startsWith('blob:'))
                    count++;
            }}
            return count;
        }}""")
        print(f"    [Doubao] 上传后附件数: {attachment_count} "
              f"(期望: {len(valid)})")

        return attachment_count

    @staticmethod
    def _check_moderation_block(body_text: str) -> dict | None:
        """Check page text for Doubao moderation/rejection signals.

        Doubao silently rejects video generation for various reasons. The model
        stops generating and displays a rejection message instead of a video.
        This method detects those messages and returns structured info so the
        caller can adjust the prompt and retry.

        Returns None if no block detected, or a dict with reason + suggestion.
        """
        # ── Keyword → (reason_tag, suggestion) mappings ──
        # IMPORTANT: keep keywords as specific multi-word phrases.
        # Single-word keywords like "面部" or "版权" will false-positive
        # on the prompt text we just typed (e.g. "镜头从面部近景..."
        # and "我有版权"). Grace period handles most cases, but specific
        # keywords reduce the risk window.
        BLOCK_RULES = [
            # Real-face / portrait rejection (most common for character refs)
            ("真实人脸", "真实人脸检测",
             "参考图中检测到真实人脸特征 → 降低写实度"),
            ("真人照片", "真人检测",
             "参考图被判定含真人照片 → 降低写实度"),
            ("面部识别", "面部识别拦截",
             "参考图含可识别面部 → 无需调整，可直接重试"),
            # Copyright / infringement (multi-word to avoid matching "版权" in prompt)
            ("侵犯版权", "版权拦截",
             "prompt 被判定含侵权内容 → 移除具体作品名"),
            ("版权保护", "版权拦截",
             "prompt 被判定含版权内容 → 加'原创角色'声明"),
            # Content policy violations
            ("违反社区规范", "内容违规",
             "prompt 触犯内容政策 → 检查是否含血腥/政治"),
            ("不符合内容规范", "内容不符合规范",
             "prompt 不符合内容规范 → 简化描述"),
            ("无法生成该内容", "内容拒审",
             "豆包拒绝生成 → 缩短prompt，降低细节密度"),
            ("审核不通过", "审核拦截",
             "触发审核 → 移除可能涉暴词汇"),
            # Sensitive imagery
            ("包含裸露", "敏感图像",
             "含敏感图像描述 → 确保所有角色穿着完整"),
            ("包含暴力", "暴力内容",
             "含暴力描述 → 移除打斗/流血词汇"),
            ("包含血腥", "血腥内容",
             "含血腥描述 → 改为抽象表述"),
            # Generic failure
            ("生成失败，请稍后重试", "生成失败",
             "豆包返回生成失败 → 缩短prompt或减少参考图"),
        ]

        body = body_text or ""
        for keyword, reason, suggestion in BLOCK_RULES:
            if keyword in body:
                return {"reason": reason, "suggestion": suggestion,
                        "error": f"[审核拦截: {reason}] {suggestion}"}
        return None

    def _find_video_urls(self, page) -> list[str]:
        """Find generated video URLs on the page.

        Strategy (in order):
          1. <video> elements with http src
          2. <source> children inside <video>
          3. Download links pointing to mp4/mov/webm
          4. Any link/button with "下载" (download) text whose href is a video
          5. Video player component data attributes (Doubao-specific)
        """
        return page.evaluate("""() => {
            const urls = [];
            const addIfVideo = (url) => {
                if (!url || typeof url !== 'string') return;
                const u = url.trim();
                if (!u || u === 'about:blank') return;
                if (u.startsWith('blob:')) {
                    // Blob URLs may be valid but can't download directly — still report
                    urls.push(u);
                    return;
                }
                if (u.startsWith('http')) urls.push(u);
            };

            // 1. <video> elements
            document.querySelectorAll('video').forEach(v => {
                addIfVideo(v.src || v.getAttribute('src'));
                v.querySelectorAll('source').forEach(s => {
                    addIfVideo(s.src || s.getAttribute('src'));
                });
            });

            // 2. Download links with video extensions
            document.querySelectorAll('a[href], a[download]').forEach(a => {
                const href = a.getAttribute('href') || '';
                if (/\\.(mp4|mov|webm|avi)(\\?|$)/i.test(href)) {
                    addIfVideo(href);
                }
            });

            // 3. Buttons/links with "下载" (download) text
            const allNodes = document.querySelectorAll(
                'a, button, div[role="button"], span[role="button"], '
                + '[class*="download"], [class*="video-download"]');
            allNodes.forEach(el => {
                const text = (el.textContent || '').trim();
                const href = (el.getAttribute('href') || '');
                if ((text.includes('下载') || text.includes('Download')) && href) {
                    addIfVideo(href);
                }
                // Also check for video src in data attributes
                ['data-src', 'data-url', 'data-video-url', 'data-video-src'].forEach(attr => {
                    addIfVideo(el.getAttribute(attr));
                });
            });

            // 4. Doubao-specific: video result container
            document.querySelectorAll('[class*="video-result"], [class*="video-player"], '
                + '[class*="generated-video"], [class*="player"], [class*="Seedance"]').forEach(el => {
                el.querySelectorAll('video, source, a[href]').forEach(child => {
                    if (child.tagName === 'SOURCE' || child.tagName === 'VIDEO') {
                        addIfVideo(child.src || child.getAttribute('src'));
                    } else {
                        addIfVideo(child.getAttribute('href'));
                    }
                });
            });

            return [...new Set(urls)];
        }""")

    def _download_video_url(
        self, page, video_url: str, out_dir: Path, index: int
    ) -> str | None:
        """Download a video from URL using browser cookies for auth."""
        import requests

        cookies = {}
        if self._context:
            for c in self._context.cookies():
                cookies[c["name"]] = c["value"]

        try:
            resp = requests.get(video_url, cookies=cookies, timeout=300,
                               headers={"Referer": "https://www.doubao.com/"})
            resp.raise_for_status()

            vid_id = uuid.uuid4().hex[:8]
            ext = ".mp4"
            content_type = resp.headers.get("Content-Type", "")
            if "video/mp4" in content_type:
                ext = ".mp4"
            elif "video/webm" in content_type:
                ext = ".webm"

            output_path = str(out_dir / f"doubao_{vid_id}{ext}")
            with open(output_path, "wb") as f:
                f.write(resp.content)

            size_mb = len(resp.content) / (1024 * 1024)
            print(f"    [Doubao] ✓ 已下载视频 #{index+1} ({size_mb:.1f}MB) → "
                  f"{Path(output_path).name}")
            return output_path

        except Exception as e:
            print(f"    [Doubao] ✗ 视频下载失败 #{index+1}: {e}")
            return None

    # ── Core: Video generation (direct video page, legacy) ──

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
