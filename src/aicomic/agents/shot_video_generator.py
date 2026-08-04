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

        v0.13: Scans segments text for ALL mentioned character names (not just
        char_ids) to avoid random character generation for off-screen/mentioned
        characters (e.g. "听到门外的少女声音" needs 小姑妈's reference).
        """
        import json as _json

        images: list[dict] = []
        seen_char_ids: set[int] = set()

        # ── Step 1: collect all character names mentioned anywhere in the shot ──
        mentioned_names: set[str] = set()

        # From char_ids
        char_ids = parse_char_ids(shot.get("char_ids"))
        for cid in char_ids:
            char_row = db.conn.execute(
                "SELECT name FROM character_card WHERE id = ?", (cid,)
            ).fetchone()
            if char_row:
                mentioned_names.add(char_row["name"])

        # From segments text (dialogue + action may reference off-screen chars)
        segments_raw = shot.get("segments_json", "[]")
        try:
            segments = _json.loads(segments_raw) if isinstance(segments_raw, str) else segments_raw
        except (_json.JSONDecodeError, TypeError):
            segments = []
        for seg in segments:
            combined = (seg.get("action", "") or "") + " " + (seg.get("dialogue", "") or "")
            # Check all known character names against this segment text
            all_chars = db.conn.execute(
                "SELECT id, name FROM character_card"
            ).fetchall()
            for cr in all_chars:
                if cr["name"] in combined:
                    mentioned_names.add(cr["name"])

        # ── Step 2: resolve ALL mentioned characters to their outfit images ──
        char_outfits = db.get_shot_character_outfits(shot["id"])
        # Build name→id map from all character cards
        name_to_id: dict[str, int] = {}
        all_chars = db.conn.execute(
            "SELECT id, name FROM character_card"
        ).fetchall()
        for cr in all_chars:
            name_to_id[cr["name"]] = cr["id"]

        for name in mentioned_names:
            cid = name_to_id.get(name)
            if cid is None or cid in seen_char_ids:
                continue
            seen_char_ids.add(cid)
            outfit_tag = char_outfits.get(cid)
            outfit = db.get_character_outfit(cid, outfit_tag)
            if not outfit:
                outfit = db.get_character_outfit(cid, None)
            if outfit:
                img_path = outfit.get("image_path", "")
                if img_path and Path(img_path).exists():
                    tag_text = outfit.get("tag", "默认")
                    images.append({
                        "path": img_path,
                        "kind": "role",
                        "label": f"角色：{name}，{tag_text}",
                    })

        # ── Step 3: Scene multi-view image (with real scene name from DB) ──
        scene_id = shot.get("scene_id")
        if scene_id:
            row = db.conn.execute(
                "SELECT name, multi_view_image FROM scene_card WHERE id = ? AND multi_view_image != ''",
                (scene_id,),
            ).fetchone()
            if row and row["multi_view_image"]:
                path = row["multi_view_image"]
                if Path(path).exists():
                    images.append({
                        "path": path,
                        "kind": "scene",
                        "label": f"场景多景别：{row['name']}",
                    })

        return images

    # ── Video prompt builder ──

    @staticmethod
    def _clean_dialogue(dialogue: str) -> str:
        """Strip voice/emotion annotations from dialogue for video prompt.

        Storyboard stores:  萧澈（内心，困惑，音色：清朗少年）: 怎么回事……
        Video prompt needs: 萧澈: 怎么回事……

        The annotations (内心/音色/etc) are storyboard metadata — the video
        model may flag them as "voice actor specification" (唇形匹配审核).
        """
        if not dialogue:
            return ""
        import re
        # Remove parenthesized annotations between speaker name and colon
        # "萧澈（内心，困惑，音色：清朗少年）: 怎么回事…" → "萧澈：怎么回事…"
        # Also handles half-width parens: "萧澈(内心):" → "萧澈:"
        cleaned = re.sub(r'[（(][^）)]*[）)]\s*[:：]\s*', '：', dialogue)
        # Clean up double colons
        cleaned = re.sub(r'：+', '：', cleaned)
        return cleaned

    @staticmethod
    def _clean_transition(transition: str) -> str:
        """Strip cross-shot references from transition text.

        Storyboard writes:  衔接镜头2的0-3秒：萧澈坐在床上神色警觉...
        Video prompt needs: 萧澈坐在床上神色警觉，听到门口传来少女声音

        Each shot is generated independently — cross-shot references like
        "衔接镜头N" are noise that confuses the video model.
        """
        if not transition:
            return ""
        import re
        # Strip "衔接镜头N的X-X秒：" prefix (with optional colon variations)
        cleaned = re.sub(
            r'^衔接镜头\d+的[\d\-]+秒[：:]?\s*',
            '',
            transition.strip(),
        )
        # Also strip bare "衔接镜头N" without time range
        cleaned = re.sub(
            r'^衔接镜头\d+\s*[：:]?\s*',
            '',
            cleaned,
        )
        return cleaned.strip()

    def _build_video_prompt(
        self, shot: dict, ref_images: list[dict]
    ) -> str:
        """Build industry-standard time-segmented video prompt.

        v0.13+ structure (aligned with 豆包漫剧 industry reference):
          角色—[char names]; 场景—[scene]
          [0-3s]镜头:...。音效:...。衔接前置指令:...
          [3-7s]镜头:...。音效:...。衔接前置指令:...
          [7-10s]镜头:...。音效:...。衔接前置指令:...
          场景:[scene summary]。（视频不要添加字幕）
          （使用中文对话，禁止添加字幕）
          （这是我用AI生成的图片，我有版权）

        v0.13.1 cleanup:
        - Dialogue: strip （内心/音色） annotations (flags moderation)
        - Transition: strip "衔接镜头N的X-X秒" cross-shot refs (noise for video model)
        """
        import json

        # ── Read segments from DB ──
        segments_json = shot.get("segments_json", "[]")
        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
        except (json.JSONDecodeError, TypeError):
            segments = []

        # ── Build parts ──
        parts = []

        # ── 1. 角色 + 场景 label (matching industry format) ──
        role_names: list[str] = []
        scene_name = ""
        for ri in ref_images:
            if ri.get("kind") == "role":
                # Extract just the character name from label like "角色：萧澈，默认"
                name = ri["label"].replace("角色：", "").split("，")[0].strip()
                if name:
                    role_names.append(name)
            elif ri.get("kind") == "scene":
                # Extract scene name from label like "场景多景别参考图" or "场景：婚房"
                scene_name = ri["label"].replace("场景多景别参考图", "").replace("场景多景别：", "").replace("场景：", "").strip()

        if role_names:
            parts.append(f"角色—{'、'.join(role_names)}；场景—{scene_name or '当前场景'}")

        # 16:9 horizontal (must be explicit — default may be portrait)
        parts.append("横屏16:9")

        # ── 2. Per-segment instructions ──
        if segments and len(segments) == 3:
            for seg in segments:
                time_range = seg.get("time_range", "?")
                camera = seg.get("camera", "中景")
                action = seg.get("action", "")
                dialogue = seg.get("dialogue")
                sound = seg.get("sound", "")
                transition = seg.get("transition")

                # Build segment line: time + camera + action
                line = f"{time_range}{camera}，{action}"

                # Inline dialogue — strip voice/emotion annotations
                if dialogue:
                    clean_dialogue = self._clean_dialogue(dialogue)
                    if clean_dialogue:
                        line += f"，{clean_dialogue}"

                # Sound
                if sound:
                    line += f"。音效:{sound}"

                # Transition — strip cross-shot references, keep natural action
                if transition:
                    trans_text = self._clean_transition(transition)
                    if trans_text:
                        trans_text = trans_text.rstrip("。")
                        if not trans_text.startswith("衔接前置指令"):
                            trans_text = f"衔接前置指令:{trans_text}"
                        line += f"。{trans_text}"

                parts.append(line + "。")
        else:
            # Fallback: flat 10s segment
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
            dialogue = normalize_prompt_terms(shot.get("dialogue", ""))
            line = f"[0-10秒]镜头:{motion}，{image_prompt}。{narration}"
            if dialogue:
                line += f"，{dialogue}"
            parts.append(line + "。")

        # ── 3. Scene summary (matching industry format) ──
        scene_summary = ""
        if scene_name:
            scene_summary = f"场景:{scene_name}。"
        # Add video subtitle instruction
        parts.append(f"{scene_summary}（视频不要添加字幕）")

        # ── 4. Closing instructions ──
        parts.append("（使用中文对话，禁止添加字幕）")
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
                    print(f"    ⚠ 无参考图片，跳过")
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

                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    db.log(
                        self.agent_name, chapter_id, "clip_save_failed",
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

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
