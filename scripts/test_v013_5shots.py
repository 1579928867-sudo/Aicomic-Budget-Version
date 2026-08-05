"""v0.13 — 前5镜头视频生成测试 (每镜头1次生成, 共5次豆包额度)

修复: 允许仅有 segments_json 的镜头也参与视频生成 (不再依赖 image_prompt 关卡)
"""
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

# ── Init DB ──
db = Database(project_root / "data" / "aicomic.db")
db.connect()
db.migrate_schema()

# ── Check for existing clips ──
existing_clips = db.conn.execute(
    "SELECT vc.id, ss.shot_num FROM video_clip vc "
    "JOIN storyboard_shot ss ON vc.shot_id = ss.id ORDER BY ss.shot_num"
).fetchall()
if existing_clips:
    print(f"⚠ 发现 {len(existing_clips)} 个旧 clip，清理中...")
    for c in existing_clips:
        db.conn.execute("DELETE FROM video_clip WHERE id = ?", (c["id"],))
    db.conn.commit()
    print("✓ 已清理旧 clip 记录")

# ── Reset shot-video-generator status (force fresh run) ──
db.conn.execute(
    "DELETE FROM task_log WHERE agent_name='shot-video-generator' AND event='status'"
)
db.conn.commit()
print("✓ 已重置 agent 状态")

# ── Get shots (top 5 with segments only, regardless of image_prompt) ──
all_shots = db.get_storyboard_shots(1)  # script_id=1
shots = [dict(s) for s in all_shots[:5]]

print(f"\n======== 测试范围: 前 {len(shots)} 个镜头 ========")
for s in shots:
    import json
    segs = json.loads(s.get("segments_json", "[]")) if isinstance(s.get("segments_json"), str) else (s.get("segments_json") or [])
    print(f"  Shot {s['shot_num']}: id={s['id']} scene_id={s['scene_id']} segments={len(segs)}")

# ── Init agent (without browser, just for prompt building) ──
agent = ShotVideoGeneratorAgent(browser_client=None)

# ── Resolve reference images for all 5 shots upfront ──
shot_refs = {}
for s in shots:
    refs = agent._resolve_reference_images(db, s)
    shot_refs[s["id"]] = refs
    char_imgs = [ri for ri in refs if ri.get("kind") == "role"]
    scene_imgs = [ri for ri in refs if ri.get("kind") == "scene"]
    print(f"  Shot {s['shot_num']} refs: {len(char_imgs)}角色 + {len(scene_imgs)}场景")
    if not refs:
        print(f"    ⚠ 无参考图! 跳过")
    for ri in refs:
        p = Path(ri["path"])
        print(f"    [{ri['kind']}] {ri['label']} — {p.name} ({p.stat().st_size//1024}KB)")

# ── Check if any shots are invalid ──
valid_shots = [s for s in shots if shot_refs.get(s["id"])]
if not valid_shots:
    print("\n❌ 没有可用的镜头 (所有镜头都缺参考图)")
    db.close()
    sys.exit(1)

print(f"\n======== 开始生成 {len(valid_shots)} 个镜头 ========")

# ── Launch browser ──
browser = DoubaoBrowserClient(
    headless=False,
    timeout_sec=600,
    poll_interval_sec=5,
)

results = []
try:
    browser.ensure_browser()
    print("[OK] Browser ready\n")

    for si, shot in enumerate(valid_shots):
        shot_num = shot["shot_num"]
        shot_id = shot["id"]
        ref_images = shot_refs[shot_id]
        ref_paths = [ri["path"] for ri in ref_images]

        # Build prompt
        video_prompt = agent._build_video_prompt(shot, ref_images)

        print(f"{'─'*60}")
        print(f"  [{si+1}/5] Shot {shot_num} (id={shot_id})")
        print(f"  参考图: {len(ref_paths)} 张")
        print(f"  Prompt: {len(video_prompt)} 字")
        print(f"{'─'*60}")

        # Generate
        t0 = time.time()
        result = browser.generate_video_from_images(
            prompt=video_prompt,
            reference_images=ref_paths,
            duration_sec=10.0,
        )
        elapsed = time.time() - t0

        status = "OK" if result.success else "FAIL"
        file_size = ""
        if result.success and result.file_paths:
            p = Path(result.file_paths[0])
            if p.exists():
                size_mb = p.stat().st_size / (1024 * 1024)
                file_size = f"{size_mb:.1f}MB"
                # Save to DB
                db.create_video_clip(
                    shot_id=shot_id,
                    file_path=str(p),
                    duration_sec=float(shot.get("duration_sec", 10.0)),
                )
                # Copy to videos dir
                dest = project_root / "data" / "videos" / f"shot_{shot_num:02d}.mp4"
                shutil.copy2(str(p), str(dest))
                file_size += f" → {dest.name}"

        error_msg = result.error or ""
        metadata = result.metadata or {}
        reason = metadata.get("reason", "")

        print(f"\n  [{status}] {elapsed:.0f}s {file_size}")
        if error_msg:
            print(f"  error: {error_msg[:300]}")
        if reason:
            print(f"  reason: {reason[:200]}")

        results.append({
            "shot_num": shot_num,
            "shot_id": shot_id,
            "success": result.success,
            "elapsed": elapsed,
            "file_size": file_size,
            "error": error_msg,
            "reason": reason,
        })

        # Brief pause between shots
        if si < len(valid_shots) - 1:
            print(f"\n  等待 5s...")
            time.sleep(5.0)

finally:
    browser.close()

# ── Summary ──
print(f"\n{'='*60}")
print(f"  生成结果汇总")
print(f"{'='*60}")
success_count = sum(1 for r in results if r["success"])
fail_count = len(results) - success_count

for r in results:
    icon = "✅" if r["success"] else "❌"
    print(f"  {icon} Shot {r['shot_num']}: {r['elapsed']:.0f}s {r['file_size']}")
    if not r["success"]:
        print(f"     error: {r['error'][:200]}")
        if r.get("reason"):
            print(f"     reason: {r['reason'][:200]}")

print(f"\n  成功: {success_count}/{len(results)}  |  失败: {fail_count}/{len(results)}")

# ── Check video files ──
video_dir = project_root / "data" / "videos"
existing = sorted(video_dir.glob("*.mp4"))
print(f"\n  videos/ 目录: {len(existing)} 个文件")
for f in existing:
    size_mb = f.stat().st_size / (1024 * 1024)
    print(f"    {f.name} ({size_mb:.1f}MB)")

db.close()
print("\nDone.")
