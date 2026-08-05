"""Generate videos for Chapter 2 (PDF), shots 1-3 only. One attempt each.

Usage: py -3 scripts/gen_ch2_videos.py
Pipeline must already be complete (script_id=4 exists with shots).
"""
import os, sys, time, shutil
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import yaml
from aicomic.db.repository import Database
from aicomic.doubao.browser import DoubaoBrowserClient
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent

config = yaml.safe_load(open(project_root / "config" / "settings.yaml", encoding="utf-8"))
dc = config.get("doubao", {})
vc = config.get("video", {})

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# Chapter 4 = PDF run
chapter_id = 4
script_id = 4

print(f"Chapter {chapter_id}, Script {script_id}")
all_shots = db.get_storyboard_shots(script_id)
shots_list = [dict(s) for s in all_shots]
print(f"Total shots: {len(shots_list)}")

target_shots = [s for s in shots_list if s["shot_num"] in (1, 2, 3)]
target_shots.sort(key=lambda s: s["shot_num"])
print(f"Target shots: {[s['shot_num'] for s in target_shots]}")
print()

browser = DoubaoBrowserClient(
    state_file=Path(dc.get("state_file", "data/doubao_state.json")),
    cookie_file=Path(dc.get("cookie_file", "data/doubao_cookies.json")),
    headless=False,
    output_dir=dc.get("output_dir", "data/"),
    timeout_sec=dc.get("timeout_sec", 300),
    poll_interval_sec=dc.get("poll_interval_sec", 3),
    rate_limit_sec=dc.get("rate_limit_sec", 10),
    selectors=dc.get("selectors", {}),
)
pages_cfg = dc.get("pages", {})
if pages_cfg:
    browser.page_urls.update(pages_cfg)

shot_video_gen = ShotVideoGeneratorAgent(
    browser_client=browser,
    duration_sec=float(vc.get("shot_video_duration_sec", 5)),
)

t0_total = time.time()
video_results = {}

for shot in target_shots:
    shot_num = shot["shot_num"]
    shot_id = shot["id"]
    print(f"{'─'*50}")
    print(f"  Shot {shot_num} (id={shot_id})")
    print(f"{'─'*50}")

    # Skip if already exists
    existing = db.conn.execute(
        "SELECT vc.id, vc.file_path FROM video_clip vc WHERE vc.shot_id = ?",
        (shot_id,),
    ).fetchone()
    if existing:
        p = Path(existing["file_path"])
        if p.exists():
            print(f"  Skip: already have {p.name} ({p.stat().st_size//1024}KB)")
            video_results[shot_num] = {"status": "skipped", "file": str(p)}
            continue
        else:
            db.conn.execute("DELETE FROM video_clip WHERE shot_id = ?", (shot_id,))
            db.conn.commit()

    # Resolve reference images
    refs = shot_video_gen._resolve_reference_images(db, shot)
    if not refs:
        print(f"  FAIL: no reference images")
        video_results[shot_num] = {"status": "failed", "error": "no refs"}
        continue

    print(f"  Refs: {len(refs)} images")
    for ri in refs:
        p = Path(ri["path"])
        ok = "OK" if p.exists() else "MISS"
        sz = p.stat().st_size // 1024 if p.exists() else 0
        print(f"    [{ri['kind']}] {ri['label']} ({sz}KB) {ok}")

    # Build prompt
    video_prompt = shot_video_gen._build_video_prompt(shot, refs)
    print(f"  Prompt: {len(video_prompt)} chars")

    # Generate - ONE attempt
    ref_paths = [ri["path"] for ri in refs]
    t0 = time.time()
    try:
        gen_result = browser.generate_video_from_images(
            prompt=video_prompt,
            reference_images=ref_paths,
            duration_sec=10.0,
        )
        elapsed = time.time() - t0

        if gen_result.success and gen_result.file_paths:
            vp = Path(gen_result.file_paths[0])
            mb = vp.stat().st_size / (1024 * 1024) if vp.exists() else 0
            print(f"  OK ({elapsed:.0f}s): {vp.name} ({mb:.1f}MB)")

            db.create_video_clip(
                shot_id=shot_id,
                file_path=str(vp),
                duration_sec=float(shot.get("duration_sec", 10.0)),
            )

            dest = project_root / "data" / "videos" / f"ch2_s{shot_num:02d}.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(vp), str(dest))
            print(f"  Backup: {dest.name}")

            video_results[shot_num] = {
                "status": "success", "file": str(vp), "backup": str(dest),
                "size_mb": round(mb, 1), "elapsed_s": int(elapsed),
            }
        else:
            err = gen_result.error or "unknown"
            reason = (gen_result.metadata or {}).get("reason", "")
            print(f"  FAIL ({elapsed:.0f}s): {err}")
            if reason:
                print(f"    reason: {reason[:200]}")
            video_results[shot_num] = {
                "status": "failed", "error": err, "reason": reason[:200],
                "elapsed_s": int(elapsed),
            }
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR ({elapsed:.0f}s): {e}")
        video_results[shot_num] = {
            "status": "error", "error": str(e), "elapsed_s": int(elapsed),
        }

    # Rate limit
    if shot_num < 3:
        wait = dc.get("rate_limit_sec", 10)
        print(f"  Wait {wait}s...")
        time.sleep(wait)

# Report
print(f"\n{'='*50}")
print(f"Results ({time.time() - t0_total:.0f}s total):")
for sn in [1, 2, 3]:
    vr = video_results.get(sn, {"status": "not_run"})
    ico = {"success": "+", "skipped": "=", "failed": "-", "error": "!", "not_run": "?"}
    detail = ""
    if vr.get("size_mb"):
        detail = f" {vr['size_mb']}MB/{vr.get('elapsed_s','?')}s"
    elif vr.get("error"):
        detail = f" {vr['error'][:80]}"
    print(f"  [{ico.get(vr['status'],'?')}] Shot {sn}: {vr['status']}{detail}")

browser.close()
db.close()
