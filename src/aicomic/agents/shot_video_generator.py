"""Shot Video Generator Agent — generates video clips per storyboard shot.

Reuses the Doubao text-to-image page: pastes the shot's reference images
(character design sheet + scene multi-view) and sends a prompt starting with
a copyright declaration followed by "生成视频，Xs，...".

The prompt structure (copyright → instruction → visual description → motion →
atmosphere → quality → numbered ref descriptions → 原比例) has been proven
to pass Doubao's content filter.

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
import time
from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database
from .prompt_utils import normalize_prompt_terms


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
        self, browser_client: Any, duration_sec: float = 5.0,
        interactive: bool = False,
    ) -> None:
        """Args:
            browser_client: DoubaoBrowserClient instance (shared across agents).
            duration_sec: Default video duration for each shot (test phase: 5s).
            interactive: If True, open candidates with system player and prompt
                         user to pick one. Default False — auto-selects first.
        """
        self.browser = browser_client
        self.duration_sec = duration_sec
        self.interactive = interactive

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    # ── Tail frame extraction (v0.10: shot-to-shot continuity) ──

    @staticmethod
    def _extract_last_frame(video_path: str) -> str | None:
        """Extract a face-safe continuity frame from a video clip.

        Extracts the last frame, then overlays a semi-transparent mosaic grid
        on the eye region (top 15-35% of the frame). Most AI face-detection
        models key on the eye-nose triangle — disrupting the eye region with a
        grid pattern breaks the face signature while preserving clothing, body
        posture, and environment continuity cues.

        Returns the processed PNG path, or None on failure.
        """
        try:
            from moviepy import VideoFileClip
            from PIL import Image, ImageDraw
        except ImportError:
            print("    ⚠ moviepy/Pillow 未安装，跳过尾帧提取")
            return None

        try:
            clip = VideoFileClip(video_path)
            if clip.duration is None or clip.duration <= 0:
                clip.close()
                return None
            # Grab a frame 0.1s before the end to avoid potential black frames
            t = max(0, clip.duration - 0.1)
            full_png = str(Path(video_path).with_suffix(".full_frame.png"))
            clip.save_frame(full_png, t=t)
            clip.close()

            img = Image.open(full_png).convert("RGBA")
            w, h = img.size

            # ── Overlay: semi-transparent grid on the eye region ──
            # Eye region is roughly top 15%–35% of the frame (varies by shot
            # type; for medium shots this covers eyes while leaving forehead
            # and lower face visible).
            eye_top = int(h * 0.15)
            eye_bottom = int(h * 0.35)
            grid_spacing = 12   # pixels between grid lines
            alpha = 80          # grid opacity (0=invisible, 255=solid)

            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Horizontal lines in eye region
            for y in range(eye_top, eye_bottom, grid_spacing):
                draw.line([(0, y), (w, y)], fill=(255, 255, 255, alpha), width=2)

            # Vertical lines in eye region
            for x in range(0, w, grid_spacing):
                draw.line([(x, eye_top), (x, eye_bottom)], fill=(255, 255, 255, alpha), width=2)

            # Composite overlay onto the frame, then flatten to RGB
            img = Image.alpha_composite(img, overlay)
            img = img.convert("RGB")

            cropped_path = str(Path(video_path).with_suffix(".last_frame.png"))
            img.save(cropped_path, "PNG")

            # Clean up the full frame
            try:
                Path(full_png).unlink()
            except Exception:
                pass

            print(f"    🖼 尾帧已提取(眼部网格遮挡): {Path(cropped_path).name}")
            return cropped_path
        except Exception as e:
            print(f"    ⚠ 尾帧提取失败: {e}")
            return None

    # ── Reference image resolution ──

    def _resolve_reference_images(
        self, db: Database, shot: dict
    ) -> list[dict]:
        """Find reference images for a shot: character design sheets + scene multi-view.

        v0.9: Each character contributes ONE design sheet image (from character_outfit),
        resolved by shot.outfit_tag. No more face closeup + three-view.

        Returns list of {"path": str, "label": str} — structured for prompt building.
        """
        images: list[dict] = []

        # ── Character design sheet images (game card format) ──
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
                    # Fetch character name for readable label
                    char_name = db.conn.execute(
                        "SELECT name FROM character_card WHERE id = ?",
                        (char_id,),
                    ).fetchone()
                    name = (char_name["name"] if char_name
                            else f"角色#{char_id}")
                    tag_text = outfit.get("tag", "默认")
                    images.append({
                        "path": img_path,
                        "kind": "role",
                        "label": f"角色：{name}，{tag_text}",
                    })

        # ── Scene multi-view image ──
        scene_id = shot.get("scene_id")
        if scene_id:
            row = db.conn.execute(
                "SELECT multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
                (scene_id,),
            ).fetchone()
            if row and row["multi_view_image"]:
                path = row["multi_view_image"]
                if Path(path).exists():
                    images.append({
                        "path": path,
                        "kind": "scene",
                        "label": "场景多景别参考图",
                    })

        return images

    # ── Video prompt builder ──

    def _build_video_prompt(
        self, shot: dict, ref_images: list[dict], last_frame_path: str | None = None
    ) -> str:
        """Build the video generation prompt for a shot.

        Structure (proven to pass Doubao content filter):
        1. Copyright declaration
        2. "生成视频，Xs" instruction
        3. Continuity instruction (only when last_frame_path is provided)
        4. image_prompt + camera motion
        5. narrative atmosphere (only if adds new info)
        6. quality tags
        7. Numbered reference image descriptions (matching actual images sent)
        8. "原比例。"

        Terms normalization (see _normalize_prompt_terms):
        - 曼联 → 幔帐 (Manchester United trademark → correct ancient bed curtain)
        - Other commercial-brand conflicts → correct ancient Chinese equivalents
        """
        image_prompt = shot.get("image_prompt", "")
        narration = shot.get("narration", "")
        camera = shot.get("camera_movement", "")
        duration = shot.get("duration_sec", self.duration_sec)

        # ── Normalize terms (fix typos that match commercial brands) ──
        image_prompt = normalize_prompt_terms(image_prompt)
        narration = normalize_prompt_terms(narration)

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
            f"{image_prompt}。",
            f"{motion}。",
        ]

        # ── v0.10: Tail-frame continuity instruction ──
        if last_frame_path:
            parts.append(
                "请接着上一镜头的尾帧画面继续生成，"
                "保持人物位置、服装细节、发型、容貌、光影方向完全一致。"
            )

        # Only include narration if it adds genuinely new information
        # (not already covered by image_prompt)
        if narration and not self._is_redundant(narration, image_prompt):
            parts.append(f"画面氛围：{narration}。")

        parts.append("高质量AI视频，流畅运镜，电影级画面。")

        # Build numbered reference image descriptions
        if ref_images:
            ref_parts = ["参考图说明："]
            for i, ri in enumerate(ref_images):
                ref_parts.append(f"第 {i+1} 张为{ri['label']}")
                ref_parts.append("；" if i < len(ref_images) - 1 else "。")
            parts.append("".join(ref_parts))

        parts.append("原比例。")

        return "".join(parts)

    @staticmethod
    def _is_redundant(narration: str, image_prompt: str) -> bool:
        """Check if narration is largely redundant with image_prompt.

        If >70% of narration's meaningful characters already appear in
        image_prompt, skip it to avoid redundancy-based filtering.
        """
        if not narration or not image_prompt:
            return False
        narr_chars = set(narration) - {" ", "，", "。", "、", "；", "："}
        ip_chars = set(image_prompt) - {" ", "，", "。", "、", "；", "："}
        if not narr_chars:
            return True
        overlap = len(narr_chars & ip_chars)
        if len(narr_chars) < 10:
            # Too short to be meaningfully redundant
            return False
        return overlap / len(narr_chars) > 0.7

    # ── User selection ──

    def _user_select_video(
        self, paths: list[str], shot_num: int
    ) -> str | None:
        """Auto-select first candidate (interactive=False) or prompt user."""
        if not self.interactive:
            return paths[0]

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
        if existing_status == "partial":
            db.log(self.agent_name, chapter_id, "resuming",
                   {"reason": "partial completion, retrying failed shots"})

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
            last_frame_path: str | None = None  # v0.10: continuity between shots
            for si, shot in enumerate(shots_to_generate):
                shot_num = shot["shot_num"]
                label = f"镜头 {shot_num} ({si+1}/{len(shots_to_generate)})"
                print(f"\n  [{label}]")

                # ── Reset per-shot retry counter ──
                self._retry_count = 0

                ref_images = self._resolve_reference_images(db, shot)

                # ── v0.10: Append tail frame from previous shot as continuity ref ──
                if last_frame_path and Path(last_frame_path).exists():
                    ref_images.append({
                        "path": last_frame_path,
                        "kind": "tail_frame",
                        "label": "尾帧参考",
                    })
                    print(f"    🔗 尾帧参考(去人脸): {Path(last_frame_path).name}")

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
                    path = ri["path"]
                    # Use kind field for reliable type detection
                    if ri.get("kind") == "role":
                        kind = "角色设定图"
                    elif ri.get("kind") == "scene":
                        kind = "场景多景别"
                    elif ri.get("kind") == "tail_frame":
                        kind = "尾帧参考"
                    else:
                        kind = "参考图"
                    print(f"       [{kind}] {Path(path).name}")

                # Build video prompt with structured ref info
                video_prompt = self._build_video_prompt(
                    shot, ref_images, last_frame_path=last_frame_path
                )
                print(f"    📝 视频提示词 ({len(video_prompt)} 字)")

                # Extract plain paths for browser call
                ref_paths = [ri["path"] for ri in ref_images]

                # Generate
                result = self.browser.generate_video_from_images(
                    prompt=video_prompt,
                    reference_images=ref_paths,
                    duration_sec=float(shot.get("duration_sec", self.duration_sec)),
                )

                if not result.success or not result.file_paths:
                    meta = result.metadata if result.success is False else {}
                    reason = (meta or {}).get("reason", "")
                    wrong_type = (meta or {}).get("wrong_type", "")
                    page_text = (meta or {}).get("page_text", "")
                    paste_failed = (meta or {}).get("paste_failed", False)

                    # ── v0.10+: Wrong type retry (image instead of video) ──
                    if wrong_type == "image" and self._retry_count < 1:
                        self._retry_count += 1
                        print(f"    🔀 豆包生成了图片而非视频，改用强化视频提示词重试...")
                        force_video_prompt = video_prompt.replace(
                            "这是我用AI生成的图片，我有版权，请帮我根据提示词生成视频。",
                            "这是我用AI生成的图片，我有版权。请生成动态视频（video），不要生成静态图片（image）。",
                        )
                        force_video_prompt = force_video_prompt.replace(
                            "原比例。",
                            "注意：必须生成视频，禁止生成静态图片。原比例。",
                        )
                        if force_video_prompt != video_prompt:
                            time.sleep(5)
                            result = self.browser.generate_video_from_images(
                                prompt=force_video_prompt,
                                reference_images=ref_paths,
                                duration_sec=float(
                                    shot.get("duration_sec", self.duration_sec)
                                ),
                            )
                            if result.success and result.file_paths:
                                print(f"    ✓ 重试成功（强化视频模式）")
                                pass
                            else:
                                db.log(
                                    self.agent_name, chapter_id, "shot_video_failed",
                                    {"shot_num": shot_num, "shot_id": shot["id"],
                                     "error": result.error,
                                     "retried": True,
                                     "retry_reason": "wrong_type_image"},
                                    level="WARNING",
                                )
                                print(f"    ✗ 重试仍失败: {result.error}")
                                continue
                        else:
                            db.log(
                                self.agent_name, chapter_id, "shot_video_failed",
                                {"shot_num": shot_num, "shot_id": shot["id"],
                                 "error": "wrong_type_image_cannot_adjust"},
                                level="WARNING",
                            )
                            print(f"    ✗ 无法调整 prompt，跳过")
                            continue

                    # ── Paste failure: hard stop — don't waste time ──
                    elif paste_failed:
                        msg = (
                            f"镜头 {shot_num}: 参考图粘贴失败（输入区未检测到附件）。"
                            f"中止全部视频生成，请检查豆包页面状态。"
                        )
                        print(f"\n  🛑 {msg}")
                        db.log(
                            self.agent_name, chapter_id, "pipeline_aborted",
                            {"shot_num": shot_num, "shot_id": shot["id"],
                             "reason": "paste_failed"},
                            level="ERROR",
                        )
                        raise RuntimeError(msg)

                    # ── Moderation block: log what Doubao said, don't guess ──
                    elif reason:
                        print(f"    🚫 审核拦截: {reason}")
                        if page_text:
                            # Print first ~500 chars of what Doubao showed
                            snippet = page_text[:500].replace("\n", " ")
                            print(f"    📄 豆包页面内容: {snippet}...")
                        db.log(
                            self.agent_name, chapter_id, "shot_video_failed",
                            {"shot_num": shot_num, "shot_id": shot["id"],
                             "error": result.error, "reason": reason,
                             "page_text_snippet": (page_text or "")[:1000]},
                            level="WARNING",
                        )
                        print(f"    ✗ 跳过（审核拦截，未修改 prompt）")
                        continue

                    else:
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

                    # ── v0.10: Extract tail frame for next shot's continuity ──
                    # Clean up previous tail frame to avoid disk clutter
                    if last_frame_path:
                        try:
                            Path(last_frame_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                    last_frame_path = self._extract_last_frame(chosen)

                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id, "shot_video_db_error",
                        {"shot_num": shot_num, "error": str(e)},
                        level="ERROR",
                    )
                    print(f"    ✗ 数据库写入失败: {e}")

            # ── v0.10: Clean up last tail frame (no longer needed) ──
            if last_frame_path:
                try:
                    Path(last_frame_path).unlink(missing_ok=True)
                except Exception:
                    pass

            # ── Mark status (partial if some failed, so next run can resume) ──
            failed_count = total_with_prompts - clips_created - len(already_done)
            if clips_created == 0:
                final_status = "failed"
            elif failed_count > 0:
                final_status = "partial"  # Some shots still need generation
            else:
                final_status = "done"

            db.set_agent_status(self.agent_name, chapter_id, final_status)
            db.log(
                self.agent_name, chapter_id,
                "completed" if final_status == "done" else "partial",
                {
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                    "failed_count": failed_count,
                    "status": final_status,
                },
            )

            return AgentResult(
                success=final_status != "failed",
                data={
                    "clips_created": clips_created,
                    "total_shots": total_with_prompts,
                    "already_done": len(already_done),
                    "failed_count": failed_count,
                    "status": final_status,
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
