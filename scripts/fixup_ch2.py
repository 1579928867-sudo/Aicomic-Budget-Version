"""Fix Chapter 2 data issues: merge duplicate characters, reset stuck statuses."""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from aicomic.db.repository import Database

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# ── Issue 1: Merge 小姑妈(id=2) → 萧泠汐(id=3) ──
# 萧泠汐 is her real name, revealed in Ch2. Keep id=3.
print("=== Fixing character duplication ===")

# Copy 小姑妈's outfit image to 萧泠汐 if 萧泠汐 has no image
xgly_outfit = db.conn.execute(
    "SELECT image_path FROM character_outfit WHERE character_id=2 AND tag='默认'"
).fetchone()
xly_outfit = db.conn.execute(
    "SELECT id, image_path, prompt FROM character_outfit WHERE character_id=3 AND tag='默认'"
).fetchone()

if xgly_outfit and xly_outfit:
    if (not xly_outfit["image_path"]) and xgly_outfit["image_path"]:
        db.conn.execute(
            "UPDATE character_outfit SET image_path = ? WHERE id = ?",
            (xgly_outfit["image_path"], xly_outfit["id"]),
        )
        db.conn.commit()
        print(f"  ✅ 复制 小姑妈 的图片到 萧泠汐: {xgly_outfit['image_path']}")

# Update storyboard_shot char_ids: replace '2' with '3' (小姑妈 → 萧泠汐)
shots_updated = db.conn.execute(
    """UPDATE storyboard_shot SET char_ids = REPLACE(char_ids, '2', '3')
       WHERE script_id = 2 AND char_ids LIKE '%2%'"""
).rowcount
db.conn.commit()
print(f"  ✅ {shots_updated} shots: char_ids 小姑妈(id=2) → 萧泠汐(id=3)")

# Update shot_character_outfit: character_id 2 → 3
sco_updated = db.conn.execute(
    "UPDATE shot_character_outfit SET character_id = 3 WHERE character_id = 2"
).rowcount
db.conn.commit()
print(f"  ✅ {sco_updated} shot_character_outfit rows updated")

# Update character_card: rename 小姑妈 to note the merge
db.conn.execute(
    "UPDATE character_card SET name = '小姑妈(已合并→萧泠汐)' WHERE id = 2"
)
db.conn.commit()
print(f"  ✅ Renamed character_card id=2 to mark as merged")

# ── Issue 2: Reset shot-visualizer (it hasn't run yet, but clear any stale state)
db.conn.execute(
    "DELETE FROM task_log WHERE chapter_id=2 AND agent_name='shot-visualizer' AND event='status'"
)
db.conn.commit()
print(f"  ✅ Reset shot-visualizer status for Chapter 2")

# Reset shot-video-generator
db.conn.execute(
    "DELETE FROM task_log WHERE chapter_id=2 AND agent_name='shot-video-generator' AND event='status'"
)
db.conn.commit()
print(f"  ✅ Reset shot-video-generator status for Chapter 2")

# ── Verify ──
print(f"\n=== VERIFICATION ===")
chars = db.conn.execute(
    "SELECT cc.id, cc.name, co.image_path FROM character_card cc LEFT JOIN character_outfit co ON cc.id=co.character_id AND co.tag='默认' ORDER BY cc.id"
).fetchall()
for c in chars:
    img = c["image_path"] or "(no image)"
    print(f"  [{c['id']}] {c['name']} — {img}")

shots = db.conn.execute(
    "SELECT shot_num, char_ids FROM storyboard_shot WHERE script_id=2 ORDER BY shot_num"
).fetchall()
print(f"\n  Storyboard shots (after fix):")
for s in shots:
    print(f"    Shot {s['shot_num']}: chars={s['char_ids']}")

db.close()
print("\nDone. Data fixup complete.")
