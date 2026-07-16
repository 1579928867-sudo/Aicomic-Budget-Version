# Task 2 Report: DoubaoBrowserClient

## Status: COMPLETE

### Files Created
- `D:/first_agent/src/aicomic/doubao/browser.py` — full `DoubaoBrowserClient` implementation with `ImageResult`, `CookieExpiredError`, `generate_image()`, `generate_video()`, lifecycle management, rate limiting, and polling helpers
- `D:/first_agent/tests/test_doubao_browser.py` — 7 unit tests + 2 e2e tests (skipped without real cookies)

### Files Modified
- `D:/first_agent/config/settings.yaml` — restructured `doubao` section:
  - Added `rate_limit_sec: 10`
  - Added `pages:` sub-section with `image` and `video` page URLs
  - Restructured `selectors:` into nested `image:` and `video:` groups (keeping existing video selectors with updated naming)
  - Changed `output_dir` from `"data/videos/"` to `"data/"` (browser.py creates `images/` and `videos/` subdirs internally)

### Commit
```
4434539 feat: add DoubaoBrowserClient — unified Playwright browser for image + video generation
```

### Test Results
```
tests/test_doubao_browser.py::test_init_loads_cookies           PASSED
tests/test_doubao_browser.py::test_init_missing_cookie_file     PASSED
tests/test_doubao_browser.py::test_init_malformed_cookie_file   PASSED
tests/test_doubao_browser.py::test_default_selectors            PASSED
tests/test_doubao_browser.py::test_custom_selectors_merge       PASSED
tests/test_doubao_browser.py::test_rate_limit_tracking          PASSED
tests/test_doubao_browser.py::test_close_without_browser        PASSED
tests/test_doubao_client.py  (4/4)                              PASSED
tests/test_video_generator.py (6/6)                             PASSED
                                                        Total: 17 passed
```

### Concerns
1. **Circular import solved**: `generate_video()` uses lazy import (`from ..doubao.client import VideoResult`) inside the method body, avoiding the circular import between `doubao/browser.py` and `doubao/client.py`. The return type annotation uses a forward reference string `-> "VideoResult"`.
2. **Selector naming divergence**: The old `DoubaoVideoGenerator` in `client.py` uses different selector names (`generate_button`, `video_result`, `generating_indicator`) than the new nested structure in `browser.py` (`generate_btn`, `result_video`, `loading`/`status_done`). The old class still works with its old flat selectors since it reads them from its own config; the config now uses the new naming. A later task should refactor `DoubaoVideoGenerator` to either delegate to `DoubaoBrowserClient` or align its own selector reads.
3. **Page URL mismatch**: The old `video_page_url` was `"https://jimeng.jianying.com/ai-tool/video/generate"`, the new `pages.video` is `"https://www.doubao.com/chat/create-video"`. Both are placeholders until Task 6 calibration.

---

## Code Review Fixes (2026-07-16)

### Findings Addressed

| ID | Priority | Finding | Change |
|----|----------|---------|--------|
| H1 | High | `CookieExpiredError` duplicated in both `browser.py` and `client.py` | Moved to `src/aicomic/doubao/__init__.py`; both files now `from . import CookieExpiredError` |
| H2 | High | Missing flat `video_page_url` in config for old `DoubaoVideoGenerator` (backward compat) | Added `video_page_url` at the `doubao` top level in `config/settings.yaml` with backward-compat comment |
| M1 | Medium | `selectors.pop("_pages")` mutates caller's dict | Changed to `(selectors or {}).get("_pages", {})` |
| M2 | Medium | Dead `page` parameter in `_download_file` | Removed `page` param from signature and both call sites |
| M3 | Medium | Duplicate `from ..doubao.client import VideoResult` in `generate_video()` except block | Removed the import from the except block; top-of-method import is sufficient |

### Files Modified
- `D:/first_agent/src/aicomic/doubao/__init__.py` — added `CookieExpiredError`
- `D:/first_agent/src/aicomic/doubao/browser.py` — replaced class with import, fixed M1/M2/M3
- `D:/first_agent/src/aicomic/doubao/client.py` — replaced class with import
- `D:/first_agent/config/settings.yaml` — added flat `video_page_url` for backward compat

### Test Results
```
tests/test_doubao_browser.py (7/7)   PASSED
tests/test_doubao_client.py (4/4)    PASSED
tests/test_video_generator.py (6/6)  PASSED
                             Total: 17 passed
```
