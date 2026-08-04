"""v0.13 download verification — Shot 1 end-to-end with model switch + network fetch.

Prerequisites:
  1. scripts/login_doubao.py (user must have logged in)
  2. StoryboardAgent v0.13 has run (segments_json populated)

Uses ShotVideoGeneratorAgent._build_video_prompt for correct v0.13 industry format.
"""
import sys, time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from aicomic.db.repository import Database
from aicomic.doubao.browser import DoubaoBrowserClient
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent

db = Database(project_root / "data" / "aicomic.db")
db.connect()
db.migrate_schema()

# ── Get Shot 7 ──
shots = db.get_storyboard_shots(1)
if not shots:
    print("ERROR: No shots found for script_id=1")
    sys.exit(1)
shot = dict(shots[6])  # Shot 7 (0-indexed)
print(f"Shot {shot['shot_num']}: id={shot['id']}  scene_id={shot['scene_id']}  camera={shot.get('camera_movement')}")
print(f"  segments: {len(__import__('json').loads(shot.get('segments_json','[]')))}")

# ── Use agent's prompt builder (reads segments_json correctly) ──
agent = ShotVideoGeneratorAgent(browser_client=None)

ref_images = agent._resolve_reference_images(db, shot)
print(f"\nReference images: {len(ref_images)}")
for ri in ref_images:
    p = Path(ri["path"])
    print(f"  [{ri['kind']}] {p.name} ({p.stat().st_size//1024}KB) — {ri['label']}")

if not ref_images:
    print("ERROR: No reference images (need to run ImageGenerator first?)")
    db.close()
    sys.exit(1)

video_prompt = agent._build_video_prompt(shot, ref_images)
print(f"\n=== Video Prompt ({len(video_prompt)} chars) ===")
print(video_prompt)
print("=" * 60)

# ── Browser ──
print("\nLaunching browser (headless=False — observe download)...")
browser = DoubaoBrowserClient(
    headless=False,
    timeout_sec=600,
    poll_interval_sec=5,
)

try:
    browser.ensure_browser()
    print("[OK] Browser ready")

    ref_paths = [ri["path"] for ri in ref_images]

    print("\n--- Generating video (10s, Seedance 2.0 Fast) ---")
    t0 = time.time()
    result = browser.generate_video_from_images(
        prompt=video_prompt,
        reference_images=ref_paths,
        duration_sec=10.0,
    )
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"RESULT (after {elapsed:.0f}s): success={result.success}")
    if result.success:
        for fp in result.file_paths:
            p = Path(fp)
            if p.exists():
                size_mb = p.stat().st_size / (1024 * 1024)
                print(f"  [EXISTS] {p.name} ({size_mb:.1f} MB)")
            else:
                print(f"  [MISSING] {p.name}")
    else:
        print(f"  error: {result.error}")
        if result.metadata:
            for k, v in result.metadata.items():
                print(f"  metadata.{k}: {str(v)[:300]}")

    # Show recent debug files
    debug_dir = Path("data/debug")
    if debug_dir.exists():
        recent = sorted(debug_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        if recent:
            print(f"\n  Recent debug files:")
            for f in recent:
                print(f"    {f.name} ({f.stat().st_size//1024}KB)")

finally:
    browser.close()
    db.close()
    print("\nDone.")
