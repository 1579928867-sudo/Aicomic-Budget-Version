# Task 3 Report: ImageGeneratorAgent

## Status: DONE

### Commits
```
61a3799 feat: add ImageGeneratorAgent — generate real images from view prompts via Doubao
```

### Files Created
- `src/aicomic/agents/image_generator.py` — 219 lines; ImageGeneratorAgent implementing AgentInterface
- `tests/test_image_generator.py` — 243 lines; 7 tests + FakeBrowserClient

### Test Results
```
7 passed in 0.20s
```

| Test | Result |
|------|--------|
| `test_validate_input_valid` | PASS |
| `test_validate_input_missing_script_id` | PASS |
| `test_validate_input_missing_chapter_id` | PASS |
| `test_execute_success` | PASS — 6 images (3 variant views + 3 scene views) |
| `test_execute_skips_when_already_done` | PASS — second run returns `{"status": "skipped"}` |
| `test_execute_all_browser_calls_fail` | PASS — returns `success=False` with error |
| `test_execute_no_variants_no_scenes` | PASS — returns `success=True` with 0 images |

### Implementation Notes

**Agent behavior:**
- Queries `appearance_variant` rows where `front_view != '' AND front_image == ''` and `scene_card` rows where `wide_view != '' AND wide_image == ''`
- Generates images for all 3 views (front/side/back or wide/mid/close) using DoubaoBrowserClient
- Skips empty view prompts gracefully
- Distinguishes between "nothing to generate" (success=True) and "all attempts failed" (success=False)
- Full idempotency via `get_agent_status` / `set_agent_status`

**Key design decision:**
- The brief specified two possible SQL approaches. I chose the simpler one: query `appearance_variant` directly without JOIN on `character_card`, since `character_card` has no `chapter_id` FK and we don't need chapter-scoped filtering here.

### Concerns
- No chapter-scoped filtering for variants/scenes — if multiple chapters share a DB, image generation may reprocess variants already handled by another chapter. The WHERE clause `front_image = ''` (and `wide_image = ''`) prevents redundant generation, so this is safe.
- The `FakeBrowserClient` uses `/tmp/` file paths which work on Linux/macOS but the tests run on Windows; `Path("/tmp/...")` creates a valid path object on Windows (it doesn't validate existence), so the tests pass fine.

## Fix: Critical — extract `_process_views` helper, reduce `execute()` to ~60 lines

**Commit:** `refactor: extract _process_views helper, reduce execute() to ~60 lines, add type hint`

### Changes
- Added `from __future__ import annotations` (needed for forward reference `"DoubaoBrowserClient"`)
- Added `Callable` to typing imports
- Fixed `__init__` type hint: `browser_client: "DoubaoBrowserClient"` and return type `-> None`
- Extracted `_process_views(db, chapter_id, rows, view_names, update_fn, entity_type)` — parameterized helper that handles the nested loop for any entity type
- `execute()` reduced from 184 lines to ~60 lines: loads variants and scenes, delegates to `_process_views` twice, then determines result in a clean if/elif/else block

### File changed
- `src/aicomic/agents/image_generator.py` (221 → 142 lines)

### Test Results
```
7 passed in 0.18s
```

| Test | Result |
|------|--------|
| `test_validate_input_valid` | PASS |
| `test_validate_input_missing_script_id` | PASS |
| `test_validate_input_missing_chapter_id` | PASS |
| `test_execute_success` | PASS |
| `test_execute_skips_when_already_done` | PASS |
| `test_execute_all_browser_calls_fail` | PASS |
| `test_execute_no_variants_no_scenes` | PASS |
