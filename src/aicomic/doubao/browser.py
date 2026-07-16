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
        file_path: Local path to the downloaded image file.
        url: Original URL the image was downloaded from.
        metadata: Arbitrary metadata (width, height, aspect_ratio, etc.).
        error: Error message if success is False.
    """

    success: bool
    file_path: str
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

    Manages browser lifecycle (lazy init, reuse, crash recovery), cookie
    injection, and rate limiting. Exposes generate_image() and generate_video()
    as the primary interface.

    Usage:
        client = DoubaoBrowserClient(
            cookie_file=Path("data/doubao_cookies.json"),
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
        cookie_file: Path = Path("data/doubao_cookies.json"),
        headless: bool = True,
        output_dir: str = "data/",
        timeout_sec: int = 300,
        poll_interval_sec: int = 3,
        rate_limit_sec: int = 10,
        selectors: dict | None = None,
    ):
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
        """Lazy-init Playwright browser with injected cookies.

        On first call: launch Chromium, create context, inject cookies.
        On subsequent calls: reuse existing browser/context.
        On crash: auto-restart.
        """
        if self._browser is not None:
            return

        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        # Remove navigator.webdriver flag
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        if self._cookies:
            self._context.add_cookies(self._cookies)

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

    def generate_image(
        self, prompt: str, aspect_ratio: str = "16:9"
    ) -> ImageResult:
        """Generate an image via Doubao web UI.

        Flow:
          1. Navigate to image generation page (logged in via cookies)
          2. Type prompt into the contenteditable div
          3. Press Enter to start generation
          4. Poll status container text for completion / failure
          5. Click download button, intercept browser download

        The download button saves all 3-4 generated images at once.
        Playwright's download interception captures the file and saves it.

        Args:
            prompt: Chinese image generation prompt.
            aspect_ratio: One of "1:1", "16:9", "9:16".

        Returns:
            ImageResult with success status and local file path.
        """
        self._wait_rate_limit()
        img_dir = self.output_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_id = uuid.uuid4().hex[:8]

        try:
            self.ensure_browser()
            page = self._context.new_page()

            try:
                sel = self.selectors["image"]

                # ── 1. Navigate to image generation page ──
                page.set_default_timeout(self.timeout_sec * 1000)
                page.goto(self.page_urls["image"], wait_until="domcontentloaded", timeout=60000)

                # ── 2. Check for cookie expiration ──
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies from "
                        "a logged-in browser session to data/doubao_cookies.json"
                    )

                # ── 3. Optionally select aspect ratio ──
                if aspect_ratio and aspect_ratio != "16:9":
                    self._select_aspect_ratio(page, sel, aspect_ratio)

                # ── 4. Type prompt into contenteditable div ──
                prompt_selector = sel.get("prompt_input", 'div[contenteditable="true"]')
                page.wait_for_selector(prompt_selector, timeout=15000)
                page.click(prompt_selector)  # focus the editor
                time.sleep(0.3)
                page.keyboard.insert_text(prompt)
                time.sleep(0.3)

                # ── 5. Press Enter to start generation ──
                page.keyboard.press("Enter")

                # ── 6. Poll status text for completion ──
                status = self._poll_for_image_result(page, sel)
                if not status:
                    return ImageResult(
                        success=False,
                        file_path="",
                        error="Image generation timed out or failed — no completion status detected",
                    )

                # ── 7. Click download button, intercept browser download ──
                download_selector = sel.get("download_btn")
                if not download_selector:
                    return ImageResult(
                        success=False,
                        file_path="",
                        error="Download button selector not configured",
                    )

                try:
                    page.wait_for_selector(download_selector, timeout=15000)
                except Exception:
                    return ImageResult(
                        success=False,
                        file_path="",
                        error="Download button did not appear — generation may have failed",
                    )

                # Determine file extension from download
                output_path = str(img_dir / f"doubao_{img_id}")
                try:
                    with page.expect_download(timeout=60000) as download_info:
                        page.click(download_selector)
                    download = download_info.value
                    # Preserve original extension
                    suggested = Path(download.suggested_filename)
                    output_path = str(img_dir / f"doubao_{img_id}{suggested.suffix}")
                    download.save_as(output_path)
                except Exception as e:
                    return ImageResult(
                        success=False,
                        file_path="",
                        error=f"Download failed: {e}",
                    )

                return ImageResult(
                    success=True,
                    file_path=output_path,
                    metadata={
                        "generator": "doubao",
                        "image_id": img_id,
                        "aspect_ratio": aspect_ratio,
                        "prompt": prompt,
                    },
                )

            finally:
                page.close()

        except CookieExpiredError:
            raise
        except Exception as e:
            return ImageResult(
                success=False,
                file_path="",
                error=f"Doubao image generation failed: {e}",
            )

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

    # ── Private: polling helpers ──

    def _poll_for_image_result(self, page, sel: dict) -> bool:
        """Poll the status container's text for completion / failure keywords.

        Returns True if generation completed successfully, False if failed,
        loops until timeout then returns False.
        """
        container_selector = sel.get("status_container", "div.container-enLQFx")
        done_keywords = sel.get("status_done_keywords", ["已生成", "生成成功"])
        failed_keywords = sel.get("status_failed_keywords", ["无法生成", "生成失败"])

        start = time.time()
        while time.time() - start < self.timeout_sec:
            try:
                container = page.query_selector(container_selector)
                if container:
                    text = container.inner_text().strip()
                    if text:
                        # Check for failure first
                        for kw in failed_keywords:
                            if kw in text:
                                return False
                        # Check for completion
                        for kw in done_keywords:
                            if kw in text:
                                return True
            except Exception:
                pass

            # Fallback: check entire page body for status keywords
            try:
                body_text = page.inner_text("body")
                for kw in failed_keywords:
                    if kw in body_text:
                        return False
                for kw in done_keywords:
                    if kw in body_text:
                        return True
            except Exception:
                pass

            time.sleep(self.poll_interval_sec)

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
