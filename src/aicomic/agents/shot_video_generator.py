"""Shot Video Generator Agent — generates video clips per storyboard shot.

Reuses the Doubao text-to-image page: pastes the shot's reference images
(character design sheet + scene multi-view) and sends a "生成视频，Xs，..." prompt.
Doubao auto-switches to its video model and returns mp4 files.

v0.9: Character images come from character_outfit (single design sheet),
not appearance_variant (face closeup + three-view).

Interactive mode (half-auto): user selects from generated candidates via CLI,
same as ImageGenerator's selection flow.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database


class ShotVideoGeneratorAgent(AgentInterface):
    """Generates video clips per storyboard shot via image-to-video on Doubao.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"clips_created": int, "total_shots": int}

    Pipeline position: after ShotVisualizer, before VideoComposer.
    Only runs when --with-video is passed and video_backend is "doubao".
    v0.9: Uses single character design sheet images (not face closeup + three-view).
    """

    agent_name = "shot-video-generator"

    def __init__(
        self, browser_client: Any, duration_sec: float = 5.0
    ) -> None:
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
            duration_sec: Default video duration for each shot (test phase: 5s).
        """
        self.browser = browser_client
        self.duration_sec = duration_sec

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    # ── Reference image resolution ──

    def _resolve_reference_images(
        self, db: Database, shot: dict
    ) -> list[str]:
        """Find reference images for a shot: character design sheets + scene multi-view.

        v0.9: Each character contributes ONE design sheet image (from character_outfit),
        resolved by shot.outfit_tag. No more face closeup + three-view.
        """
        images: list[str] = []

        # ── Character design sheet images ──
        char_ids_raw = shot.get("char_ids", "[]")
        try:
            char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
        except (json.JSONDecodeError, TypeError):
            char_ids = []

        outfit_tag = shot.get("outfit_tag")  # None → default

        for char_id in char_ids:
            outfit = db.get_character_outfit(char_id, outfit_tag)
            if not outfit:
                # Fallback: default outfit
                outfit = db.get_character_outfit(char_id, None)
            if outfit:
                img_path = outfit.get("image_path", "")
                if img_path and Path(img_path).exists():
                    images.append(img_path)

        # ── Scene multi-view image (unchanged) ──
        scene_id = shot.get("scene_id")
        if scene_id:
            row = db.conn.execute(
                "SELECT multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
                (scene_id,),
            ).fetchone()
            if row and row["multi_view_image"]:
                path = row["multi_view_image"]
                if Path(path).exists():
                    images.append(path)

        return images

    # ── Video prompt builder ──

    def _build_video_prompt(self, shot: dict) -> str:
        """Build the video generation prompt for a shot.

        Format: "生成视频，Xs，[image_prompt with motion cues]。
                 场景参考多视图说明。角色参考已附三视图。"
        """
        image_prompt = shot.get("image_prompt", "")
        narration = shot.get("narration", "")
        camera = shot.get("camera_movement", "")
        duration = shot.get("duration_sec", self.duration_sec)

        # Build motion cue from camera movement
        camera_motion_map = {
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
        motion = camera_motion_map.get(camera, "镜头稳定，画面自然呈现")

        parts = [
            "这是我用AI生成的图片，我有版权，请帮我根据提示词生成视频。",
            f"生成视频，{int(duration)}s",
            f"{image_prompt}。{motion}。",
        ]

        if narration:
            # Add narrative atmosphere
            parts.append(f"画面氛围：{narration}。")

        parts.append(
            "高质量AI视频，流畅运镜，电影级画面。"
            "参考图说明：人物参考图为角色设定图（含全身设计+三视图+人物简介+装备细节）；"
            "场景参考图为多景别设定。"
        )

        return "".join(parts)

    # ── User selection ──

    def _user_select_video(
        self, paths: list[str], shot_num: int
    ) -> str | None:
        """Open all candidate videos with system player, prompt user to pick one."""
        print(f"\n  🎬 镜头 #{shot_num} — 豆包生成了 {len(paths)} 个候选视频：")
        for i, p in enumerate(paths):
            print(f"    [{i+1}] {Path(p).name}")

        # Open with system default player
        for p in paths:
            try:
                if sys.platform == "win32":
                    os.startfile(p)
                elif sys.platform == "darwin":
                    subprocess.run(["open", p], check=False)
                else:
                    subprocess.run(["xdg-open", p], check=False)
            except Exception:
                pass

        while True:
            try:
                choice = input(
                    f"  选择保留哪个？(1-{len(paths)}，回车默认选1，输入 s 跳过): "
                ).strip()
                if choice.lower() == "s":
                    print(f"  ⏭ 跳过镜头 #{shot_num}\n")
                    return None
                if choice == "":
                    choice = "1"
                idx = int(choice) - 1
                if 0 <= idx < len(paths):
                    chosen = paths[idx]
                    print(
                        f"  ✓ 保留 [{idx+1}] {Path(chosen).name}"
                        f"，删除其余 {len(paths)-1} 个\n"
                    )
                    return chosen
                print(f"  ⚠ 请输入 1-{len(paths)} 或 s 跳过")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("\n  ℹ 非交互模式，自动选择第1张")
                return paths[0]

    # ── Main execution ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"script_id": script_id})

        try:
            # ── Load shots with image_prompts ──
            shots = db.get_storyboard_shots(script_id)
            if not shots:
                raise ValueError(f"No storyboard shots for script_id={script_id}")

            # Filter: need image_prompt, and no existing video_clip
            shots_to_generate = []
            already_done = []
            for s in shots:
                sd = dict(s)
                if not sd.get("image_prompt", ""):
                    continue  # No image prompt → skip
                existing = db.get_video_clips_for_shot(sd["id"])
                if existing:
                    already_done.append(sd["shot_num"])
                else:
                    shots_to_generate.append(sd)

            if not shots_to_generate:
                db.log(
                    self.agent_name, chapter_id, "skipped",
                    {"reason": "all valid shots already have video clips",
                     "already_done": already_done},
                )
                db.set_agent_status(self.agent_name, chapter_id, "done")
                total = len([s for s in shots if dict(s).get("image_prompt", "")])
                return AgentResult(
                    success=True,
                    data={"clips_created": 0, "total_shots": total, "skipped_all": True},
                )

            total_with_prompts = len([
                s for s in shots if dict(s).get("image_prompt", "")
            ])
            print(
                f"  Shot Video Generator: {len(shots_to_generate)} 个镜头待生成 "
                f"({len(already_done)} 已跳过, 共 {total_with_prompts} 有效)"
            )

            # ── Generate per shot ──
            clips_created = 0
            for si, shot in enumerate(shots_to_generate):
                shot_num = shot["shot_num"]
                label = f"镜头 {shot_num} ({si+1}/{len(shots_to_generate)})"
                print(f"\n  [{label}]")

                ref_images = self._resolve_reference_images(db, shot)
                if not ref_images:
                    db.log(
                        self.agent_name, chapter_id, "shot_skipped_no_refs",
                        {"shot_num": shot_num, "shot_id": shot["id"]},
                        level="WARNING",
                    )
                    print(f"    ⚠ 无参考图片（需先运行 Image Generator），跳过")
                    continue

                print(f"    📎 参考图片: {len(ref_images)} 张")
                for ri in ref_images:
                    print(f"       {Path(ri).name}")

                # Build video prompt
                video_prompt = self._build_video_prompt(shot)
                print(f"    📝 视频提示词 ({len(video_prompt)} 字)")

                # Generate
                result = self.browser.generate_video_from_images(
                    prompt=video_prompt,
                    reference_images=ref_images,
                    duration_sec=float(shot.get("duration_sec", self.duration_sec)),
                )

                if not result.success or not result.file_paths:
                    db.log(
                        self.agent_name, chapter_id, "shot_video_failed",
                        {"shot_num": shot_num, "shot_id": shot["id"],
                         "error": result.error},
                        level="WARNING",
                    )
                    print(f"    ✗ 生成失败: {result.error}")
                    continue

                # User selection
                paths = result.file_paths
                if len(paths) == 1:
                    chosen = paths[0]
                    print(f"    ✓ 已保存 (仅1个候选) → {Path(chosen).name}")
                else:
                    chosen = self._user_select_video(paths, shot_num)
                    if chosen is None:
                        # Clean up all
                        for p in paths:
                            try:
                                Path(p).unlink(missing_ok=True)
                            except Exception:
                                pass
                        continue

                    # Delete unchosen
                    for p in paths:
                        if p != chosen:
                            try:
                                Path(p).unlink(missing_ok=True)
                            except Exception:
                                pass

                # Save to DB
                try:
                    db.create_video_clip(
                        shot_id=shot["id"],
                        file_path=chosen,
                        duration_sec=float(shot.get("duration_sec", self.duration_sec)),
                    )
                    clips_created += 1
                    print(f"    💾 已保存到数据库 (shot_id={shot['id']})")
                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id, "shot_video_db_error",
                        {"shot_num": shot_num, "error": str(e)},
                        level="ERROR",
                    )
                    print(f"    ✗ 数据库写入失败: {e}")

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
