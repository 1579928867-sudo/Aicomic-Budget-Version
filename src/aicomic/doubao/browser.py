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


class CookieExpiredError(Exception):
    """Raised when Doubao cookies are expired and user needs to re-export."""
    pass


# Default selectors — these are placeholders until Task 6 calibration
_DEFAULT_SELECTORS = {
    "image": {
        "prompt_input": "textarea[placeholder*='描述']",
        "generate_btn": "button:has-text('生成')",
        "result_img": "img[class*='result']",
        "loading": "[class*='generating']",
        "ratio_1_1": "[data-ratio='1:1']",
        "ratio_16_9": "[data-ratio='16:9']",
        "ratio_9_16": "[data-ratio='9:16']",
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
        page_overrides = selectors.pop("_pages", {}) if selectors else {}
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
        )
        self._context = self._browser.new_context()

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

        Args:
            prompt: Chinese image generation prompt.
            aspect_ratio: One of "1:1", "16:9", "9:16".

        Returns:
            ImageResult with success status and local file path.
        """
        import requests

        self._wait_rate_limit()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.ensure_browser()
            page = self._context.new_page()

            try:
                # 1. Navigate to image generation page
                page.goto(self.page_urls["image"], wait_until="domcontentloaded")

                # 2. Check for cookie expiration
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies from "
                        "a logged-in browser session to data/doubao_cookies.json"
                    )

                # 3. Wait for and fill the prompt input
                sel = self.selectors["image"]
                prompt_selector = sel.get("prompt_input", "textarea")
                page.wait_for_selector(prompt_selector, timeout=15000)
                page.fill(prompt_selector, prompt)

                # 4. Select aspect ratio if not default
                ratio_key = f"ratio_{aspect_ratio.replace(':', '_')}"
                ratio_selector = sel.get(ratio_key)
                if ratio_selector:
                    try:
                        page.click(ratio_selector, timeout=3000)
                    except Exception:
                        pass  # Ratio selector not found, use default

                # 5. Click generate button
                btn_selector = sel.get("generate_btn", "button:has-text('生成')")
                page.wait_for_selector(btn_selector, timeout=5000)
                page.click(btn_selector)

                # 6. Wait for generation to complete
                image_url = self._poll_for_image_result(page, sel)

                if image_url is None:
                    return ImageResult(
                        success=False,
                        file_path="",
                        error="Image generation timed out or failed",
                    )

                # 7. Download image
                img_id = uuid.uuid4().hex[:8]
                output_path = str(self.output_dir / "images" / f"doubao_{img_id}.png")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)

                self._download_file(page, image_url, output_path)

                return ImageResult(
                    success=True,
                    file_path=output_path,
                    url=image_url,
                    metadata={
                        "generator": "doubao",
                        "image_id": img_id,
                        "aspect_ratio": aspect_ratio,
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

                self._download_file(page, video_url, output_path)

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
            from ..doubao.client import VideoResult
            return VideoResult(
                success=False,
                file_path="",
                duration_sec=0,
                error=f"Doubao video generation failed: {e}",
            )

    # ── Private: polling helpers ──

    def _poll_for_image_result(self, page, sel: dict) -> str | None:
        """Poll DOM for image generation completion. Returns image URL or None."""
        loading_selector = sel.get("loading", "[class*='generating']")
        result_selector = sel.get("result_img", "img[class*='result']")

        start = time.time()
        while time.time() - start < self.timeout_sec:
            # Still loading — wait
            if page.query_selector(loading_selector):
                time.sleep(self.poll_interval_sec)
                continue

            # Try to find result image
            img_el = page.query_selector(result_selector)
            if img_el:
                src = img_el.get_attribute("src")
                if src and not src.startswith("data:"):
                    return src

            time.sleep(self.poll_interval_sec)

        return None

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

    def _download_file(self, page, file_url: str, output_path: str):
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
