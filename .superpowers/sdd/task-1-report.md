# Task 1 Report: DB — New Image Columns + Backfill Methods

## Status: DONE

## Commits

```
ae1f80b feat: add image path columns and update methods for appearance_variant and scene_card
```

## Files Modified

- `src/aicomic/db/repository.py`
  - `migrate_schema()`: Added 6 ALTER TABLE statements (front_image, side_image, back_image on appearance_variant; wide_image, mid_image, close_image on scene_card) with try/except idempotency guard.
  - New method `update_appearance_variant_image(variant_id, view, file_path)` — updates `{view}_image` column on appearance_variant.
  - New method `update_scene_card_image(scene_id, view, file_path)` — updates `{view}_image` column on scene_card.
- `tests/test_db.py`: Added 3 new tests at the end of file.
  - `test_migrate_schema_adds_image_columns` — verifies 6 new columns exist and migration is idempotent.
  - `test_update_appearance_variant_image` — writes and reads back front/side/back_image.
  - `test_update_scene_card_image` — writes and reads back wide/mid/close_image.

## Test Results

Command:
```
/c/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_db.py -v
```

Output: **17 passed in 0.41s** (14 existing + 3 new). All tests green.

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
tests/test_db.py::test_create_final_video PASSED
tests/test_db.py::test_migrate_schema_adds_image_columns PASSED
tests/test_db.py::test_update_appearance_variant_image PASSED
tests/test_db.py::test_update_scene_card_image PASSED
```

## Concerns

None. All new columns default to `''` as required. Migrations are idempotent via try/except OperationalError. All 17 tests pass.

---

## v0.6 Fix Round: Whitelist validation + dead code cleanup

### Commits

```
[hash] fix: add whitelist guard for view parameter in update_appearance_variant_image and update_scene_card_image
```

### Changes

- `src/aicomic/db/repository.py`
  - Added class-level constants `_ALLOWED_APPEARANCE_IMAGE_VIEWS = {"front", "side", "back"}` and `_ALLOWED_SCENE_IMAGE_VIEWS = {"wide", "mid", "close"}` after `__init__`.
  - `update_appearance_variant_image`: Added `if view not in` guard that raises `ValueError` with a descriptive message listing allowed values.
  - `update_scene_card_image`: Same guard for scene-card views.

- `tests/test_db.py`
  - `test_update_appearance_variant_image`: Removed two unused lines (`novel_id = ...`, `chapter_id = ...`) that were never referenced.
  - Added `test_update_appearance_variant_image_invalid_view` — verifies that passing `"invalid"` as view raises `ValueError`.

### Test Run

Command:
```
/c/Users/w/AppData/Local/Programs/Python/Python312/python.exe -m pytest tests/test_db.py -v
```

Result: **18 passed in 0.46s** (17 existing + 1 new). All green.

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
tests/test_db.py::test_create_final_video PASSED
tests/test_db.py::test_migrate_schema_adds_image_columns PASSED
tests/test_db.py::test_update_appearance_variant_image PASSED
tests/test_db.py::test_update_appearance_variant_image_invalid_view PASSED
tests/test_db.py::test_update_scene_card_image PASSED
```
