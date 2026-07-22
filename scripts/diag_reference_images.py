"""Diagnostic: verify ShotVideoGenerator can resolve character images for each shot.

Does NOT generate video — just checks reference image resolution logic.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, "src")

from aicomic.db.repository import Database

db = Database(Path("data/aicomic.db"))
db.connect()

# Check script_id=1
script_id = 1
shots = db.get_storyboard_shots(script_id)
print(f"Shots for script_id={script_id}: {len(shots)}")

for s in shots:
    sd = dict(s)
    shot_num = sd["shot_num"]
    char_ids_raw = sd.get("char_ids", "[]")
    try:
        char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
    except (json.JSONDecodeError, TypeError):
        char_ids = []
    scene_id = sd.get("scene_id")
    outfit_tag = sd.get("outfit_tag")

    print(f"\n--- Shot #{shot_num} (id={sd['id']}) ---")
    print(f"  char_ids={char_ids}, scene_id={scene_id}, outfit_tag={outfit_tag}")

    # Resolve character images
    char_imgs = []
    for char_id in char_ids:
        outfit = db.get_character_outfit(char_id, outfit_tag)
        if not outfit:
            outfit = db.get_character_outfit(char_id, None)
        if outfit:
            ip = outfit.get("image_path", "")
            exists = Path(ip).exists() if ip else False
            char_imgs.append({"path": ip, "exists": exists, "char_id": char_id})
            print(f"  char_id={char_id}: path={ip!r}, exists={exists}")
        else:
            print(f"  char_id={char_id}: NO OUTFIT FOUND")

    # Resolve scene image
    scene_img = None
    if scene_id:
        row = db.conn.execute(
            "SELECT multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
            (scene_id,),
        ).fetchone()
        if row:
            sp = row["multi_view_image"]
            exists = Path(sp).exists() if sp else False
            scene_img = {"path": sp, "exists": exists}
            print(f"  scene_id={scene_id}: path={sp!r}, exists={exists}")
        else:
            print(f"  scene_id={scene_id}: NO SCENE IMAGE")

    total_refs = len([i for i in char_imgs if i["exists"]])
    if scene_img and scene_img["exists"]:
        total_refs += 1
    print(f"  → Total valid ref images: {total_refs} (char={len([i for i in char_imgs if i['exists']])}, scene={1 if scene_img and scene_img['exists'] else 0})")

db.close()
