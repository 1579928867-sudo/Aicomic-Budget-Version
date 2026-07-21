"""Orchestrator — coordinates the multi-agent pipeline.

v0.9 pipeline: Screenwriter → CharDesigner → SceneDesigner → OutfitManager
→ ImageGenerator → ShotVisualizer → ShotVideoGenerator → VideoGenerator → VideoComposer
"""

from .interface import AgentResult
from .bus import AgentBus
from .db.repository import Database


class Orchestrator:
    """Coordinates Agent execution through the pipeline.

    Pipeline steps (v0.9):
        1. Screenwriter — generate script from raw text
        2. Character Designer — generate design sheet prompts
        3. Scene Designer — generate scene environment descriptions
        4. Outfit Manager — detect outfit changes, tag shots
        5. Image Generator — generate design sheet + scene images (optional)
        6. Shot Visualizer — generate per-shot composite image prompts
        7. Shot Video Generator — image-to-video per shot (optional)
        8. Video Composer — stitch clips into final video (optional)

    Usage:
        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, raw_text)
        result = orchestrator.run_chapter(chapter_id, raw_text, with_video=True)
    """

    def __init__(self, bus: AgentBus, db: Database):
        self.bus = bus
        self.db = db

    def run_chapter(
        self, chapter_id: int, raw_text: str,
        with_video: bool = False,
        with_images: bool = False,  # v0.6
    ) -> AgentResult:
        """Run the full pipeline for a single chapter.

        Pipeline steps (v0.9):
            1. Screenwriter — generate script from raw text
            2. Character Designer — generate design sheet prompts
            3. Scene Designer — generate scene environment descriptions
            4. Outfit Manager — detect outfit changes, tag shots
            5. Image Generator — generate design sheet + scene images (optional)
            6. Shot Visualizer — generate per-shot composite image prompts
            7. Shot Video Generator — image-to-video per shot (optional)
            8. Video Composer — stitch clips into final video (optional)

        Args:
            chapter_id: ID of the chapter to process.
            raw_text: The raw chapter text.
            with_video: If True, also run video generation (Steps 7-8).
            with_images: If True, also run image generation (Step 5).

        Returns:
            AgentResult with the final status.
        """
        self.db.log("orchestrator", chapter_id, "pipeline_started")

        # ── Step 1: Screenwriter ──
        result = self.bus.run(
            "screenwriter",
            {"chapter_id": chapter_id, "raw_text": raw_text},
            self.db,
        )

        if not result.success:
            self.db.log(
                "orchestrator", chapter_id, "pipeline_failed",
                {"failed_at": "screenwriter", "error": result.error},
                level="ERROR",
            )
            return result

        sw_data = result.data or {}
        script_id = sw_data.get("script_id")
        characters = sw_data.get("characters", [])
        scenes_list = sw_data.get("scenes_list", [])

        # Count shots for feedback
        if script_id:
            shot_row = self.db.conn.execute(
                "SELECT COUNT(*) as cnt FROM storyboard_shot WHERE script_id = ?",
                (script_id,),
            ).fetchone()
            shot_count = shot_row["cnt"] if shot_row else 0
        else:
            shot_count = 0

        print(f"  ✓ Screenwriter: 脚本 #{script_id}, {len(characters)} 角色, "
              f"{len(scenes_list)} 场景, {shot_count} 镜头")

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
            # Non-fatal — continue with scene designer even if char designer fails

        outfits_created = char_result.data.get("outfits_created", 0) if char_result.data else 0
        char_names = char_result.data.get("character_names", []) if char_result.data else []
        print(f"  ✓ Character Designer: {outfits_created} 角色设定图提示词 ({', '.join(char_names) if char_names else 'N/A'})")

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
        print(f"  ✓ Scene Designer: {scenes_updated} 场景 ({', '.join(scene_names) if scene_names else 'N/A'})")

        # ── Step 3.2: Outfit Manager (detect outfit changes, tag shots) ──
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
                print(f"  ⏭ Outfit Manager: 无换装检测, {shots_tagged} 镜头已标记")
        else:
            print(f"  ⚠ Outfit Manager: {outfit_result.error}")

        # ── Step 3.5: Image Generator (optional) ──
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
                if imgs > 0:
                    print(f"  ✓ Image Generator: {imgs} 张图片 ({outfits_p} 角色设定图, {scenes_p} 场景)")
                else:
                    print(f"  ⚠ Image Generator: 0 张图片 (无可生成内容或全部失败)")
            else:
                err = img_result.error or "未知错误"
                print(f"  ✗ Image Generator: 失败 — {err}")
                self.db.log(
                    "orchestrator", chapter_id, "pipeline_failed",
                    {"failed_at": "image-generator", "error": img_result.error},
                    level="ERROR",
                )

        # ── Step 4: Shot Visualizer ──
        shot_vis_result = self.bus.run(
            "shot-visualizer",
            {
                "chapter_id": chapter_id,
                "script_id": script_id,
            },
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

        # ── Step 4.5: Shot Video Generator (optional, image-to-video per shot) ──
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
                if sc > 0:
                    print(f"  ✓ Shot Video Generator: {sc}/{st} 视频片段")
                elif shot_video_result.data.get("skipped_all"):
                    print(f"  ⏭ Shot Video Generator: 全部已生成，跳过")
                else:
                    print(f"  ⚠ Shot Video Generator: 0/{st} 成功")
            else:
                err = shot_video_result.error or "未知错误"
                if "not registered" in err:
                    print(f"  ⏭ Shot Video Generator: 未注册（非 doubao 后端），跳过")
                else:
                    print(f"  ✗ Shot Video Generator: 失败 — {err}")
                    self.db.log(
                        "orchestrator", chapter_id, "pipeline_step_failed",
                        {"step": "shot-video-generator", "error": err},
                        level="WARNING",
                    )

        # ── Step 5: Video Generator (optional, legacy — skipped when shot-video-generator ran) ──
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
                    # doubao mode: shot-video-generator replaces this step
                    print(f"  ⏭ Video Generator: 由 ShotVideoGenerator 替代，跳过")
                    video_result = None  # Don't block composer
                else:
                    self.db.log(
                        "orchestrator", chapter_id, "pipeline_failed",
                        {"failed_at": "video-generator", "error": video_result.error},
                        level="ERROR",
                    )

        # ── Step 6: Video Composer (optional, runs if any video clips exist) ──
        composer_result = None
        if with_video and script_id:
            # Check if we have video clips (either from shot-video-gen or legacy)
            clips_exist = bool(shot_video_result and shot_video_result.success
                               and shot_video_result.data
                               and shot_video_result.data.get("clips_created", 0) > 0)
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
                "char_designer": "ok" if char_result.success else "failed",
                "scene_designer": "ok" if scene_result.success else "failed",
                "outfit_manager": "ok" if outfit_result.success else "failed",
                "image_generator": "ok" if (img_result and img_result.success) else ("skipped" if not with_images else "failed"),
                "shot_visualizer": "ok" if shot_vis_result.success else "failed",
                "shot_video_generator": "ok" if (shot_video_result and shot_video_result.success) else ("skipped" if not with_video else "failed"),
                "video_generator": "ok" if (video_result and video_result.success) else ("skipped" if (not with_video or video_result is None) else "failed"),
                "video_composer": "ok" if (composer_result and composer_result.success) else ("skipped" if not with_video else "failed"),
            },
        )

        return AgentResult(
            success=True,
            data={
                "chapter_id": chapter_id,
                "script_id": script_id,
                "characters": characters,
                "scenes_list": scenes_list,
                "outfits_created": char_result.data.get("outfits_created", 0) if char_result.data else 0,
                "outfits_detected": outfit_result.data.get("outfits_generated", 0) if (outfit_result and outfit_result.data) else 0,
                "outfits_processed": outfit_result.data.get("shots_tagged", 0) if (outfit_result and outfit_result.data) else 0,
                "scenes_updated": scene_result.data.get("scenes_updated", 0) if scene_result.data else 0,
                "images_generated": img_result.data.get("images_generated", 0) if (img_result and img_result.data) else 0,
                "outfits_processed": img_result.data.get("outfits_processed", 0) if (img_result and img_result.data) else 0,
                "scenes_processed": img_result.data.get("scenes_processed", 0) if (img_result and img_result.data) else 0,
                "shots_visualized": shot_vis_result.data.get("shots_processed", 0) if shot_vis_result.data else 0,
                "shot_video_clips": shot_video_result.data.get("clips_created", 0) if (shot_video_result and shot_video_result.data) else 0,
                "clips_created": video_result.data.get("clips_created", 0) if (video_result and video_result.data) else 0,
                "final_video_path": composer_result.data.get("final_video_path") if (composer_result and composer_result.data) else None,
                "clip_count": composer_result.data.get("clip_count", 0) if (composer_result and composer_result.data) else 0,
            },
        )
