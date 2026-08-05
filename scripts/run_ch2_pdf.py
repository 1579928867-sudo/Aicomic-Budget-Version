"""Chapter 2 PDF pipeline — parse PDF → full pipeline → shots 1-3 video (one attempt each).

Usage:
    py -3 scripts/run_ch2_pdf.py
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
from aicomic.parsers import parse_file
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

# ── Config ──
config_path = project_root / "config" / "settings.yaml"
config = {}
if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

api_key = os.environ.get("DEEPSEEK_API_KEY") or config.get("deepseek", {}).get("api_key", "")
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
    sys.exit(1)

configure_output_encoding()

# ══════════════════════════════════════════════════════════════════════
# Step 0: Parse PDF
# ══════════════════════════════════════════════════════════════════════
pdf_path = project_root / "逆天邪神第2章 情不自禁.pdf"
print(f"📄 Parsing PDF: {pdf_path.name}")
print(f"   路径: {pdf_path}")
print(f"   存在: {pdf_path.exists()}")

try:
    raw_text = parse_file(pdf_path)
except Exception as exc:
    print(f"\n❌ PDF 解析失败: {exc}")
    sys.exit(1)

if not raw_text or not raw_text.strip():
    print(f"\n❌ PDF 解析结果为空，停止。")
    sys.exit(1)

print(f"   ✅ PDF 解析成功: {len(raw_text)} 字符")

# Quick sanity check — should have substantial Chinese text
cn_chars = sum(1 for c in raw_text if '一' <= c <= '鿿')
print(f"   中文字符数: {cn_chars}")

if cn_chars < 100:
    print(f"\n❌ PDF 中文字符过少 ({cn_chars})，可能识别失败，停止。")
    print(f"   前200字符: {raw_text[:200]}")
    sys.exit(1)

# Show first few lines
lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
print(f"   有效行数: {len(lines)}")
print(f"   前3行预览:")
for i, line in enumerate(lines[:3]):
    print(f"     L{i+1}: {line[:120]}")

# ══════════════════════════════════════════════════════════════════════
# Step 1: DB setup
# ══════════════════════════════════════════════════════════════════════
db_path = project_root / "data" / "aicomic.db"
db = Database(db_path)
db.connect()
db.init_schema()
db.migrate_schema()

novel_title = "逆天邪神"
existing_novel = db.get_novel_by_title(novel_title)
if existing_novel:
    novel_id = existing_novel["id"]
    print(f"\n📖 Novel 已有 (id={novel_id})")
else:
    novel_id = db.create_novel(title=novel_title, author="")
    print(f"\n📖 Novel created (id={novel_id})")

# Find or create chapter 2
existing_ch2 = db.get_chapter_by_num(novel_id, 2)
if existing_ch2:
    chapter_id = existing_ch2["id"]
    print(f"📋 Chapter 2 已有 (id={chapter_id}), 更新 raw_text")
    db.conn.execute(
        "UPDATE chapter SET raw_text = ? WHERE id = ?",
        (raw_text, chapter_id),
    )
    db.conn.commit()
else:
    chapter_id = db.create_chapter(novel_id, 2, raw_text)
    print(f"📋 Chapter 2 created (id={chapter_id})")

print(f"\n{'='*60}")
print(f"第2章 PDF 全链路 — 镜头 1-3")
print(f"  Chapter ID: {chapter_id}")
print(f"  文本: {len(raw_text)} 字符 / {cn_chars} 中文")
print(f"{'='*60}")

# ══════════════════════════════════════════════════════════════════════
# Step 2: Register agents
# ══════════════════════════════════════════════════════════════════════
llm = DeepSeekClient(
    api_key=api_key,
    model=config.get("deepseek", {}).get("model", "deepseek-chat"),
    base_url=config.get("deepseek", {}).get("base_url", "https://api.deepseek.com"),
)

bus = AgentBus()
bus.register(ScriptwriterAgent(llm_client=llm))
bus.register(ScreenwriterAgent(llm_client=llm))
bus.register(CharacterDesignerAgent(llm_client=llm))
bus.register(SceneDesignerAgent(llm_client=llm))
bus.register(ShotVisualizerAgent(llm_client=llm))
bus.register(OutfitManagerAgent(llm_client=llm))

# Shared browser (no-headless for video gen)
doubao_cfg = config.get("doubao", {})
browser_client = DoubaoBrowserClient(
    state_file=Path(doubao_cfg.get("state_file", "data/doubao_state.json")),
    cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
    headless=False,  # 显示浏览器窗口
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
# Phase 1: Full pipeline (no video yet)
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
print(f"  Beats: {result.data.get('beat_count', 0)}")
print(f"  Shots: {result.data.get('shots_created', 0)}")
print(f"  Outfits: {result.data.get('outfits_created', 0)}")
print(f"  Shots visualized: {result.data.get('shots_visualized', 0)}")
print(f"{'─'*60}")

# ══════════════════════════════════════════════════════════════════════
# Phase 2: Video generation — shots 1-3 ONLY, ONE attempt each
# ══════════════════════════════════════════════════════════════════════
if not script_id:
    print("\nERROR: No script_id, cannot generate videos")
    browser_client.close()
    db.close()
    sys.exit(1)

print(f"\n{'▸'*30}")
print(f"Phase 2: Video — shots 1-3 (一次生成，不重试)")
print(f"{'▸'*30}\n")

all_shots = db.get_storyboard_shots(script_id)
shots_list = [dict(s) for s in all_shots]
print(f"  找到 {len(shots_list)} 个镜头")

target_shots = [s for s in shots_list if s["shot_num"] in (1, 2, 3)]
target_shots.sort(key=lambda s: s["shot_num"])

if not target_shots:
    print("ERROR: 没有找到 shot 1-3！")
    browser_client.close()
    db.close()
    sys.exit(1)

shot_video_gen = ShotVideoGeneratorAgent(
    browser_client=browser_client,
    duration_sec=float(config.get("video", {}).get("shot_video_duration_sec", 5)),
)

video_results = {}
for shot in target_shots:
    shot_num = shot["shot_num"]
    shot_id = shot["id"]
    print(f"\n{'─'*50}")
    print(f"  🎬 Shot {shot_num} (id={shot_id})")
    print(f"{'─'*50}")

    # Check existing — skip if already done
    existing = db.conn.execute(
        "SELECT vc.id, vc.file_path FROM video_clip vc WHERE vc.shot_id = ?",
        (shot_id,),
    ).fetchone()
    if existing:
        p = Path(existing["file_path"])
        if p.exists():
            print(f"  ✅ 已有视频: {p.name} ({p.stat().st_size//1024}KB)")
            video_results[shot_num] = {"status": "skipped", "file": str(p)}
            continue
        else:
            db.conn.execute("DELETE FROM video_clip WHERE shot_id = ?", (shot_id,))
            db.conn.commit()
            print("  🧹 清理过期clip记录")

    # Resolve reference images
    refs = shot_video_gen._resolve_reference_images(db, shot)
    if not refs:
        print(f"  ❌ 无参考图！跳过")
        video_results[shot_num] = {"status": "failed", "error": "No reference images"}
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

    # Generate — ONE attempt
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

            db.create_video_clip(
                shot_id=shot_id,
                file_path=str(vp),
                duration_sec=float(shot.get("duration_sec", 10.0)),
            )

            # Backup copy
            dest = project_root / "data" / "videos" / f"ch2_shot_{shot_num:02d}.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(vp), str(dest))
            print(f"  📁 备份到: {dest.name}")

            video_results[shot_num] = {
                "status": "success", "file": str(vp), "backup": str(dest),
                "size_mb": round(size_mb, 1), "elapsed_s": int(elapsed_shot),
            }
        else:
            err = gen_result.error or "未知错误"
            meta = gen_result.metadata or {}
            reason = meta.get("reason", "")
            print(f"\n  ❌ 失败 ({elapsed_shot:.0f}s): {err}")
            if reason:
                print(f"     reason: {reason[:200]}")
            video_results[shot_num] = {
                "status": "failed", "error": err, "reason": reason[:200],
                "elapsed_s": int(elapsed_shot),
            }
    except Exception as e:
        elapsed_shot = time.time() - t0_shot
        print(f"\n  ❌ 异常 ({elapsed_shot:.0f}s): {e}")
        video_results[shot_num] = {
            "status": "error", "error": str(e), "elapsed_s": int(elapsed_shot),
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
print(f"📊 第 2 章 PDF 生成报告")
print(f"{'='*60}")
print(f"\n## PDF 解析")
print(f"  文件: {pdf_path.name}")
print(f"  字符数: {len(raw_text)} / 中文: {cn_chars}")
print(f"  行数: {len(lines)}")

print(f"\n## Phase 1: Pipeline ({pipeline_elapsed:.0f}s)")
print(f"  Status: {'✅' if result.success else '❌'}")
pipeline_data = dict(result.data) if result.data else {}
print(f"  Script ID: {script_id}")
print(f"  Characters: {pipeline_data.get('characters', [])}")
print(f"  Scenes: {pipeline_data.get('scenes_list', [])}")
print(f"  Beats: {pipeline_data.get('beat_count', 0)}")
print(f"  Shots: {pipeline_data.get('shots_created', 0)}")
print(f"  Outfits: {pipeline_data.get('outfits_created', 0)}")
print(f"  Shots visualized: {pipeline_data.get('shots_visualized', 0)}")

print(f"\n## Phase 2: Video — shots 1-3")
for sn in [1, 2, 3]:
    vr = video_results.get(sn, {"status": "not_run"})
    icons = {"success": "✅", "skipped": "⏭️", "failed": "❌", "error": "💥", "not_run": "⬜"}
    icon = icons.get(vr["status"], "❓")
    detail = ""
    if vr["status"] == "success":
        detail = f" — {vr.get('size_mb', '?')}MB in {vr.get('elapsed_s', '?')}s"
    elif vr["status"] in ("failed", "error"):
        detail = f" — {vr.get('error', '?')[:80]}"
    elif vr["status"] == "skipped":
        detail = f" — 已存在"
    print(f"  {icon} Shot {sn}: {vr['status']}{detail}")

print(f"\n## 总耗时: {time.time() - t0:.0f}s")
print(f"{'='*60}")

browser_client.close()
db.close()
