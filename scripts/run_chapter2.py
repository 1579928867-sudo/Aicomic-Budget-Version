"""Chapter 2 pipeline driver — runs full pipeline + generates videos for shots 1-3 only.

Usage:
    python scripts/run_chapter2.py              # Full run (pipeline + shots 1-3)
    python scripts/run_chapter2.py --skip-video # Pipeline only, no video generation
"""

import sys
import time
import shutil
from pathlib import Path

# ── Project root ──
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from aicomic.db.repository import Database
from aicomic.bus import AgentBus
from aicomic.orchestrator import Orchestrator
from aicomic.doubao.browser import DoubaoBrowserClient, configure_output_encoding
from aicomic.agents.scriptwriter import ScriptwriterAgent
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.agents.char_designer import CharacterDesignerAgent
from aicomic.agents.scene_designer import SceneDesignerAgent
from aicomic.agents.shot_visualizer import ShotVisualizerAgent
from aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent
from aicomic.agents.outfit_manager import OutfitManagerAgent
from aicomic.llm.deepseek import DeepSeekClient
import yaml

SKIP_VIDEO = "--skip-video" in sys.argv

# ── Config ──
config_path = project_root / "config" / "settings.yaml"
config = {}
if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

# ── API Key ──
import os
api_key = os.environ.get("DEEPSEEK_API_KEY") or config.get("deepseek", {}).get("api_key", "")
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
    sys.exit(1)

# ── Init ──
configure_output_encoding()
db_path = project_root / "data" / "aicomic.db"
db = Database(db_path)
db.connect()
db.init_schema()
db.migrate_schema()

llm = DeepSeekClient(
    api_key=api_key,
    model=config.get("deepseek", {}).get("model", "deepseek-chat"),
    base_url=config.get("deepseek", {}).get("base_url", "https://api.deepseek.com"),
)

# ── Chapter 2 setup ──
novel_title = "逆天邪神"
existing_novel = db.get_novel_by_title(novel_title)
if existing_novel:
    novel_id = existing_novel["id"]
    print(f"📖 Novel 已有 (id={novel_id})")
else:
    novel_id = db.create_novel(title=novel_title, author="")
    print(f"📖 Novel created (id={novel_id})")

# Find or create chapter 2
existing_ch2 = db.get_chapter_by_num(novel_id, 2)
if existing_ch2:
    chapter_id = existing_ch2["id"]
    print(f"📋 Chapter 2 已有 (id={chapter_id})")
    raw_text = existing_ch2.get("raw_text", "")
    if not raw_text.strip():
        ch2_file = project_root / "逆天邪神第2章 情不自禁 .txt"
        raw_text = ch2_file.read_text(encoding="utf-8")
        db.conn.execute(
            "UPDATE chapter SET raw_text = ? WHERE id = ?",
            (raw_text, chapter_id),
        )
        db.conn.commit()
        print("  raw_text 已回填")
else:
    ch2_file = project_root / "逆天邪神第2章 情不自禁 .txt"
    raw_text = ch2_file.read_text(encoding="utf-8")
    chapter_id = db.create_chapter(novel_id, 2, raw_text)
    print(f"📋 Chapter 2 created (id={chapter_id})")

print(f"\n{'='*60}")
print(f"第2章全链路生成 — 仅镜头 1-3")
print(f"  Chapter ID: {chapter_id}")
print(f"  文本长度: {len(raw_text)} 字符")
print(f"  视频生成: {'跳过' if SKIP_VIDEO else '镜头 1-3'}")
print(f"{'='*60}\n")

# ── Register agents ──
scriptwriter = ScriptwriterAgent(llm_client=llm)
storyboard_agent = ScreenwriterAgent(llm_client=llm)
char_designer = CharacterDesignerAgent(llm_client=llm)
scene_designer = SceneDesignerAgent(llm_client=llm)
shot_visualizer = ShotVisualizerAgent(llm_client=llm)
outfit_manager = OutfitManagerAgent(llm_client=llm)

bus = AgentBus()
bus.register(scriptwriter)
bus.register(storyboard_agent)
bus.register(char_designer)
bus.register(scene_designer)
bus.register(shot_visualizer)
bus.register(outfit_manager)

# ── Browser for video generation ──
doubao_cfg = config.get("doubao", {})
browser_client = DoubaoBrowserClient(
    state_file=Path(doubao_cfg.get("state_file", "data/doubao_state.json")),
    cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
    headless=doubao_cfg.get("headless", True),
    output_dir=doubao_cfg.get("output_dir", "data/"),
    timeout_sec=doubao_cfg.get("timeout_sec", 300),
    poll_interval_sec=doubao_cfg.get("poll_interval_sec", 3),
    rate_limit_sec=doubao_cfg.get("rate_limit_sec", 10),
    selectors=doubao_cfg.get("selectors", {}),
)
pages_cfg = doubao_cfg.get("pages", {})
if pages_cfg:
    browser_client.page_urls.update(pages_cfg)

orchestrator = Orchestrator(bus, db)

# ══════════════════════════════════════════════════════════════════════
# Phase 1: Pipeline (Scriptwriter → ShotVisualizer)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'▸'*30}")
print(f"Phase 1: Pipeline")
print(f"{'▸'*30}\n")

t0 = time.time()
result = orchestrator.run_chapter(
    chapter_id=chapter_id,
    raw_text=raw_text,
    with_video=False,
)
pipeline_elapsed = time.time() - t0

if not result.success:
    print(f"\n{'!'*60}")
    print(f"PIPELINE FAILED: {result.error}")
    print(f"{'!'*60}")
    browser_client.close()
    db.close()
    sys.exit(1)

script_id = result.data.get("script_id") if result.data else None
print(f"\n{'─'*60}")
print(f"Phase 1 完成 ({pipeline_elapsed:.0f}s)")
print(f"  Script ID: {script_id}")
print(f"  Characters: {result.data.get('characters', [])}")
print(f"  Scenes: {result.data.get('scenes_list', [])}")
print(f"  Shots created: {result.data.get('shots_created', 0)}")
print(f"  Outfits created: {result.data.get('outfits_created', 0)}")
print(f"  Shots visualized: {result.data.get('shots_visualized', 0)}")
print(f"{'─'*60}")

# ── Collect pipeline results for report ──
pipeline_report = dict(result.data) if result.data else {}

# ══════════════════════════════════════════════════════════════════════
# Phase 2: Video generation for shots 1-3 only
# ══════════════════════════════════════════════════════════════════════
video_results = {}
if SKIP_VIDEO:
    print(f"\n⏭ 跳过视频生成 (--skip-video)")
else:
    if not script_id:
        print("\nERROR: No script_id from pipeline, cannot generate videos")
    else:
        print(f"\n{'▸'*30}")
        print(f"Phase 2: Video generation — shots 1-3 (script_id={script_id})")
        print(f"{'▸'*30}\n")

        all_shots = db.get_storyboard_shots(script_id)
        shots_list = [dict(s) for s in all_shots]
        print(f"  找到 {len(shots_list)} 个镜头\n")

        # Find shots 1, 2, 3
        target_shots = [s for s in shots_list if s["shot_num"] in (1, 2, 3)]
        target_shots.sort(key=lambda s: s["shot_num"])

        if not target_shots:
            print("ERROR: 没有找到 shot 1-3！")
        else:
            # Initialize ShotVideoGenerator with browser
            shot_duration = float(
                config.get("video", {}).get("shot_video_duration_sec", 5)
            )
            shot_video_gen = ShotVideoGeneratorAgent(
                browser_client=browser_client,
                duration_sec=shot_duration,
            )

            for shot in target_shots:
                shot_num = shot["shot_num"]
                shot_id = shot["id"]
                print(f"\n{'─'*50}")
                print(f"  🎬 Shot {shot_num} (id={shot_id})")
                print(f"{'─'*50}")

                # Check existing
                existing = db.conn.execute(
                    "SELECT vc.id, vc.file_path FROM video_clip vc WHERE vc.shot_id = ?",
                    (shot_id,),
                ).fetchone()
                if existing:
                    p = Path(existing["file_path"])
                    if p.exists():
                        print(f"  ✅ 已有视频: {p.name} ({p.stat().st_size//1024}KB)")
                        video_results[shot_num] = {
                            "status": "skipped",
                            "file": str(p),
                            "size_kb": p.stat().st_size // 1024,
                        }
                        continue
                    else:
                        db.conn.execute(
                            "DELETE FROM video_clip WHERE shot_id = ?", (shot_id,)
                        )
                        db.conn.commit()
                        print("  🧹 清理过期clip记录")

                # Resolve reference images
                refs = shot_video_gen._resolve_reference_images(db, shot)
                if not refs:
                    print(f"  ❌ 无参考图！跳过")
                    video_results[shot_num] = {
                        "status": "failed",
                        "error": "No reference images",
                    }
                    continue

                print(f"  参考图: {len(refs)} 张")
                for ri in refs:
                    p = Path(ri["path"])
                    exists = p.exists()
                    size = p.stat().st_size // 1024 if exists else 0
                    print(f"    [{ri['kind']}] {ri['label']} — {p.name} ({size}KB) {'✅' if exists else '❌MISSING'}")

                # Build prompt
                video_prompt = shot_video_gen._build_video_prompt(shot, refs)
                print(f"\n  Prompt ({len(video_prompt)} chars):")
                for line in video_prompt.split("\n")[:5]:
                    print(f"    {line[:120]}")
                if len(video_prompt.split("\n")) > 5:
                    print(f"    ... (+{len(video_prompt.splitlines()) - 5} lines)")

                # Generate video
                ref_paths = [ri["path"] for ri in refs]
                t0_shot = time.time()

                try:
                    gen_result = browser_client.generate_video_from_images(
                        prompt=video_prompt,
                        reference_images=ref_paths,
                        duration_sec=10.0,
                    )
                    elapsed_shot = time.time() - t0_shot

                    if gen_result.success and gen_result.file_paths:
                        vp = Path(gen_result.file_paths[0])
                        size_mb = vp.stat().st_size / (1024 * 1024) if vp.exists() else 0
                        print(f"\n  ✅ 视频生成 ({elapsed_shot:.0f}s): {vp.name} ({size_mb:.1f}MB)")

                        # Save to DB
                        db.create_video_clip(
                            shot_id=shot_id,
                            file_path=str(vp),
                            duration_sec=float(shot.get("duration_sec", 10.0)),
                        )

                        # Copy to videos dir with consistent name
                        dest = project_root / "data" / "videos" / f"ch2_shot_{shot_num:02d}.mp4"
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(vp), str(dest))
                        print(f"  📁 备份到: {dest.name}")

                        video_results[shot_num] = {
                            "status": "success",
                            "file": str(vp),
                            "backup": str(dest),
                            "size_mb": round(size_mb, 1),
                            "elapsed_s": int(elapsed_shot),
                        }
                    else:
                        err = gen_result.error or "未知错误"
                        meta = gen_result.metadata or {}
                        reason = meta.get("reason", "")
                        print(f"\n  ❌ 失败 ({elapsed_shot:.0f}s): {err}")
                        if reason:
                            print(f"     reason: {reason[:200]}")
                        video_results[shot_num] = {
                            "status": "failed",
                            "error": err,
                            "reason": reason[:200],
                            "elapsed_s": int(elapsed_shot),
                        }
                except Exception as e:
                    elapsed_shot = time.time() - t0_shot
                    print(f"\n  ❌ 异常 ({elapsed_shot:.0f}s): {e}")
                    video_results[shot_num] = {
                        "status": "error",
                        "error": str(e),
                        "elapsed_s": int(elapsed_shot),
                    }

                # Rate limit between shots
                if shot_num < 3:
                    wait = doubao_cfg.get("rate_limit_sec", 10)
                    print(f"\n  ⏳ 等待 {wait}s (rate limit)...")
                    time.sleep(wait)

# ══════════════════════════════════════════════════════════════════════
# Final Report
# ══════════════════════════════════════════════════════════════════════
print(f"\n\n{'='*60}")
print(f"📊 第 2 章生成报告")
print(f"{'='*60}")
print(f"\n## Phase 1: Pipeline")
print(f"  Status: ✅ success ({pipeline_elapsed:.0f}s)")
print(f"  Script ID: {script_id}")
print(f"  Characters: {pipeline_report.get('characters', [])}")
print(f"  Scenes: {pipeline_report.get('scenes_list', [])}")
print(f"  Beats: {pipeline_report.get('beat_count', 0)}")
print(f"  Shots (合并后): {pipeline_report.get('shots_created', 0)}")
print(f"  Outfits created: {pipeline_report.get('outfits_created', 0)}")
print(f"  Shots visualized: {pipeline_report.get('shots_visualized', 0)}")

if not SKIP_VIDEO:
    print(f"\n## Phase 2: Video Generation")
    for sn in [1, 2, 3]:
        vr = video_results.get(sn, {"status": "not_run"})
        status_icon = {"success": "✅", "skipped": "⏭️", "failed": "❌", "error": "💥", "not_run": "⬜"}
        icon = status_icon.get(vr["status"], "❓")
        detail = ""
        if vr["status"] == "success":
            detail = f" — {vr.get('size_mb', '?')}MB in {vr.get('elapsed_s', '?')}s"
        elif vr["status"] == "failed":
            detail = f" — {vr.get('error', '?')[:80]}"
        elif vr["status"] == "skipped":
            detail = f" — {vr.get('file', '?')} ({vr.get('size_kb', '?')}KB)"
        print(f"  {icon} Shot {sn}: {vr['status']}{detail}")
else:
    print(f"\n## Phase 2: Video Generation — ⏭️ skipped")

# ── DB state verification ──
print(f"\n## DB Verification")
# Characters
chars = db.conn.execute("SELECT id, name FROM character_card ORDER BY id").fetchall()
print(f"  Characters in DB: {len(chars)}")
for c in chars:
    print(f"    [{c['id']}] {c['name']}")

# Scenes
scenes = db.conn.execute("SELECT id, name FROM scene_card ORDER BY id").fetchall()
print(f"  Scenes in DB: {len(scenes)}")
new_scenes = [s for s in scenes if s["id"] > 12]
if new_scenes:
    print(f"  🆕 New scenes (Ch2):")
    for s in new_scenes:
        print(f"    [{s['id']}] {s['name']}")
else:
    print(f"  (No new scenes added for Ch2)")

# Character outfits with images
outfits = db.conn.execute(
    "SELECT co.id, cc.name, co.tag, co.image_path FROM character_outfit co "
    "JOIN character_card cc ON co.character_id = cc.id ORDER BY co.id"
).fetchall()
print(f"  Character outfits: {len(outfits)}")
for o in outfits:
    img_status = "✅" if o["image_path"] and Path(o["image_path"]).exists() else "⬜"
    print(f"    [{o['id']}] {o['name']} / {o['tag']} {img_status} {o['image_path'] or '(no image)'}")

# Storyboard shots for ch2
if script_id:
    shots = db.conn.execute(
        "SELECT shot_num, narration, char_ids FROM storyboard_shot WHERE script_id=? ORDER BY shot_num",
        (script_id,),
    ).fetchall()
    print(f"  Storyboard shots (script_id={script_id}): {len(shots)}")
    for s in shots:
        print(f"    Shot {s['shot_num']}: {s['narration'][:80] if s.get('narration') else '(no narration)'}")
        print(f"      chars={s.get('char_ids', '[]')}")

# Video clips for ch2
if script_id:
    clips = db.conn.execute(
        "SELECT vc.shot_id, vc.file_path, ss.shot_num FROM video_clip vc "
        "JOIN storyboard_shot ss ON vc.shot_id = ss.id "
        "WHERE ss.script_id = ? ORDER BY ss.shot_num",
        (script_id,),
    ).fetchall()
    print(f"  Video clips: {len(clips)}")
    for cl in clips:
        p = Path(cl["file_path"])
        print(f"    Shot {cl['shot_num']}: {cl['file_path']} ({p.stat().st_size//1024}KB if p.exists() else 'MISSING')")

print(f"\n{'='*60}")
print(f"Done. 总耗时: {time.time() - t0:.0f}s")
print(f"{'='*60}")

browser_client.close()
db.close()
