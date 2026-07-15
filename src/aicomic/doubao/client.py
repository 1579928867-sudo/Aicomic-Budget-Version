"""Video generation protocol interface and implementations.

Defines a clean abstraction for AI video generation services.
Currently provides a Mock implementation for pipeline testing;
Doubao and other backends implement the same protocol for production use.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
import time
import uuid


@dataclass
class VideoResult:
    """Result from a video generation call.

    Attributes:
        success: Whether generation succeeded.
        file_path: Path to the generated video file.
        duration_sec: Actual duration of the generated video.
        metadata: Arbitrary metadata from the generator.
        error: Error message if success is False.
    """

    success: bool
    file_path: str
    duration_sec: float
    metadata: dict = field(default_factory=dict)
    error: str | None = None


class VideoGenerator(ABC):
    """Abstract protocol for AI video generation services.

    Implementations should handle API calls or browser automation
    to generate short video clips from text prompts.

    Usage:
        generator = MockVideoGenerator(output_dir=Path("data/videos"))
        result = generator.generate(prompt="...", duration_sec=5.0)
    """

    @abstractmethod
    def generate(self, prompt: str, duration_sec: float) -> VideoResult:
        """Generate a video clip from a text prompt.

        Args:
            prompt: Full video generation prompt (Chinese, production-ready).
            duration_sec: Target duration in seconds.

        Returns:
            VideoResult with success status and output path.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable generator name for logging."""
        ...


class MockVideoGenerator(VideoGenerator):
    """Mock generator for pipeline testing — creates placeholder entries.

    Does NOT produce actual video files. Returns success with a
    synthetic file path so the pipeline can validate end-to-end flow.
    """

    def __init__(self, output_dir: Path = Path("data/videos")):
        self.output_dir = output_dir

    @property
    def name(self) -> str:
        return "mock"

    def generate(self, prompt: str, duration_sec: float) -> VideoResult:
        clip_id = uuid.uuid4().hex[:8]
        file_path = str(self.output_dir / f"clip_{clip_id}.mp4")

        # Simulate generation latency
        time.sleep(0.01)

        return VideoResult(
            success=True,
            file_path=file_path,
            duration_sec=duration_sec,
            metadata={"generator": "mock", "clip_id": clip_id},
        )


class CookieExpiredError(Exception):
    """Raised when Doubao cookies are expired and user needs to re-export."""
    pass


class DoubaoVideoGenerator(VideoGenerator):
    """Doubao (豆包/即梦) video generation via Playwright browser automation.

    Uses cookie-based authentication. User must first export cookies
    from a logged-in browser session to data/doubao_cookies.json.

    Config is read from config/settings.yaml -> doubao section, with
    defaults for all values.
    """

    def __init__(
        self,
        cookie_file: Path = Path("data/doubao_cookies.json"),
        headless: bool = True,
        output_dir: str = "data/videos",
        timeout_sec: int = 300,
        poll_interval_sec: int = 3,
        video_page_url: str = "https://jimeng.jianying.com/ai-tool/video/generate",
        selectors: dict | None = None,
    ):
        self.cookie_file = Path(cookie_file)
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.video_page_url = video_page_url
        self.selectors = selectors or {}

        # Load cookies from file
        self._cookies: list[dict] = []
        self._load_cookies()

        # Lazy browser init
        self._playwright = None
        self._browser = None
        self._context = None

    @property
    def name(self) -> str:
        return "doubao"

    # ── Cookie management ──

    def _load_cookies(self):
        """Load cookies from JSON file."""
        if self.cookie_file.exists():
            try:
                import json
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    self._cookies = json.load(f)
            except Exception:
                self._cookies = []

    # ── Browser lifecycle ──

    def _ensure_browser(self):
        """Lazy-init Playwright browser with injected cookies."""
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
        """Clean up browser and Playwright resources."""
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    # ── Core generate ──

    def generate(self, prompt: str, duration_sec: float) -> VideoResult:
        """Generate a video clip via Doubao browser automation.

        Args:
            prompt: Chinese video generation prompt.
            duration_sec: Target duration in seconds.

        Returns:
            VideoResult with success status and output file path.
        """
        import time
        import uuid

        self.output_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._ensure_browser()
            page = self._context.new_page()

            try:
                # 1. Navigate to video generation page
                page.goto(self.video_page_url, wait_until="domcontentloaded")

                # 2. Check for cookie expiration (redirect to login)
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise CookieExpiredError(
                        "Doubao cookies expired. Please re-export cookies from "
                        "a logged-in browser session to data/doubao_cookies.json"
                    )

                # 3. Fill in prompt
                prompt_selector = self.selectors.get(
                    "prompt_input", "textarea[placeholder*='描述']"
                )
                page.wait_for_selector(prompt_selector, timeout=15000)
                page.fill(prompt_selector, prompt)

                # 4. Click generate button
                btn_selector = self.selectors.get(
                    "generate_button", "button:has-text('生成')"
                )
                page.wait_for_selector(btn_selector, timeout=5000)
                page.click(btn_selector)

                # 5. Poll for completion
                video_url = self._poll_for_result(page)

                if video_url is None:
                    return VideoResult(
                        success=False,
                        file_path="",
                        duration_sec=0,
                        error="Video generation timed out or failed",
                    )

                # 6. Download video
                clip_id = uuid.uuid4().hex[:8]
                output_path = str(self.output_dir / f"doubao_{clip_id}.mp4")

                self._download_video(page, video_url, output_path)

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
                error=f"Doubao generation failed: {e}",
            )

    def _poll_for_result(self, page) -> str | None:
        """Poll for video generation completion. Returns video URL or None."""
        import time

        done_selector = self.selectors.get("status_done", "[class*='success']")
        failed_selector = self.selectors.get("status_failed", "[class*='error']")
        video_selector = self.selectors.get("video_result", "video")
        generating_selector = self.selectors.get(
            "generating_indicator", "[class*='generating']"
        )

        start = time.time()
        while time.time() - start < self.timeout_sec:
            # Check for failure
            if page.query_selector(failed_selector):
                return None

            # Check for completion
            if not page.query_selector(generating_selector):
                # Try to get video element
                video_el = page.query_selector(video_selector)
                if video_el:
                    src = video_el.get_attribute("src")
                    if src:
                        return src

            time.sleep(self.poll_interval_sec)

        return None

    def _download_video(self, page, video_url: str, output_path: str):
        """Download video from URL to local file."""
        import requests

        # Try getting cookies from context for authenticated download
        cookies = {}
        if self._context:
            browser_cookies = self._context.cookies()
            for c in browser_cookies:
                cookies[c["name"]] = c["value"]

        resp = requests.get(video_url, cookies=cookies, timeout=60)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(resp.content)
