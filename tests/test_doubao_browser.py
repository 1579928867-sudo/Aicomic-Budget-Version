"""Tests for DoubaoBrowserClient."""
import json
import tempfile
from pathlib import Path

import pytest

from aicomic.doubao.browser import DoubaoBrowserClient, ImageResult, CookieExpiredError


# ── Cookie file helpers ──

def _make_cookie_file() -> Path:
    """Create a temporary cookie JSON file with valid cookies."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w",
                                      encoding="utf-8")
    json.dump([
        {"name": "sessionid", "value": "test123", "domain": ".doubao.com", "path": "/"},
        {"name": "token", "value": "abc456", "domain": ".doubao.com", "path": "/"},
    ], tmp)
    tmp.close()
    return Path(tmp.name)


def _make_empty_cookie_file() -> Path:
    """Create a temporary empty JSON file."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w",
                                      encoding="utf-8")
    json.dump([], tmp)
    tmp.close()
    return Path(tmp.name)


# ── Tests ──

def test_init_loads_cookies():
    """Constructor should load cookies from a valid JSON file."""
    cookie_path = _make_cookie_file()
    try:
        client = DoubaoBrowserClient(
            cookie_file=cookie_path,
            headless=True,
        )
        assert client._cookies is not None
        assert len(client._cookies) == 2
        assert client._cookies[0]["name"] == "sessionid"
    finally:
        cookie_path.unlink()


def test_init_missing_cookie_file():
    """Missing cookie file should result in empty cookies, no crash."""
    client = DoubaoBrowserClient(
        cookie_file=Path("data/nonexistent_cookies.json"),
        headless=True,
    )
    assert client._cookies == []


def test_init_malformed_cookie_file():
    """Malformed JSON in cookie file should result in empty cookies."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w",
                                      encoding="utf-8")
    tmp.write("not valid json {{{")
    tmp.close()
    cookie_path = Path(tmp.name)
    try:
        client = DoubaoBrowserClient(cookie_file=cookie_path, headless=True)
        assert client._cookies == []
    finally:
        cookie_path.unlink()


def test_default_selectors():
    """Without explicit selectors config, defaults should be populated."""
    client = DoubaoBrowserClient(headless=True)
    assert "image" in client.selectors
    assert "video" in client.selectors
    assert "prompt_input" in client.selectors["image"]
    assert "prompt_input" in client.selectors["video"]


def test_custom_selectors_merge():
    """Custom selectors should override defaults, not replace wholesale."""
    custom = {
        "image": {
            "prompt_input": "textarea#my-input",
        }
    }
    client = DoubaoBrowserClient(headless=True, selectors=custom)
    # Custom value should be used
    assert client.selectors["image"]["prompt_input"] == "textarea#my-input"
    # Non-overridden selector should still have default
    assert "download_btn" in client.selectors["image"]


def test_rate_limit_tracking():
    """Internal rate limit should track last call time."""
    client = DoubaoBrowserClient(headless=True, rate_limit_sec=5)
    assert client._last_call_time == 0.0


def test_close_without_browser():
    """close() should be safe to call before any browser was launched."""
    client = DoubaoBrowserClient(headless=True)
    client.close()  # Should not raise


@pytest.mark.skip(reason="Requires real Doubao cookies and network access")
def test_generate_image_e2e():
    """End-to-end: generate a real image via Doubao browser automation."""
    cookie_path = Path("data/doubao_cookies.json")
    if not cookie_path.exists():
        pytest.skip("Cookie file not found")

    client = DoubaoBrowserClient(
        cookie_file=cookie_path,
        headless=False,  # show browser for debugging
        timeout_sec=600,
    )
    try:
        result = client.generate_image(
            prompt="古代仙侠风格，写实电影感风格，一个侠客站在山巅",
            aspect_ratio="16:9",
        )
        assert result.success is True
        assert result.file_path != ""
        assert Path(result.file_path).exists()
    finally:
        client.close()


@pytest.mark.skip(reason="Requires real Doubao cookies and network access")
def test_generate_video_e2e():
    """End-to-end: generate a real video via Doubao browser automation."""
    cookie_path = Path("data/doubao_cookies.json")
    if not cookie_path.exists():
        pytest.skip("Cookie file not found")

    client = DoubaoBrowserClient(
        cookie_file=cookie_path,
        headless=False,
        timeout_sec=600,
    )
    try:
        result = client.generate_video(
            prompt="古代仙侠风格，一个侠客站在山巅，风吹动衣袂",
            duration_sec=5.0,
        )
        assert result.success is True
        assert result.file_path != ""
        assert Path(result.file_path).exists()
    finally:
        client.close()
