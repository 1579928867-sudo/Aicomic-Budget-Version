"""Check DB state for video generation test."""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from aicomic.db.repository import Database

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# Scripts
rows = db.conn.execute("SELECT id, chapter_id, status FROM script ORDER BY id").fetchall()
print(f"Scripts ({len(rows)}):")
for r in rows:
    print(f"  id={r['id']} chapter_id={r['chapter_id']} status={r['status']}")

# Shots
rows = db.conn.execute(
    "SELECT id, shot_num, scene_id, status FROM storyboard_shot ORDER BY shot_num"
).fetchall()
print(f"\nShots ({len(rows)}):")
for r in rows:
    print(f"  id={r['id']} shot_num={r['shot_num']} scene_id={r['scene_id']} status={r['status']}")

# Video clips
rows = db.conn.execute(
    "SELECT vc.id, vc.shot_id, ss.shot_num, vc.file_path, vc.status "
    "FROM video_clip vc JOIN storyboard_shot ss ON vc.shot_id = ss.id "
    "ORDER BY ss.shot_num"
).fetchall()
print(f"\nVideo Clips ({len(rows)}):")
for r in rows:
    print(f"  clip_id={r['id']} shot_num={r['shot_num']} path={Path(r['file_path']).name}")

# Agent statuses
rows = db.conn.execute(
    "SELECT agent_name, chapter_id, event, detail FROM task_log "
    "WHERE event='status' ORDER BY agent_name, id DESC"
).fetchall()
print(f"\nAgent Statuses ({len(rows)}):")
import json
for r in rows:
    detail = json.loads(r["detail"])
    print(f"  {r['agent_name']} ch{r['chapter_id']}: {detail.get('status','?')}")

# Scene cards with images
rows = db.conn.execute(
    "SELECT id, name, multi_view_image FROM scene_card WHERE multi_view_image != ''"
).fetchall()
print(f"\nScenes with images ({len(rows)}):")
for r in rows:
    p = Path(r["multi_view_image"])
    exists = p.exists()
    print(f"  id={r['id']} {r['name']}: {p.name} (exists={exists})")

# Character outfits with images
rows = db.conn.execute(
    "SELECT co.id, cc.name, co.tag, co.image_path "
    "FROM character_outfit co JOIN character_card cc ON co.character_id = cc.id "
    "WHERE co.image_path != ''"
).fetchall()
print(f"\nCharacter outfits with images ({len(rows)}):")
for r in rows:
    p = Path(r["image_path"])
    exists = p.exists()
    print(f"  id={r['id']} {r['name']}/{r['tag']}: {p.name} (exists={exists})")

db.close()
