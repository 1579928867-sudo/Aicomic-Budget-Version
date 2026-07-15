# Task 1 Report: DB — add view backfill methods

## Status: DONE

## Changes Made

### `src/aicomic/db/repository.py`
1. **New method `update_appearance_variant_views()`**: Accepts `variant_id`, `front`, `side`, `back` and updates the corresponding columns in the `appearance_variant` table.
2. **Expanded `update_scene_card()` signature**: Added `wide_view=""`, `mid_view=""`, `close_view=""` parameters with empty-string defaults for backward compatibility. The SQL UPDATE now sets all 6 fields and `status = 'done'`.

### `tests/test_db.py`
1. **`test_update_appearance_variant_views`**: Creates an appearance variant, calls the new method, and verifies `front_view`, `side_view`, `back_view` columns are correctly populated.
2. **`test_update_scene_card_with_views`**: Calls `update_scene_card` with all 6 keyword arguments and verifies all columns (including `wide_view`, `mid_view`, `close_view`, `status`) are correctly set.

## Verification
- All 13 DB tests pass (2 new + 11 existing) — no backward compatibility breakage.
- All original callers of `update_scene_card` continue to work since new params have default values.

## Commit
```
cbb2e15 feat: add view-update methods for appearance_variant and scene_card
```

## Follow-up Fix (Bugfix Session)

### Fix 1: `create_video_clip` ignores `duration_sec` (Critical — data loss)
- **Root cause**: The INSERT statement only specified `(shot_id, file_path, status)` and did not include `duration_sec`, silently ignoring the parameter.
- **Fix**: Added `duration_sec` column to the `video_clip` table schema in `init_schema`, added a migration in `migrate_schema` for existing databases, and updated the INSERT in `create_video_clip` to include `duration_sec`.

### Fix 2: `migrate_schema` uses over-broad `except Exception: pass`
- **Root cause**: `migrate_schema` caught all exceptions, masking genuine database errors.
- **Fix**: Changed `except Exception: pass` to `except sqlite3.OperationalError: pass` so only column-already-exists errors are swallowed.

### Verification
All 13 DB tests pass:
```
tests/test_db.py::test_database_connect_and_init PASSED
tests/test_db.py::test_create_and_get_novel PASSED
tests/test_db.py::test_create_and_get_chapter PASSED
tests/test_db.py::test_get_chapter_not_found PASSED
tests/test_db.py::test_save_script_and_storyboard_shots PASSED
tests/test_db.py::test_get_or_create_character PASSED
tests/test_db.py::test_get_or_create_scene PASSED
tests/test_db.py::test_agent_status_lifecycle PASSED
tests/test_db.py::test_task_log PASSED
tests/test_db.py::test_migrate_schema_adds_image_prompt_column PASSED
tests/test_db.py::test_update_appearance_variant_views PASSED
tests/test_db.py::test_update_scene_card_with_views PASSED
tests/test_db.py::test_update_shot_image_prompt PASSED
--- 13 passed in 0.30s ---
```

### Commit
```
fix: insert duration_sec in create_video_clip, narrow migrate_schema exception
```

## Concerns
None.
