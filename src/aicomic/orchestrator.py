"""Orchestrator — coordinates the multi-agent pipeline.

v0.10 pipeline: Scriptwriter → CharDesigner → SceneDesigner → OutfitManager
→ StoryboardAgent → ImageGenerator → ShotVisualizer
→ ShotVideoGenerator → VideoGenerator → VideoComposer
"""

from pathlib import Path

from .interface import AgentResult
from .bus import AgentBus
from .db.repository import Database


class Orchestrator:
    """Coordinates Agent execution through the pipeline.

    Pipeline steps (v0.10):
        1. Scriptwriter — novel → structured script (beats, dialogue, expressions, sound)
        2. Character Designer — generate design sheet prompts
        3. Scene Designer — generate scene environment descriptions
        4. Outfit Manager — detect outfit changes, tag shots
        5. Storyboard Agent — script beats → merged camera shots (≤10s, 5-8 total)
        6. Image Generator — generate design sheet + scene images (optional)
        7. Shot Visualizer — generate per-shot composite image prompts
        8. Shot Video Generator — image-to-video per shot (optional)
        9. Video Composer — stitch clips into final video (optional)

    Usage:
        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, raw_text)
        result = orchestrator.run_chapter(chapter_id, raw_text, with_video=True)
    """

    def __init__(self, bus: AgentBus, db: Database):
        self.bus = bus
        self.db = db

    def _count_existing_images(self, chapter_id: int) -> int:
        """Count character outfit + scene images that exist on disk for this chapter.

        Walks the character_outfit and scene_card tables; counts only rows
        whose image_path points to a file that exists.
        """
        count = 0
        # Count character_outfit images linked to this chapter's characters
        # via the shot_character_outfit junction table (v0.12)
        rows = self.db.conn.execute("""
            SELECT co.image_path FROM character_outfit co
            JOIN shot_character_outfit sco ON sco.character_id = co.character_id
            JOIN storyboard_shot ss ON ss.id = sco.shot_id
            JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
        """, (chapter_id,)).fetchall()
        for r in rows:
            if r["image_path"] and Path(r["image_path"]).exists():
                count += 1

        # Count scene images
        rows2 = self.db.conn.execute("""
            SELECT sc2.multi_view_image FROM scene_card sc2
            JOIN storyboard_shot ss2 ON ss2.scene_id = sc2.id
            JOIN script s2 ON s2.id = ss2.script_id
            WHERE s2.chapter_id = ? AND sc2.multi_view_image != ''
        """, (chapter_id,)).fetchall()
        for r in rows2:
            p = r["multi_view_image"]
            if p and Path(p).exists():
                count += 1
        return count

    def _verify_shot_assets(self, chapter_id: int) -> tuple[bool, list[str]]:
        """逐镜头检查视频生成所需的参考图是否全部就位。

        Returns:
            (ok, missing_items) — ok=True 表示可以安全进入视频阶段。
            missing_items 是缺失项的可读列表。
        """
        import os as _os
        import json as _json

        missing: list[str] = []
        shots = self.db.conn.execute("""
            SELECT ss.id, ss.shot_num, ss.char_ids, ss.scene_id,
                   sc.name AS scene_name, sc.multi_view_image
            FROM storyboard_shot ss
            JOIN script s ON s.id = ss.script_id
            LEFT JOIN scene_card sc ON sc.id = ss.scene_id
            WHERE s.chapter_id = ?
            ORDER BY ss.shot_num
        """, (chapter_id,)).fetchall()

        if not shots:
            return False, ["尚未生成分镜 — 请先运行「剧本与设计」阶段"]

        for shot in shots:
            shot_id = shot["id"]
            shot_num = shot["shot_num"]
            scene_name = shot["scene_name"] or f"场景#{shot['scene_id']}"

            # ── 1. 场景多景别图 ──
            scene_img = shot["multi_view_image"]
            if not scene_img or not _os.path.exists(scene_img):
                missing.append(
                    f"镜头{shot_num}: 场景「{scene_name}」缺少多景别参考图"
                )

            # ── 2. 角色设定图 ──
            outfit_rows = self.db.conn.execute("""
                SELECT cc.name, co.image_path,
                       COALESCE(co.tag, '默认') AS tag
                FROM shot_character_outfit sco
                JOIN character_card cc ON cc.id = sco.character_id
                LEFT JOIN character_outfit co ON co.character_id = sco.character_id
                    AND co.tag = COALESCE(sco.outfit_tag, '默认')
                WHERE sco.shot_id = ?
            """, (shot_id,)).fetchall()

            # Fallback for pre-junction data
            if not outfit_rows:
                try:
                    char_ids = _json.loads(shot["char_ids"] or "[]")
                except (_json.JSONDecodeError, TypeError):
                    char_ids = []
                for cid in char_ids:
                    row = self.db.conn.execute("""
                        SELECT cc.name, co.image_path,
                               COALESCE(co.tag, '默认') AS tag
                        FROM character_card cc
                        LEFT JOIN character_outfit co ON co.character_id = cc.id
                        WHERE cc.id = ?
                        ORDER BY co.id DESC LIMIT 1
                    """, (cid,)).fetchone()
                    if row:
                        outfit_rows.append(row)

            for orow in outfit_rows:
                img_path = orow["image_path"]
                if not img_path or not _os.path.exists(img_path):
                    missing.append(
                        f"镜头{shot_num}: 角色「{orow['name']}」缺少 "
                        f"{orow['tag']} 设定图"
                    )

        return (len(missing) == 0, missing)

    def _missing_clip_shots(self, script_id: int) -> list[int]:
        """Return shot numbers that don't have any video clips yet.

        Query: find all storyboard_shot rows for this script, then exclude
        those that appear in video_clip joined through storyboard_shot.
        """
        all_shots = self.db.conn.execute(
            "SELECT shot_num FROM storyboard_shot WHERE script_id = ? ORDER BY shot_num",
            (script_id,),
        ).fetchall()
        existing = set(
            r[0] for r in self.db.conn.execute(
                """SELECT ss.shot_num FROM video_clip vc
                   JOIN storyboard_shot ss ON vc.shot_id = ss.id
                   WHERE ss.script_id = ?""",
                (script_id,),
            ).fetchall()
        )
        return [s["shot_num"] for s in all_shots if s["shot_num"] not in existing]

    def _resolve_script_id(self, chapter_id: int) -> int | None:
        """Get the latest script_id for a chapter from the DB.

        Used as a fallback when a skipped agent returns minimal data.
        """
        row = self.db.conn.execute(
            "SELECT id FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        return row["id"] if row else None

    def _resolve_script_chars_scenes(self, chapter_id: int, script_id: int):
        """Resolve characters, scenes list, and beat count from a script's JSON."""
        row = self.db.conn.execute(
            "SELECT raw_json FROM script WHERE id = ?", (script_id,)
        ).fetchone()
        if not row:
            return [], [], 0
        import json
        raw = json.loads(row["raw_json"])
        chars = list(raw.get("casting", {}).keys()) if isinstance(raw.get("casting"), dict) else raw.get("characters", [])
        scenes = list(raw.get("scenes", {}).keys()) if isinstance(raw.get("scenes"), dict) else raw.get("scenes_list", [])
        beats = raw.get("beats", [])
        return chars, scenes, len(beats)

    def _check_phase(self, stop_after: str | None, agent_name: str,
                     chapter_id: int, script_id: int | None,
                     summary: dict) -> AgentResult | None:
        """If stop_after matches, return a phase-complete result instead of continuing."""
        if stop_after and stop_after == agent_name:
            return AgentResult(
                success=True,
                data={
                    "chapter_id": chapter_id,
                    "script_id": script_id,
                    "phase": f"stopped_at_{agent_name}",
                    "completed_agent": agent_name,
                    "summary": summary,
                },
            )
        return None

    def run_chapter(
        self, chapter_id: int, raw_text: str,
        with_video: bool = False,
        with_images: bool = False,
        stop_after: str | None = None,
        max_video_clips: int = 3,
    ) -> AgentResult:
        """Run the full pipeline for a single chapter.

        If stop_after is set (agent name), the pipeline stops after completing
        that agent and returns with success + data.phase='stopped_at_{agent}'.
        This enables interactive phase-by-phase execution from the web UI.

        max_video_clips: max clips per batch for shot-video-generator.
            0 = unlimited. Default 3 (free doubao daily quota).
        """
        # Fix Windows GBK encoding for emoji in print() calls
        import sys as _sys
        if _sys.platform == "win32":
            try:
                _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        self.db.log("orchestrator", chapter_id, "pipeline_started")

        # ── Auto-load raw_text from DB if caller passed empty string ──
        if not raw_text.strip():
            row = self.db.conn.execute(
                "SELECT raw_text FROM chapter WHERE id = ?", (chapter_id,)
            ).fetchone()
            if row and row["raw_text"]:
                raw_text = row["raw_text"]
            else:
                return AgentResult(success=False, error=f"Chapter {chapter_id} has no text — please upload the chapter file first")

        # ── Resume detection ──
        AGENTS_IN_ORDER = [
            "scriptwriter", "char-designer", "scene-designer",
            "outfit-manager", "storyboard-agent", "image-generator",
            "shot-visualizer", "shot-video-generator",
        ]
        completed = []
        pending = []
        for name in AGENTS_IN_ORDER:
            st = self.db.get_agent_status(name, chapter_id)
            if st == "done":
                completed.append(name)
            elif st in ("partial", "running", "failed"):
                pending.append((name, st))
            else:
                pending.append((name, st or "pending"))

        if completed:
            done_names = ", ".join(completed)
            if pending:
                p_names = ", ".join(f"{n}({s})" for n, s in pending)
                print(f"  📋 续跑检测: [{done_names}] 已完成，剩余: {p_names}")
            else:
                print(f"  📋 全部已完成，仅验证状态")

        # ── Step 1: Scriptwriter (novel → structured script) ──
        result = self.bus.run(
            "scriptwriter",
            {"chapter_id": chapter_id, "raw_text": raw_text},
            self.db,
        )

        if not result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "scriptwriter", "error": result.error},
                level="ERROR",
            )
            return result

        sw_data = result.data or {}
        script_id = sw_data.get("script_id")
        # ── Resume: if agent skipped, look up script_id from DB ──
        if not script_id:
            script_id = self._resolve_script_id(chapter_id)
            if script_id:
                characters, scenes_list, beat_count = self._resolve_script_chars_scenes(
                    chapter_id, script_id
                )
            else:
                characters, scenes_list, beat_count = [], [], 0
        else:
            characters = sw_data.get("characters", [])
            scenes_list = sw_data.get("scenes_list", [])
            beat_count = sw_data.get("beat_count", 0)

        if not script_id:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "scriptwriter", "error": "no script_id from agent or DB"},
                level="ERROR",
            )
            return AgentResult(success=False, error="No script found for this chapter")

        print(f"  ✓ Scriptwriter: 剧本 #{script_id}, {len(characters)} 角色, "
              f"{len(scenes_list)} 场景, {beat_count} beats")

        # ── Register characters and scenes (needed by downstream agents) ──
        char_name_to_id: dict[str, int] = {}
        for name in characters:
            char_id, _ = self.db.get_or_create_character(name)
            char_name_to_id[name] = char_id

        scene_name_to_id: dict[str, int] = {}
        for name in scenes_list:
            scene_id = self.db.get_or_create_scene(name)
            scene_name_to_id[name] = scene_id

        # ── Step 2: Character Designer ──
        char_result = self.bus.run(
            "char-designer",
            {
                "chapter_id": chapter_id,
                "raw_text": raw_text,
                "characters": characters,
                "script_id": script_id,
            },
            self.db,
        )

        if not char_result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "char-designer", "error": char_result.error},
                level="ERROR",
            )

        outfits_created = char_result.data.get("outfits_created", 0) if char_result.data else 0
        char_names = char_result.data.get("character_names", []) if char_result.data else []
        print(f"  ✓ Character Designer: {outfits_created} 角色设定图提示词 "
              f"({', '.join(char_names) if char_names else 'N/A'})")

        # ── Step 3: Scene Designer ──
        scene_result = self.bus.run(
            "scene-designer",
            {
                "chapter_id": chapter_id,
                "raw_text": raw_text,
                "scenes_list": scenes_list,
                "script_id": script_id,
            },
            self.db,
        )

        if not scene_result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "scene-designer", "error": scene_result.error},
                level="ERROR",
            )

        scenes_updated = scene_result.data.get("scenes_updated", 0) if scene_result.data else 0
        scene_names = scene_result.data.get("scene_names", []) if scene_result.data else []
        print(f"  ✓ Scene Designer: {scenes_updated} 场景 "
              f"({', '.join(scene_names) if scene_names else 'N/A'})")

        # ── Step 4: Outfit Manager ──
        outfit_result = self.bus.run(
            "outfit-manager",
            {"chapter_id": chapter_id, "script_id": script_id},
            self.db,
        )
        if outfit_result.success:
            outfits_gen = outfit_result.data.get("outfits_generated", 0) if outfit_result.data else 0
            shots_tagged = outfit_result.data.get("shots_tagged", 0) if outfit_result.data else 0
            if outfits_gen > 0:
                print(f"  ✓ Outfit Manager: {outfits_gen} 新服饰标签, {shots_tagged} 镜头已标记")
            else:
                print(f"  ⏭ Outfit Manager: 无换装检测")
        else:
            print(f"  ⚠ Outfit Manager: {outfit_result.error}")

        # ── Step 5: Storyboard Agent (script beats → merged camera shots) ──
        storyboard_result = self.bus.run(
            "storyboard-agent",
            {"chapter_id": chapter_id, "script_id": script_id},
            self.db,
        )

        if not storyboard_result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "storyboard-agent", "error": storyboard_result.error},
                level="ERROR",
            )
            return storyboard_result

        shots_created = storyboard_result.data.get("shots_created", 0) if (storyboard_result.data and storyboard_result.data.get("shots_created") is not None) else 0
        # 如果 agent 被跳过 (idempotent), data 里没有 shots_created → 从 DB 查
        if shots_created == 0:
            row = self.db.conn.execute(
                "SELECT COUNT(*) as c FROM storyboard_shot WHERE script_id = ?", (script_id,)
            ).fetchone()
            shots_created = row["c"] if row else 0
        print(f"  ✓ Storyboard Agent: {shots_created} 镜头 (合并后)")

        # ── Phase checkpoint: script/design complete ──
        phase_result = self._check_phase(stop_after, "storyboard-agent", chapter_id, script_id,
                                          {"characters": len(characters), "scenes": len(scenes_list),
                                           "shots": shots_created})
        if phase_result: return phase_result

        # ── Backfill: storyboard may have created scene entries for scenes
        #     not in the original scenes_list. Run scene designer on any scene
        #     that still has an empty multi_view_prompt. ──
        if raw_text:
            promptless = self.db.conn.execute(
                """SELECT sc.name FROM scene_card sc
                   JOIN storyboard_shot ss ON ss.scene_id = sc.id
                   JOIN script s ON s.id = ss.script_id
                   WHERE s.chapter_id = ? AND (sc.multi_view_prompt = '' OR sc.multi_view_prompt IS NULL)
                   GROUP BY sc.id""",
                (chapter_id,),
            ).fetchall()
            if promptless:
                missing_names = [r["name"] for r in promptless]
                print(f"  🔧 补填 {len(missing_names)} 个缺失的场景提示词: {missing_names}")
                try:
                    backfill_result = self.bus.run(
                        "scene-designer",
                        {
                            "chapter_id": chapter_id,
                            "raw_text": raw_text,
                            "scenes_list": missing_names,
                            "script_id": script_id,
                        },
                        self.db,
                    )
                    if backfill_result.success:
                        print(f"  ✓ 场景提示词补填完成")
                    else:
                        print(f"  ⚠ 场景提示词补填失败: {backfill_result.error}")
                except Exception as e:
                    print(f"  ⚠ 场景提示词补填异常: {e}")

        # ── Step 6: Image Generator (optional) ──
        img_result = None
        if with_images and script_id:
            img_result = self.bus.run(
                "image-generator",
                {"chapter_id": chapter_id, "script_id": script_id},
                self.db,
            )
            if img_result.success:
                imgs = img_result.data.get("images_generated", 0) if img_result.data else 0
                outfits_p = img_result.data.get("outfits_processed", 0) if img_result.data else 0
                scenes_p = img_result.data.get("scenes_processed", 0) if img_result.data else 0
                skipped = (img_result.data or {}).get("status") == "skipped"

                if skipped:
                    # Agent skipped via idempotency — trust that images exist
                    print(f"  ✓ Image Generator: 已跳过 (图片已存在)")
                elif imgs > 0:
                    partial_warn = ""
                    is_partial = (img_result.data or {}).get("status") == "partial"
                    if is_partial:
                        failed_o = img_result.data.get("failed_outfits", 0)
                        failed_s = img_result.data.get("failed_scenes", 0)
                        parts = []
                        if failed_o: parts.append(f"{failed_o}角色")
                        if failed_s: parts.append(f"{failed_s}场景")
                        partial_warn = f" ⚠ 部分失败({','.join(parts)})，续跑可补"
                    print(f"  ✓ Image Generator: {imgs} 张图片 "
                          f"({outfits_p} 角色设定图, {scenes_p} 场景){partial_warn}")
                else:
                    # ── v0.10 gate: agent RAN but produced 0 images → abort ──
                    print(f"  ⚠ Image Generator: 0 张图片")
                    if with_video:
                        msg = (
                            f"图片生成为 0（角色={outfits_p}, 场景={scenes_p}），"
                            f"视频生成需要参考图，中断 pipeline 避免浪费豆包额度"
                        )
                        print(f"  🛑 {msg}")
                        self.db.log(
                            "orchestrator", chapter_id, "pipeline_aborted",
                            {"reason": "no_images_for_video", "detail": msg},
                            level="ERROR",
                        )
                        return AgentResult(success=False, error=msg)
            else:
                err = img_result.error or "未知错误"
                print(f"  ✗ Image Generator: 失败 — {err}")
                # ── v0.10 gate: image gen failed → video will also fail ──
                if with_video:
                    msg = f"图片生成失败（{err}），中断 pipeline 避免浪费豆包视频额度"
                    print(f"  🛑 {msg}")
                    self.db.log(
                        "orchestrator", chapter_id, "pipeline_aborted",
                        {"reason": "image_gen_failed", "error": err},
                        level="ERROR",
                    )
                    return AgentResult(success=False, error=msg)

        # ── Step 7: Shot Visualizer ──
        shot_vis_result = self.bus.run(
            "shot-visualizer",
            {"chapter_id": chapter_id, "script_id": script_id},
            self.db,
        )

        if not shot_vis_result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "shot-visualizer", "error": shot_vis_result.error},
                level="ERROR",
            )

        shots_vis = shot_vis_result.data.get("shots_processed", 0) if shot_vis_result.data else 0
        print(f"  ✓ Shot Visualizer: {shots_vis} 镜头已生成分镜提示词")

        # ── Phase checkpoint: image generation complete ──
        phase_result = self._check_phase(stop_after, "shot-visualizer", chapter_id, script_id,
                                          {"shots_visualized": shots_vis,
                                           "images_generated": (img_result.data or {}).get("images_generated", 0) if img_result else 0})
        if phase_result: return phase_result

        # ── Step 8: Shot Video Generator (optional) ──
        shot_video_result = None
        if with_video and script_id:
            # ── 素材完整性预检：逐一核实每个分镜的场景图+角色图 ──
            assets_ok, assets_missing = self._verify_shot_assets(chapter_id)
            if not assets_ok:
                missing_detail = "；".join(assets_missing)
                msg = (
                    f"视频生成入口检查失败：{len(assets_missing)} 项素材缺失，"
                    f"请重新运行图片生成阶段补全。缺失：{missing_detail}"
                )
                print(f"  🛑 {msg}")
                self.db.log(
                    "orchestrator", chapter_id, "pipeline_aborted",
                    {"reason": "video_preflight_missing_assets",
                     "missing_count": len(assets_missing),
                     "missing_detail": assets_missing},
                    level="ERROR",
                )
                return AgentResult(success=False, error=msg)

            print(f"  ▶ Shot Video Generator: starting for script {script_id}... "
                  f"(max {max_video_clips} clips/batch)" if max_video_clips > 0 else "(unlimited)")
            shot_video_result = self.bus.run(
                "shot-video-generator",
                {
                    "chapter_id": chapter_id,
                    "script_id": script_id,
                    "max_clips_per_run": max_video_clips,
                },
                self.db,
            )
            if shot_video_result.success:
                sd = shot_video_result.data or {}
                sc = sd.get("clips_created", 0)
                st = sd.get("total_shots", 0)
                fc = sd.get("failed_count", 0)
                if sc > 0 and fc > 0:
                    # Detect which shot numbers are missing clips
                    failed_nums = self._missing_clip_shots(script_id)
                    failed_detail = ", ".join(f"镜头{n}" for n in failed_nums) if failed_nums else f"{fc}个"
                    sd["failed_shot_nums"] = failed_nums
                    sd["warning"] = f"{sc}/{st} 分镜视频成功，{failed_detail}未生成。请先解决失败的分镜后再合成视频。"
                    print(f"  ⚡ Shot Video Generator: {sc}/{st} 成功, {fc} 失败 ({failed_detail}, 可续跑)")
                elif sc > 0:
                    print(f"  ✓ Shot Video Generator: {sc}/{st} 视频片段")
                elif sd.get("skipped_all"):
                    print(f"  ⏭ Shot Video Generator: 全部已生成，跳过")
                else:
                    print(f"  ⚠ Shot Video Generator: 0/{st} 成功")
            else:
                err = shot_video_result.error or "未知错误"
                if "not registered" in err:
                    self.db.log("orchestrator", chapter_id, "pipeline_failed",
                        {"failed_at": "shot-video-generator", "error": f"Agent未注册: {err}"}, level="ERROR")
                    return AgentResult(success=False, error=f"视频生成Agent未注册，请检查config/settings.yaml中video.generator配置")
                else:
                    self.db.log("orchestrator", chapter_id, "pipeline_failed",
                        {"failed_at": "shot-video-generator", "error": err}, level="ERROR")
                    return AgentResult(success=False, error=f"视频生成失败: {err}")
            # If with_video but 0 clips produced, also fail (unless explicitly skipped or budget_paused)
            # (sd is already defined above from shot_video_result.data)
            if shot_video_result.success and sd.get("clips_created", 0) == 0 \
               and not sd.get("skipped_all") and sd.get("status") != "budget_paused":
                shots_count = len(self.db.conn.execute(
                    "SELECT id FROM storyboard_shot WHERE script_id = ?", (script_id,)
                ).fetchall())
                self.db.log("orchestrator", chapter_id, "pipeline_failed",
                    {"failed_at": "shot-video-generator", "error": "0 clips generated", "shots": shots_count}, level="ERROR")
                return AgentResult(success=False,
                    error=f"视频生成失败: 0/{shots_count} 个分镜视频生成成功。请检查豆包 Cookie 是否有效，或查看任务日志了解详情。")

            # ── Budget checkpoint: shot-video-generator stopped by clip limit ──
            if shot_video_result.success and sd.get("status") == "budget_paused":
                print(f"  ⏸ Video phase paused by budget: {sd.get('clips_created')}/{sd.get('total_shots')} clips, {sd.get('remaining_shots', '?')} remaining")
                self.db.log("orchestrator", chapter_id, "video_budget_paused",
                    {"clips_created": sd.get("clips_created"), "remaining": sd.get("remaining_shots")})

        # ── Step 9: Video Generator (legacy) ──
        video_result = None
        if with_video and script_id:
            video_result = self.bus.run(
                "video-generator",
                {"chapter_id": chapter_id, "script_id": script_id},
                self.db,
            )
            if not video_result.success:
                err = video_result.error or ""
                if "not registered" in err:
                    print(f"  ⏭ Video Generator: 由 ShotVideoGenerator 替代，跳过")
                    video_result = None
                else:
                    self.db.log(
                        "orchestrator", chapter_id, "pipeline_failed",
                        {"failed_at": "video-generator", "error": video_result.error},
                        level="ERROR",
                    )

        # ── Step 10: Video Composer (optional) ──
        composer_result = None
        composer_skipped_reason = None
        if with_video and script_id:
            clips_exist = bool(
                shot_video_result and shot_video_result.success
                and shot_video_result.data
                and shot_video_result.data.get("clips_created", 0) > 0
            )
            has_failures = bool(
                shot_video_result and shot_video_result.data
                and shot_video_result.data.get("failed_count", 0) > 0
            )
            legacy_ok = video_result and video_result.success
            if has_failures and clips_exist:
                # ── Partial success: warn user, don't auto-compose ──
                failed_nums = (shot_video_result.data or {}).get("failed_shot_nums", [])
                failed_detail = ", ".join(f"镜头{n}" for n in failed_nums) if failed_nums else "部分"
                composer_skipped_reason = (
                    f"⚠ 跳过视频合成：{failed_detail}未生成。"
                    f"解决失败的分镜后可再次运行视频阶段完成合成。"
                )
                print(f"  {composer_skipped_reason}")
                self.db.log("orchestrator", chapter_id, "composer_skipped",
                    {"reason": "partial_clips", "failed_shots": failed_nums}, level="WARNING")
            elif clips_exist or legacy_ok:
                composer_result = self.bus.run(
                    "video-composer",
                    {"chapter_id": chapter_id, "script_id": script_id},
                    self.db,
                )
                if not composer_result.success:
                    self.db.log(
                        "orchestrator", chapter_id, "pipeline_failed",
                        {"failed_at": "video-composer", "error": composer_result.error},
                        level="ERROR",
                    )

        sv_data = (shot_video_result.data or {}) if (shot_video_result and shot_video_result.success) else {}
        sv_clips = sv_data.get("clips_created", 0)
        sv_failed = sv_data.get("failed_count", 0)
        sv_warning = sv_data.get("warning", "")
        sv_failed_nums = sv_data.get("failed_shot_nums", [])

        self.db.log(
            "orchestrator", chapter_id, "pipeline_completed",
            {
                "script_id": script_id,
                "scriptwriter": "ok",
                "char_designer": "ok" if char_result.success else "failed",
                "scene_designer": "ok" if scene_result.success else "failed",
                "outfit_manager": "ok" if outfit_result.success else "failed",
                "storyboard_agent": "ok" if storyboard_result.success else "failed",
                "image_generator": "ok" if (img_result and img_result.success) else "skipped",
                "shot_visualizer": "ok" if shot_vis_result.success else "failed",
                "video_clips_created": sv_clips,
                "video_clips_failed": sv_failed,
                "video_composer_skipped": composer_skipped_reason,
            },
        )

        return AgentResult(
            success=True,
            data={
                "chapter_id": chapter_id,
                "script_id": script_id,
                "beat_count": beat_count,
                "characters": characters,
                "scenes_list": scenes_list,
                "shots_created": shots_created,
                "outfits_created": outfits_created,
                "scenes_updated": scenes_updated,
                "images_generated": img_result.data.get("images_generated", 0) if (img_result and img_result.data) else 0,
                "shots_visualized": shots_vis,
                "clips_created": (
                    sv_clips
                    or (video_result.data.get("clips_created", 0) if (video_result and video_result.success and video_result.data) else 0)
                ),
                "clips_failed": sv_failed,
                "failed_shot_nums": sv_failed_nums,
                "video_warning": sv_warning or composer_skipped_reason or "",
                "final_video_path": composer_result.data.get("final_video_path") if (composer_result and composer_result.data) else None,
                "budget_paused": sv_data.get("status") == "budget_paused",
                "budget_remaining": sv_data.get("remaining_shots", 0),
                "budget_per_run": sv_data.get("budget_per_run", 3),
                "budget_message": sv_data.get("message", ""),
            },
        )
