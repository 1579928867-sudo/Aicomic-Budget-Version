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

import time
from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database
from .prompt_utils import normalize_prompt_terms, parse_char_ids, user_select_candidate


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

    # ── Reference image resolution ──

    def _resolve_reference_images(
        self, db: Database, shot: dict
    ) -> list[dict]:
        """Find reference images for a shot: character design sheets + scene multi-view.

        v0.12: Each character's outfit is resolved independently via the
        shot_character_outfit junction table — no more single-outfit_tag last-wins.

        Returns list of {"path": str, "label": str} — structured for prompt building.
        """
        images: list[dict] = []

        # ── Character design sheet images (game card format) ──
        char_ids = parse_char_ids(shot.get("char_ids"))

        # Per-character outfit tags from junction table (v0.12)
        char_outfits = db.get_shot_character_outfits(shot["id"])

        for char_id in char_ids:
            outfit_tag = char_outfits.get(char_id)  # None → default
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
        self, shot: dict, ref_images: list[dict]
    ) -> str:
        """Build industry-standard time-segmented video prompt.

        Structure (from industry reference — proven to work with Doubao):
        1. Quality preamble
        2. Per-segment [0-3s][3-7s][7-10s] instructions
        3. Scene summary
        4. Reference image descriptions
        5. Copyright declaration
        """
        import json

        # ── Quality preamble (industry standard) ──
        QUALITY_PREAMBLE = (
            "虚幻引擎5渲染，3D国漫电影质感，16:9宽银幕画幅，"
            "4K超高清，60fps高帧率，电影级光影，"
            "全局光照，体积雾，物理布料模拟，动态模糊自然"
        )

        # ── Read segments from DB (v0.13+ format) ──
        segments_json = shot.get("segments_json", "[]")
        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
        except (json.JSONDecodeError, TypeError):
            segments = []

        parts = [QUALITY_PREAMBLE]

        # ── Per-segment instructions ──
        if segments and len(segments) == 3:
            for seg in segments:
                line = f"[{seg.get('time_range', '?')}]镜头:{seg.get('camera', '中景')}，{seg.get('action', '')}"
                dialogue = seg.get("dialogue")
                sound = seg.get("sound", "")
                transition = seg.get("transition")

                if dialogue:
                    line += f"。{dialogue}"
                if sound:
                    line += f"。音效:{sound}"
                if transition:
                    line += f"。{transition}"
                parts.append(line + "。")
        else:
            # Fallback: use old-style flat fields
            image_prompt = normalize_prompt_terms(shot.get("image_prompt", ""))
            narration = normalize_prompt_terms(shot.get("narration", ""))
            camera = shot.get("camera_movement", "")
            camera_motion_map = {
                "Push": "镜头缓慢推进", "Pull": "镜头缓慢拉远",
                "Pan": "镜头水平横移", "FT": "镜头跟随人物移动",
                "HA": "高角度俯拍", "LA": "低角度仰拍",
                "OTS": "过肩视角", "CU": "特写", "ECU": "大特写",
                "MS": "中景", "LS": "全景",
            }
            motion = camera_motion_map.get(camera, "中景")
            parts.append(f"[0-10秒]镜头:{motion}，{image_prompt}。{narration}。")

        # ── Dialogue (if not already embedded in segments) ──
        if not segments:
            dialogue = normalize_prompt_terms(shot.get("dialogue", ""))
            if dialogue:
                parts.append(f"人物语言与内心独白：{dialogue}。")

        parts.append("无背景音乐，纯画面内容。")

        # ── Reference images ──
        if ref_images:
            ref_parts = ["参考图说明："]
            for i, ri in enumerate(ref_images):
                ref_parts.append(f"第 {i+1} 张为{ri['label']}")
                ref_parts.append("；" if i < len(ref_images) - 1 else "。")
            parts.append("".join(ref_parts))

        parts.append("原比例。")
        parts.append("（这是我用AI生成的图片，我有版权）")

        return "\n".join(parts)

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
            return False
        return overlap / len(narr_chars) > 0.7

    @staticmethod
    def _extract_subtitle_lines(dialogue: str) -> str:
        """Format dialogue for natural Chinese subtitles.

        Input:  "萧澈（内心）（困惑）: 怎么回事……\n小姑妈: 你醒了！"
        Output: "萧澈心想："怎么回事……" | 小姑妈："你醒了！"
        """
        if not dialogue:
            return ""
        lines = []
        for line in dialogue.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Parse "Speaker（emotion）: content" or "Speaker: content"
            sep = "：" if "：" in line else ":"
            if sep in line:
                speaker_part, _, content = line.partition(sep)
                speaker_part = speaker_part.strip()
                content = content.strip().strip('"').strip('"').strip("'")

                # Extract speaker name (before first bracket)
                speaker = speaker_part.split("（")[0].split("(")[0].strip()

                # Detect if internal monologue
                is_inner = "内心" in speaker_part

                if is_inner:
                    lines.append(f'{speaker}心想："{content}"')
                else:
                    lines.append(f'{speaker}："{content}"')
        return " | ".join(lines) if lines else ""

    # ── User selection ──

    # ── Main execution ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        skip = begin_agent_run(self.agent_name, chapter_id, db, {"script_id": script_id})
        if skip:
            return skip

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

                # ── Reset per-shot retry counter ──
                self._retry_count = 0

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
                    path = ri["path"]
                    # Use kind field for reliable type detection
                    if ri.get("kind") == "role":
                        kind = "角色设定图"
                    elif ri.get("kind") == "scene":
                        kind = "场景多景别"
                    else:
                        kind = "参考图"
                    print(f"       [{kind}] {Path(path).name}")

                # Build video prompt with structured ref info
                video_prompt = self._build_video_prompt(
                    shot, ref_images
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
                        force_video_prompt = "请生成动态视频（video），不要生成静态图片（image）。" + video_prompt
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
                    chosen = user_select_candidate(
                        paths, self.interactive, f"🎬 镜头 #{shot_num}",
                        allow_skip=True, skip_msg=f"跳过镜头 #{shot_num}",
                    )
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
