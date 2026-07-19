# Task 1 Report: DB Schema + Repository Methods (v0.7)

## Status: DONE

## Commit

```
7cb134b feat(db): add three_view / multi_view columns and update methods
```

## Files Modified

- `src/aicomic/db/repository.py`

### Step 1 — Migration statements (lines 161–165 in final file)

Added four v0.7 `ALTER TABLE` statements inside `migrate_schema()`:

- `ALTER TABLE appearance_variant ADD COLUMN three_view_prompt TEXT DEFAULT ''`
- `ALTER TABLE appearance_variant ADD COLUMN three_view_image TEXT DEFAULT ''`
- `ALTER TABLE scene_card ADD COLUMN multi_view_prompt TEXT DEFAULT ''`
- `ALTER TABLE scene_card ADD COLUMN multi_view_image TEXT DEFAULT ''`

### Step 2 — `update_scene_card_multi_view_prompt` (lines 347–353)

Inserted after `update_scene_card()`. Accepts `scene_id: int` and `prompt: str`, updates `multi_view_prompt` on the matching `scene_card` row, then commits.

### Step 3 — `update_appearance_variant_three_view_prompt` (lines 404–412)

Inserted after `update_appearance_variant_views()`. Accepts `variant_id: int` and `prompt: str`, updates `three_view_prompt` on the matching `appearance_variant` row, then commits.

### Step 4 — `update_appearance_variant_three_view` (lines 430–438)

Inserted after `update_appearance_variant_image()`. Accepts `variant_id: int` and `file_path: str`, updates `three_view_image` on the matching `appearance_variant` row, then commits.

### Step 5 — `update_scene_card_multi_view` (lines 456–462)

Inserted after `update_scene_card_image()`. Accepts `scene_id: int` and `file_path: str`, updates `multi_view_image` on the matching `scene_card` row, then commits.

## Test Results

Command:

```
/c/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "from src.aicomic.db.repository import Database; from pathlib import Path; db = Database(Path('data/aicomic.db')); db.connect(); db.migrate_schema(); print('OK')"
```

**First run:** `OK`
**Second run (idempotency check):** `OK`

No errors. All four new columns default to `''` as specified. Migrations are idempotent via the existing `try/except sqlite3.OperationalError: pass` pattern.

## Concerns

None. The implementation matches the brief exactly, follows existing code conventions, and all tests pass.

## Self-review notes

- All four new methods follow the naming convention of existing methods (`update_{table}_{column}`).
- All four methods use parameterized binding (`?` placeholders) consistent with the rest of the file.
- None of the new methods introduce validation whitelists — the brief did not specify any (the columns are fixed, not dynamic view names).
- No existing code was modified; only new code was added (41 insertions).
