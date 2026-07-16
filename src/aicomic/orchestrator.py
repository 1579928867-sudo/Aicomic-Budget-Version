"""Orchestrator — coordinates the multi-agent pipeline.

v0.5 pipeline: Screenwriter → CharDesigner → SceneDesigner → ShotVisualizer → VideoGenerator → VideoComposer
"""

import json

from .interface import AgentResult
from .bus import AgentBus
from .db.repository import Database


class Orchestrator:
    """Coordinates Agent execution through the pipeline.

    Pipeline steps (v0.5):
        1. Screenwriter — generate script from raw text
        2. Character Designer — generate appearance descriptions
        3. Scene Designer — generate scene environment descriptions
        4. Shot Visualizer — generate per-shot composite image prompts
        5. Video Generator — generate video clips from shots (optional)
        6. Video Composer — stitch clips into final video with subtitles (optional)

    Usage:
        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, raw_text)
        result = orchestrator.run_chapter(chapter_id, raw_text, with_video=True)
    """

    def __init__(self, bus: AgentBus, db: Database):
        self.bus = bus
        self.db = db

    def _extract_character_variants(self, script_id: int) -> dict[str, list[str]]:
        """Scan storyboard shots for character variants (non-default).

        Returns mapping of character_name → list of unique variant names.
        """
        variants: dict[str, set[str]] = {}

        script_rows = self.db.conn.execute(
            "SELECT raw_json FROM script WHERE id = ?", (script_id,)
        ).fetchone()
        if script_rows:
            raw = json.loads(script_rows["raw_json"])
            for scene in raw.get("scenes", []):
                for shot in scene.get("shots", []):
                    for char in shot.get("characters", []):
                        name = char.get("name", "")
                        variant = char.get("variant", "default")
                        if variant != "default":
                            if name not in variants:
                                variants[name] = set()
                            variants[name].add(variant)

        return {name: sorted(vs) for name, vs in variants.items()}

    def run_chapter(
        self, chapter_id: int, raw_text: str,
        with_video: bool = False,
        with_images: bool = False,  # v0.6
    ) -> AgentResult:
        """Run the full pipeline for a single chapter.

        Pipeline steps (v0.5):
            1. Screenwriter — generate script from raw text
            2. Character Designer — generate appearance descriptions
            3. Scene Designer — generate scene environment descriptions
            3.5. Image Generator — generate real images from view prompts (optional)
            4. Shot Visualizer — generate per-shot composite image prompts
            5. Video Generator — generate video clips (optional, only if with_video=True)
            6. Video Composer — stitch clips into final video with subtitles (optional)

        Args:
            chapter_id: ID of the chapter to process.
            raw_text: The raw chapter text.
            with_video: If True, also run video generation (Steps 5-6).
            with_images: If True, also run image generation (Step 3.5).

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

        # ── Step 2: Character Designer ──
        char_variants = {}
        if script_id:
            char_variants = self._extract_character_variants(script_id)

        char_result = self.bus.run(
            "char-designer",
            {
                "chapter_id": chapter_id,
                "raw_text": raw_text,
                "characters": characters,
                "script_id": script_id,
                "character_variants": char_variants,
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

        # ── Step 3.5: Image Generator (optional) ──
        img_result = None
        if with_images and script_id:
            img_result = self.bus.run(
                "image-generator",
                {"chapter_id": chapter_id, "script_id": script_id},
                self.db,
            )
            if not img_result.success:
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

        # ── Step 5: Video Generator (optional) ──
        video_result = None
        if with_video and script_id:
            video_result = self.bus.run(
                "video-generator",
                {"chapter_id": chapter_id, "script_id": script_id},
                self.db,
            )
            if not video_result.success:
                self.db.log(
                    "orchestrator", chapter_id, "pipeline_failed",
                    {"failed_at": "video-generator", "error": video_result.error},
                    level="ERROR",
                )

        # ── Step 6: Video Composer (optional, only when video was generated) ──
        composer_result = None
        if with_video and script_id and video_result and video_result.success:
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
                "image_generator": "ok" if (img_result and img_result.success) else ("skipped" if not with_images else "failed"),
                "shot_visualizer": "ok" if shot_vis_result.success else "failed",
                "video_generator": "ok" if (video_result and video_result.success) else ("skipped" if not with_video else "failed"),
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
                "char_variants_created": char_result.data.get("variants_created", 0) if char_result.data else 0,
                "scenes_updated": scene_result.data.get("scenes_updated", 0) if scene_result.data else 0,
                "images_generated": img_result.data.get("images_generated", 0) if (img_result and img_result.data) else 0,
                "variants_processed": img_result.data.get("variants_processed", 0) if (img_result and img_result.data) else 0,
                "scenes_processed": img_result.data.get("scenes_processed", 0) if (img_result and img_result.data) else 0,
                "shots_visualized": shot_vis_result.data.get("shots_processed", 0) if shot_vis_result.data else 0,
                "clips_created": video_result.data.get("clips_created", 0) if (video_result and video_result.data) else 0,
                "final_video_path": composer_result.data.get("final_video_path") if (composer_result and composer_result.data) else None,
                "clip_count": composer_result.data.get("clip_count", 0) if (composer_result and composer_result.data) else 0,
            },
        )
