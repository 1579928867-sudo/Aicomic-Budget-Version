"""Tests for DoubaoVideoGenerator (Playwright-based)."""

import json
import tempfile
from pathlib import Path

import pytest

from aicomic.doubao.client import (
    DoubaoVideoGenerator,
    CookieExpiredError,
    VideoResult,
)


# ── Helpers ──

def _make_cookie_file() -> Path:
    """Create a temporary cookie JSON file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump([
        {"name": "sessionid", "value": "test123", "domain": ".bytedance.com", "path": "/"},
    ], tmp)
    tmp.close()
    return Path(tmp.name)


# ── Tests ──

def test_name():
    gen = DoubaoVideoGenerator(
        cookie_file=Path("data/doubao_cookies.json"),
        headless=True,
    )
    assert gen.name == "doubao"


def test_init_loads_cookies():
    cookie_path = _make_cookie_file()
    try:
        gen = DoubaoVideoGenerator(
            cookie_file=cookie_path,
            headless=True,
        )
        assert gen._cookies is not None
        assert len(gen._cookies) == 1
        assert gen._cookies[0]["name"] == "sessionid"
    finally:
        cookie_path.unlink()


def test_init_missing_cookie_file():
    gen = DoubaoVideoGenerator(
        cookie_file=Path("data/nonexistent_cookies.json"),
        headless=True,
    )
    assert gen._cookies == []


def test_generate_returns_failure_without_browser():
    """When Playwright is not available, generate() returns a failure VideoResult."""
    gen = DoubaoVideoGenerator(
        cookie_file=Path("data/doubao_cookies.json"),
        headless=True,
    )
    result = gen.generate("test prompt", 5.0)
    assert result.success is False


def test_doubao_video_generator_accepts_browser_client():
    """Constructor should accept optional browser_client parameter."""
    from aicomic.doubao.browser import DoubaoBrowserClient

    # This test just verifies the constructor signature accepts browser_client
    # without actually launching a browser
    gen = DoubaoVideoGenerator(
        headless=True,
        browser_client=None,  # explicitly None means self-managed
    )
    assert gen.name == "doubao"
    assert gen._owns_browser is True


@pytest.mark.skip(reason="Requires real Doubao cookies and network access")
def test_generate_e2e():
    """End-to-end test with real cookies — run manually only."""
    gen = DoubaoVideoGenerator(
        cookie_file=Path("data/doubao_cookies.json"),
        headless=False,  # show browser for debugging
        timeout_sec=600,
    )
    result = gen.generate("古代仙侠风格，写实电影感风格，一个侠客站在山巅", 5.0)
    assert result.success is True
    assert result.file_path != ""
    assert Path(result.file_path).exists()
