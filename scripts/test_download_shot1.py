"""Generate Shot 1 only — to test download + subtitle embedding."""
import os, sys, json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

# UTF-8 output
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

from aicomic.db.repository import Database
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent
from aicomic.doubao.browser import DoubaoBrowserClient

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# ── Get Shot 1 data ──
shot = dict(db.conn.execute(
    "SELECT * FROM storyboard_shot WHERE script_id=1 AND shot_num=1"
).fetchone())
print(f"Shot 1: id={shot['id']} scene_id={shot['scene_id']}")
print(f"  Camera: {shot['camera_movement']}")
print(f"  Narration: {str(shot['narration'])[:80]}...")
print(f"  Dialogue: {str(shot['dialogue'])[:80]}...")

# ── Check char_ids ──
char_ids_str = shot.get("char_ids", "[]")
print(f"  char_ids: {char_ids_str}")

# ── Launch browser ──
browser = DoubaoBrowserClient(headless=False)
browser.ensure_browser()

# ── Create agent ──
agent = ShotVideoGeneratorAgent(browser_client=browser, interactive=False)

# ── Resolve reference images ──
ref_images = agent._resolve_reference_images(db, shot)
print(f"\nReference images: {len(ref_images)}")
for ri in ref_images:
    print(f"  [{ri['kind']}] {Path(ri['path']).name} — {ri['label']}")

# ── Build prompt ──
prompt = agent._build_video_prompt(shot, ref_images)
print(f"\n=== Video Prompt ({len(prompt)} chars) ===")
print(prompt)

# ── Generate video ──
print("\n--- Generating video ---")
result = browser.generate_video_from_images(
    prompt=prompt,
    reference_images=[ri["path"] for ri in ref_images],
    duration_sec=float(shot.get("duration_sec", 9.0)),
)

print(f"\nResult: success={result.success}")
if result.success:
    print(f"Files: {result.file_paths}")
    for fp in result.file_paths:
        size = Path(fp).stat().st_size if Path(fp).exists() else 0
        print(f"  {fp} ({size/1024:.0f} KB)")
else:
    print(f"Error: {result.error}")
    if result.metadata:
        for k, v in result.metadata.items():
            print(f"  {k}: {str(v)[:200]}")

db.close()
