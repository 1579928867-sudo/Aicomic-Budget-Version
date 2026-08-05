"""v0.13.2 — Single shot video generation test."""
import sys, time, shutil
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

SHOT_NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 1
SCRIPT_ID = 1

# ── Init DB ──
db = Database(project_root / "data" / "aicomic.db")
db.connect()

# ── Get the shot ──
all_shots = db.get_storyboard_shots(SCRIPT_ID)
shot = None
for s in all_shots:
    if dict(s)["shot_num"] == SHOT_NUM:
        shot = dict(s)
        break

if not shot:
    print(f"ERROR: Shot {SHOT_NUM} not found!")
    db.close()
    sys.exit(1)

# Check for existing clip
existing = db.conn.execute(
    "SELECT vc.id, vc.file_path FROM video_clip vc WHERE vc.shot_id = ?",
    (shot["id"],),
).fetchone()
if existing:
    p = Path(existing["file_path"])
    print(f"Shot {SHOT_NUM} already has clip: {p} (exists={p.exists()})")
    if p.exists():
        print("Skipping (already generated).")
        db.close()
        sys.exit(0)
    else:
        db.conn.execute("DELETE FROM video_clip WHERE shot_id = ?", (shot["id"],))
        db.conn.commit()
        print("Cleaned stale clip record.")

# ── Init agent (without browser, just for prompt/resolution) ──
agent = ShotVideoGeneratorAgent(browser_client=None)

# ── Resolve reference images ──
refs = agent._resolve_reference_images(db, shot)
print(f"Shot {SHOT_NUM} (id={shot['id']}):")
print(f"  Reference images: {len(refs)}")
if not refs:
    print("  ERROR: No reference images!")
    db.close()
    sys.exit(1)

for ri in refs:
    p = Path(ri["path"])
    print(f"    [{ri['kind']}] {ri['label']} — {p.name} ({p.stat().st_size//1024}KB)")

ref_paths = [ri["path"] for ri in refs]

# ── Build video prompt ──
video_prompt = agent._build_video_prompt(shot, refs)
print(f"\n  Video prompt ({len(video_prompt)} chars):")
print(f"  {'─'*50}")
for line in video_prompt.split("\n"):
    print(f"  {line}")
print(f"  {'─'*50}")

# ── Launch browser ──
browser = DoubaoBrowserClient(headless=False, timeout_sec=600, poll_interval_sec=5)

try:
    browser.ensure_browser()
    print("\n[OK] Browser ready, generating video...\n")

    t0 = time.time()
    result = browser.generate_video_from_images(
        prompt=video_prompt,
        reference_images=ref_paths,
        duration_sec=10.0,
    )
    elapsed = time.time() - t0

    if result.success and result.file_paths:
        p = Path(result.file_paths[0])
        size_mb = p.stat().st_size / (1024 * 1024) if p.exists() else 0
        print(f"\n[OK] Video generated in {elapsed:.0f}s: {p.name} ({size_mb:.1f}MB)")

        # Save to DB
        db.create_video_clip(
            shot_id=shot["id"],
            file_path=str(p),
            duration_sec=float(shot.get("duration_sec", 10.0)),
        )

        # Copy to videos dir
        dest = project_root / "data" / "videos" / f"shot_{SHOT_NUM:02d}.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(p), str(dest))
        print(f"[OK] Copied to {dest}")

    else:
        print(f"\n[FAIL] {elapsed:.0f}s: {result.error}")
        meta = result.metadata or {}
        if meta.get("reason"):
            print(f"  reason: {meta['reason'][:200]}")
        if meta.get("page_text"):
            print(f"  page: {meta['page_text'][:300]}")

finally:
    browser.close()

db.close()
print("\nDone.")
