# Task 2 Report: Browser Client — Return All Downloaded Images

## Status: DONE

## Commit

```
adbfe2e feat(browser): ImageResult.file_paths — return all downloaded images
```

## Files Modified

- **`src/aicomic/doubao/browser.py`**
  - **Step 1 — `ImageResult` dataclass (line 13-32)**: Added `file_paths: list[str] = field(default_factory=list)` field after `file_path`. Updated docstring to document the new attribute. Used `field(default_factory=list)` to avoid mutable default sharing.
  - **Step 2 — download loop in `generate_image()` (lines 374-391)**: Replaced the old `first_path = None` / `if result_path and first_path is None: first_path = result_path` pattern with a `downloaded = []` list that collects every successful download. On success, returns `file_path=downloaded[0]` (backward compat) and `file_paths=downloaded`. Updated `metadata["total_downloaded"]` to use `len(downloaded)` instead of `len(grid)`.

## Test Results

### Syntax and backward compat verification

Command 1 (new feature: explicit `file_paths`):
```
/c/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c
  "from src.aicomic.doubao.browser import ImageResult;
   r = ImageResult(success=True, file_path='a.png', file_paths=['a.png','b.png']);
   print('OK:', r.file_path, r.file_paths)"
```
Output: `OK: a.png ['a.png', 'b.png']`

Command 2 (backward compat: no `file_paths` arg):
```
/c/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c
  "from src.aicomic.doubao.browser import ImageResult;
   r = ImageResult(success=False, file_path='', error='test');
   print('OK:', r.file_paths)"
```
Output: `OK: []`

### Existing test suite

```
tests/test_doubao_browser.py ........ 7 passed, 2 skipped (e2e)
tests/test_image_generator.py ....... 6 passed
tests/test_db.py .................... 18 passed
Full suite: 77 passed, 3 skipped, 4 failed
```

The 4 failures are pre-existing (missing `three_view_prompt` / `multi_view_prompt` columns in DB) — completely unrelated to this task. All doubao browser tests and image generator tests pass.

## Concerns

None. The change is minimal and backward-compatible. Old code that constructs `ImageResult` without `file_paths` gets an empty list from the default factory.

## Self-Review Notes

- [x] `field(default_factory=list)` used — no mutable default sharing
- [x] `file_path` still set to `downloaded[0]` — all existing callers continue to work
- [x] Metadata `total_downloaded` now reflects actual downloaded count, not grid size
- [x] Error-return paths unchanged (still return `file_path=""`)
- [x] All unit tests pass
