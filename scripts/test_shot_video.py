"""Standalone test: shot video generation via Doubao image-to-video.

Bypasses the agent pipeline entirely. Reads existing shot/reference data
from the database, builds the prompt, and calls generate_video_from_images()
directly. Use this to validate the video generation flow before wiring it
into the full pipeline.

Usage:
    python scripts/test_shot_video.py [--shot-num N] [--headless]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Add src to path so we can import aicomic
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aicomic.db.repository import Database
from aicomic.doubao.browser import DoubaoBrowserClient
from aicomic.doubao import CookieExpiredError


def resolve_reference_images(db: Database, shot: dict, script_id: int) -> list[str]:
    """Find reference images: face closeup → three-view → scene multi-view.
    Uses script JSON to match the correct variant for each character in this shot."""
    images: list[str] = []

    # ── Build char_id → variant_name map from script JSON (this shot only) ──
    char_variant: dict[int, str] = {}
    script_rows = db.conn.execute(
        "SELECT raw_json FROM script WHERE id = ?", (script_id,)
    ).fetchone()
    shot_num = shot["shot_num"]
    if script_rows:
        script_json = json.loads(script_rows["raw_json"])
        for scene in script_json.get("scenes", []):
            for shot_data in scene.get("shots", []):
                if shot_data.get("shot_num") == shot_num:
                    for char in shot_data.get("characters", []):
                        cname = char.get("name", "")
                        crow = db.conn.execute(
                            "SELECT id FROM character_card WHERE name = ?",
                            (cname,),
                        ).fetchone()
                        if crow:
                            char_variant[crow["id"]] = char.get("variant", "default")
                    break

    char_ids_raw = shot.get("char_ids", "[]")
    try:
        char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
    except (json.JSONDecodeError, TypeError):
        char_ids = []

    for char_id in char_ids:
        # v0.12: Use character_outfit (design sheet) instead of deprecated appearance_variant
        row = db.conn.execute(
            """SELECT image_path FROM character_outfit
               WHERE character_id = ? AND image_path != ''
               ORDER BY is_default DESC LIMIT 1""",
            (char_id,),
        ).fetchone()
        if row:
            img = row["image_path"]
            if img and Path(img).exists():
                images.append(img)

    scene_id = shot.get("scene_id")
    if scene_id:
        row = db.conn.execute(
            "SELECT multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
            (scene_id,),
        ).fetchone()
        if row and row["multi_view_image"]:
            p = row["multi_view_image"]
            if Path(p).exists():
                images.append(p)

    return images


CAMERA_MOTION = {
    "Push": "镜头缓慢推进，画面由远及近",
    "Pull": "镜头缓慢拉远，画面由近及远",
    "Pan": "镜头水平横移，展现空间全貌",
    "Zoom": "镜头变焦推进",
    "FT": "镜头跟随人物移动，背景产生视差",
    "HA": "高角度俯拍，镜头缓慢下摇",
    "LA": "低角度仰拍，镜头缓慢上摇",
    "OTS": "过肩视角，前景人物轻微晃动",
    "CU": "特写镜头，人物面部微表情变化",
    "ECU": "大特写，细微动作和纹理变化",
    "MS": "中景，人物肢体动作自然流畅",
    "LS": "远景，环境氛围动态变化",
}


def build_video_prompt(shot: dict, duration_sec: float = 5.0) -> str:
    """Build the full video generation prompt for a shot."""
    image_prompt = shot.get("image_prompt", "")
    narration = shot.get("narration", "")
    camera = shot.get("camera_movement", "")
    shot_dur = shot.get("duration_sec", duration_sec)

    motion = CAMERA_MOTION.get(camera, "镜头稳定，画面自然呈现")

    parts = [
        "这是我用AI生成的图片，我有版权，请帮我根据提示词生成视频。",
        f"生成视频，{int(shot_dur)}s",
        f"{image_prompt}。{motion}。",
    ]
    if narration:
        parts.append(f"画面氛围：{narration}。")
    parts.append(
        "高质量AI视频，流畅运镜，电影级画面。"
        "参考图说明：第1张为角色面部特写（锚定五官和面部轮廓）；"
        "第2张为角色三视图（左侧面-中正面-右背面，展示全身服装和体型）；"
        "第3张为场景多景别设定（白线分隔：上方全景空间环境、中间中景核心区域、下方特写材质道具）。"
    )
    return "".join(parts)


def user_select(paths: list[str], shot_num: int) -> str | None:
    """Open candidate videos and let user pick."""
    print(f"\n  🎬 镜头 #{shot_num} — 生成了 {len(paths)} 个候选视频：")
    for i, p in enumerate(paths):
        print(f"    [{i+1}] {Path(p).name}  "
              f"({os.path.getsize(p) / 1024 / 1024:.1f}MB)")

    for p in paths:
        try:
            os.startfile(p)
        except Exception:
            pass

    while True:
        try:
            choice = input(
                f"  选择保留哪个？(1-{len(paths)}，回车默认选1，s 跳过): "
            ).strip()
            if choice.lower() == "s":
                return None
            if choice == "":
                choice = "1"
            idx = int(choice) - 1
            if 0 <= idx < len(paths):
                chosen = paths[idx]
                for p in paths:
                    if p != chosen:
                        try:
                            Path(p).unlink(missing_ok=True)
                        except Exception:
                            pass
                print(f"  ✓ 保留 [{idx+1}] {Path(chosen).name}\n")
                return chosen
            print(f"  ⚠ 请输入 1-{len(paths)} 或 s 跳过")
        except (ValueError, KeyboardInterrupt, EOFError):
            print("\n  ℹ 非交互模式，自动选第1张")
            return paths[0]


def main():
    parser = argparse.ArgumentParser(description="独立测试图生视频")
    parser.add_argument("--db", default="data/aicomic.db",
                       help="数据库路径 (default: data/aicomic.db)")
    parser.add_argument("--shot-num", type=int, default=None,
                       help="只测试指定镜头号 (1-based)，不指定则测所有")
    parser.add_argument("--duration", type=float, default=5.0,
                       help="视频时长秒数 (default: 5)")
    parser.add_argument("--no-headless", action="store_true",
                       help="显示浏览器窗口")
    parser.add_argument("--state-file", default="data/doubao_state.json",
                       help="登录状态文件")
    args = parser.parse_args()

    # ── Connect DB ──
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        print("   请先跑完整的图片管线: python -m aicomic run xxx.txt --with-images")
        sys.exit(1)

    db = Database(db_path)
    db.connect()

    # ── Find chapters with scripts ──
    chap_rows = db.conn.execute(
        "SELECT id, chapter_num FROM chapter ORDER BY id DESC LIMIT 5"
    ).fetchall()
    if not chap_rows:
        print("❌ 没有 chapter 数据")
        sys.exit(1)

    # Use latest chapter
    chapter = dict(chap_rows[0])
    chapter_id = chapter["id"]
    print(f"📖 Chapter #{chapter_id} (num={chapter.get('chapter_num', '?')})")

    # Get script_id
    script_row = db.conn.execute(
        "SELECT id FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
        (chapter_id,),
    ).fetchone()
    if not script_row:
        print("❌ 没有 script 数据")
        sys.exit(1)
    script_id = script_row["id"]

    # ── Load shots ──
    shots = db.get_storyboard_shots(script_id)
    valid_shots = [dict(s) for s in shots if dict(s).get("image_prompt", "")]
    print(f"📋 {len(valid_shots)} 个有效镜头 (共 {len(shots)} 镜头)")

    if args.shot_num:
        valid_shots = [s for s in valid_shots if s["shot_num"] == args.shot_num]
        if not valid_shots:
            print(f"❌ 没有 shot_num={args.shot_num} 的镜头")
            sys.exit(1)

    # ── Init browser ──
    headless = not args.no_headless
    print(f"🌐 浏览器: {'无头' if headless else '显示窗口'}")
    browser = DoubaoBrowserClient(
        state_file=Path(args.state_file),
        headless=headless,
        output_dir="data/",
        timeout_sec=300,
        poll_interval_sec=3,
        rate_limit_sec=5,
    )

    try:
        success_count = 0
        for si, shot in enumerate(valid_shots):
            shot_num = shot["shot_num"]
            shot_id = shot["id"]
            label = f"镜头 {shot_num} ({si+1}/{len(valid_shots)})"
            print(f"\n{'='*60}")
            print(f"  [{label}]")

            # ── Resolve reference images ──
            refs = resolve_reference_images(db, shot, script_id)
            if not refs:
                print(f"  ⚠ 无参考图片，跳过")
                continue
            print(f"  📎 参考图: {len(refs)} 张")
            for r in refs:
                print(f"     {Path(r).name}")

            # ── Build prompt ──
            video_prompt = build_video_prompt(shot, args.duration)
            print(f"  📝 提示词 ({len(video_prompt)} 字):")
            print(f"     {video_prompt[:200]}...")

            # ── Generate ──
            print(f"  🎬 开始生成视频...")
            try:
                result = browser.generate_video_from_images(
                    prompt=video_prompt,
                    reference_images=refs,
                    duration_sec=args.duration,
                )
            except CookieExpiredError as e:
                print(f"\n❌ Cookie 过期: {e}")
                print("   请运行: python scripts/export_cookies.py")
                break

            if not result.success or not result.file_paths:
                print(f"  ✗ 失败: {result.error}")
                # Save debug info
                db.log(
                    "test_shot_video", chapter_id, "shot_failed",
                    {"shot_id": shot_id, "shot_num": shot_num,
                     "error": result.error},
                    level="WARNING",
                )
                continue

            # ── User selection ──
            paths = result.file_paths
            if len(paths) == 1:
                chosen = paths[0]
                print(f"  ✓ 自动保存: {Path(chosen).name}")
            else:
                chosen = user_select(paths, shot_num)

            if chosen:
                db.create_video_clip(shot_id, chosen, args.duration)
                success_count += 1
                print(f"  💾 已保存到 DB (shot_id={shot_id})")
            else:
                # Clean up all
                for p in paths:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception:
                        pass
                print(f"  ⏭ 已跳过，删除所有候选")

        print(f"\n{'='*60}")
        print(f"✅ 完成: {success_count}/{len(valid_shots)} 个视频生成成功")

    finally:
        browser.close()
        db.close()


if __name__ == "__main__":
    main()
