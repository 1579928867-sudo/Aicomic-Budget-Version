# Task 5 Report: Image Generator Core Refactor

## What Was Implemented

### `src/aicomic/agents/image_generator.py` (modified, 255 lines)

The file was rewritten from the old per-view generation approach (3 separate calls per entity for front/side/back views) to the new composite-prompt approach (1 call per entity with CLI interactive candidate selection).

**Key changes:**

| Section | Lines | Description |
|---------|-------|-------------|
| Imports + docstring | 1-17 | Replaced `Callable` with `os`, `subprocess`, `sys`, `Path`. Updated docstring. |
| `_process_entity()` | 44-107 | **New method** (replaces `_process_views`). One call per entity. Sends composite prompt to Doubao, handles auto-save (1 candidate) or CLI user selection (multiple candidates), deletes unchosen files. |
| `_user_select_image()` | 109-150 | **New method**. Opens candidates with system viewer (`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux), prompts user, returns chosen path or `None` on cancel. |
| `execute()` | 152-254 | **Rewritten**. Now queries `three_view_prompt` / `multi_view_prompt` columns (not old per-view columns). Iterates entities calling `_process_entity`. Same `AgentResult` shape. |

### `tests/test_image_generator.py` (updated)

Updated to align with the new composite-prompt flow:

| Change | Description |
|--------|-------------|
| `FakeBrowserClient` | Now populates `file_paths=[path]` in returned `ImageResult`. |
| `_setup_full_data` | Sets `three_view_prompt` and `multi_view_prompt` (composite columns) instead of old per-view prompts. |
| `test_execute_success` | Updated assertions: 2 images (1 variant + 1 scene composite), checks `three_view_image` / `multi_view_image` columns. |

### `tests/test_char_designer.py` and `tests/test_scene_designer.py` (fixed)

Both had `_make_db()` calling `init_schema()` but not `migrate_schema()`. Since the new schema columns are added via migrations, this caused `no such column` errors. Added `db.migrate_schema()` call in both files.

## Test Results

### Exact commands and output

```
$ python -m pytest tests/test_image_generator.py -v

============================= test session starts =============================
collected 7 items

tests/test_image_generator.py::test_validate_input_valid PASSED
tests/test_image_generator.py::test_validate_input_missing_script_id PASSED
tests/test_image_generator.py::test_validate_input_missing_chapter_id PASSED
tests/test_image_generator.py::test_execute_success PASSED
tests/test_image_generator.py::test_execute_skips_when_already_done PASSED
tests/test_image_generator.py::test_execute_all_browser_calls_fail PASSED
tests/test_image_generator.py::test_execute_no_variants_no_scenes PASSED
======================= 7 passed in 0.20s =============================
```

Full suite:

```
$ python -m pytest tests/ -v
======================= 81 passed, 3 skipped in 18.83s ========================
```

(3 skipped are e2e browser tests requiring real Doubao credentials.)

## Concerns and Open Questions

1. **Test data alignment**: The original brief stated "existing tests should still pass" but the old tests exercised per-view image generation (3 views/entity), which no longer exists. Test data and assertions were updated to reflect the new composite-prompt flow. This is an expected consequence of the architectural change.

2. **`file_paths` population**: The `FakeBrowserClient` needed to populate `result.file_paths` — previously only `file_path` was set. This matches the real `DoubaoBrowserClient` which does populate `file_paths`.

3. **Schema migration in test helpers**: Two other test files had `_make_db()` without `migrate_schema()`, which caused failures when their agents tried to access the new columns. This was a latent issue exposed by the new columns.

4. **Orchestrator compatibility**: The orchestrator passes `{"chapter_id": ..., "script_id": ...}` unchanged to the image generator — no changes needed there.

## Self-Review Checklist

- [x] `_process_views` method removed entirely
- [x] `_process_entity` replaces it with one-call-per-entity pattern
- [x] `_user_select_image` handles cross-platform image opening
- [x] `execute()` queries new columns (`three_view_prompt`, `multi_view_prompt`)
- [x] Same `AgentResult` shape preserved (`images_generated`, `variants_processed`, `scenes_processed`)
- [x] Syntax verified: `python -c "from ... import ImageGeneratorAgent; print('OK')"` outputs `OK`
- [x] All existing tests pass (81 passed, 3 skipped for e2e)
- [x] Commit made
