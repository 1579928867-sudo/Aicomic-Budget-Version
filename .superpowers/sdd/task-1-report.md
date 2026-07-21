# Task 1 Report: Database schema — character_outfit table + outfit_tag column

## Status: DONE

## Commits

```
316a9afd0aaef44f5739598c22552ec4d6c89d4a feat(db): add character_outfit table + outfit_tag column for v0.9 outfit system
```

## Files Modified

- `src/aicomic/db/repository.py`

### Step 1 — `character_outfit` CREATE TABLE in `init_schema()`

Added after `appearance_variant` block and before `scene_card`:

```sql
CREATE TABLE IF NOT EXISTS character_outfit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL REFERENCES character_card(id),
    tag TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    image_path TEXT DEFAULT '',
    is_default INTEGER DEFAULT 0,
    activation_condition TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(character_id, tag)
);
```

### Step 2 — Migrations in `migrate_schema()`

Appended two v0.9 items to the migrations list:

- `ALTER TABLE storyboard_shot ADD COLUMN outfit_tag TEXT DEFAULT NULL`
- `CREATE TABLE IF NOT EXISTS character_outfit(...)` (idempotent via IF NOT EXISTS)

## Test Verification

**Command:**
```bash
C:/Users/w/AppData/Local/Programs/Python/Python312/python.exe -c "
from pathlib import Path
import sys; sys.path.insert(0, 'src')
from aicomic.db.repository import Database
db = Database(Path('data/aicomic.db'))
db.connect()
db.init_schema()
db.migrate_schema()
tables = db.conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print([t['name'] for t in tables])
cols = [c['name'] for c in db.conn.execute('PRAGMA table_info(storyboard_shot)')]
print('outfit_tag' in cols)
db.close()
"
```

**Output:**
```
['novel', 'sqlite_sequence', 'chapter', 'script', 'storyboard_shot', 'character_card', 'appearance_variant', 'scene_card', 'video_clip', 'final_video', 'task_log', 'character_outfit']
True
```

**Result:** PASS — `character_outfit` in table list, `outfit_tag` column present (`True`).

## Concerns

None. Implementation matches the brief exactly, follows existing code conventions, and verification passes.
