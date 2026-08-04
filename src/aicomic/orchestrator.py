"""Orchestrator — coordinates the multi-agent pipeline.

v0.10 pipeline: Scriptwriter → CharDesigner → SceneDesigner → OutfitManager
→ StoryboardAgent → ImageGenerator → ShotVisualizer
→ ShotVideoGenerator → VideoGenerator → VideoComposer
"""

import json
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
        raw = json.loads(row["raw_json"])
        chars = list(raw.get("casting", {}).keys()) if isinstance(raw.get("casting"), dict) else raw.get("characters", [])
        scenes = list(raw.get("scenes", {}).keys()) if isinstance(raw.get("scenes"), dict) else raw.get("scenes_list", [])
        beats = raw.get("beats", [])
        return chars, scenes, len(beats)

    def run_chapter(
        self, chapter_id: int, raw_text: str,
        with_video: bool = False,
    ) -> AgentResult:
        """Run the full pipeline for a single chapter."""
        self.db.log("orchestrator", chapter_id, "pipeline_started")

        # ── Early dependency check: MoviePy for video composition ──
        if with_video:
            try:
                from moviepy import VideoFileClip  # noqa: F401
            except ImportError:
                msg = "moviepy not installed. Run: pip install moviepy"
                self.db.log("orchestrator", chapter_id, "pipeline_failed",
                           {"failed_at": "early_check", "error": msg}, level="ERROR")
                return AgentResult(success=False, error=msg)

        # ── Resume detection ──
        AGENTS_IN_ORDER = [
            "scriptwriter", "char-designer", "scene-designer",
            "storyboard-agent", "outfit-manager",
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
            return char_result

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
            return scene_result

        scenes_updated = scene_result.data.get("scenes_updated", 0) if scene_result.data else 0
        scene_names = scene_result.data.get("scene_names", []) if scene_result.data else []
        print(f"  ✓ Scene Designer: {scenes_updated} 场景 "
              f"({', '.join(scene_names) if scene_names else 'N/A'})")

        # ── Step 4: Storyboard Agent (script beats → merged camera shots) ──
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

        shots_created = storyboard_result.data.get("shots_created", 0) if storyboard_result.data else 0
        print(f"  ✓ Storyboard Agent: {shots_created} 镜头 (合并后)")

        # ── Step 5: Outfit Manager (depends on storyboard shots) ──
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
            # Non-fatal but log — continues after storyboard ensures shots exist
            self.db.log(
                "orchestrator", chapter_id, "pipeline_warning",
                {"failed_at": "outfit-manager", "error": outfit_result.error},
                level="WARNING",
            )

        # ── Step 6: Shot Visualizer ──
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
            return shot_vis_result

        shots_vis = shot_vis_result.data.get("shots_processed", 0) if shot_vis_result.data else 0
        print(f"  ✓ Shot Visualizer: {shots_vis} 镜头已生成分镜提示词")

        # ── Step 8: Shot Video Generator (optional) ──
        shot_video_result = None
        if with_video and script_id:
            shot_video_result = self.bus.run(
                "shot-video-generator",
                {"chapter_id": chapter_id, "script_id": script_id},
                self.db,
            )
            if shot_video_result.success:
                sc = shot_video_result.data.get("clips_created", 0) if shot_video_result.data else 0
                st = shot_video_result.data.get("total_shots", 0) if shot_video_result.data else 0
                fc = shot_video_result.data.get("failed_count", 0) if shot_video_result.data else 0
                if sc > 0 and fc > 0:
                    print(f"  ⚡ Shot Video Generator: {sc}/{st} 成功, {fc} 失败 (可续跑)")
                elif sc > 0:
                    print(f"  ✓ Shot Video Generator: {sc}/{st} 视频片段")
                elif shot_video_result.data.get("skipped_all"):
                    print(f"  ⏭ Shot Video Generator: 全部已生成，跳过")
                else:
                    print(f"  ⚠ Shot Video Generator: 0/{st} 成功")
            else:
                err = shot_video_result.error or "未知错误"
                if "not registered" in err:
                    print(f"  ⏭ Shot Video Generator: 未注册，跳过")
                else:
                    print(f"  ✗ Shot Video Generator: 失败 — {err}")

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
        if with_video and script_id:
            clips_exist = bool(
                shot_video_result and shot_video_result.success
                and shot_video_result.data
                and shot_video_result.data.get("clips_created", 0) > 0
            )
            legacy_ok = video_result and video_result.success
            if clips_exist or legacy_ok:
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

        self.db.log(
            "orchestrator", chapter_id, "pipeline_completed",
            {
                "script_id": script_id,
                "scriptwriter": "ok",
                "char_designer": "ok" if char_result.success else "failed",
                "scene_designer": "ok" if scene_result.success else "failed",
                "outfit_manager": "ok" if outfit_result.success else "failed",
                "storyboard_agent": "ok" if storyboard_result.success else "failed",
                "shot_visualizer": "ok" if shot_vis_result.success else "failed",
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
                "shots_visualized": shots_vis,
                "clips_created": (
                    shot_video_result.data.get("clips_created", 0)
                    if (shot_video_result and shot_video_result.success and shot_video_result.data)
                    else video_result.data.get("clips_created", 0)
                    if (video_result and video_result.success and video_result.data)
                    else 0
                ),
                "final_video_path": composer_result.data.get("final_video_path") if (composer_result and composer_result.data) else None,
            },
        )
