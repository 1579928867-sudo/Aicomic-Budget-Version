"""Video Composer Agent — stitches video clips into a final video.

v0.13: Subtitles are embedded by Doubao during video generation — no MoviePy
text overlays needed. Just concatenate with fade transitions.
"""

from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database


class VideoComposerAgent(AgentInterface):
    """Composes video clips into a final video with subtitles and transitions.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"final_video_path": str, "clip_count": int, "total_duration": float}
    """

    agent_name = "video-composer"

    def __init__(self, output_dir: str = "data/videos"):
        self.output_dir = Path(output_dir)

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        skip = begin_agent_run(self.agent_name, chapter_id, db, {"script_id": script_id})
        if skip:
            return skip

        try:
            # ── Load video clips ──
            all_clips = db.get_video_clips(script_id)
            if not all_clips:
                raise ValueError(f"No video clips found for script_id={script_id}")

            # ── Build shot_id → scene_id map from storyboard shots ──
            shots = db.get_storyboard_shots(script_id)
            shot_to_scene: dict[int, int | None] = {}
            for s in shots:
                sd = dict(s)
                shot_to_scene[sd["id"]] = sd.get("scene_id")

            # Filter to existing files, track scene_id per clip
            clip_paths: list[str] = []
            clip_scene_ids: list[int | None] = []
            for c in all_clips:
                cd = dict(c)
                fp = cd.get("file_path", "")
                if fp and Path(fp).exists():
                    clip_paths.append(fp)
                    clip_scene_ids.append(shot_to_scene.get(cd.get("shot_id")))
                else:
                    db.log(
                        self.agent_name, chapter_id, "clip_missing",
                        {"clip_id": cd["id"], "file_path": fp},
                        level="WARNING",
                    )

            if not clip_paths:
                raise ValueError("No existing video clip files to compose")

            # ── Compose ──
            output_path = str(
                self.output_dir / f"final_{chapter_id}.mp4"
            )
            final_path = self._compose(clip_paths, clip_scene_ids, output_path, chapter_id, db)

            # ── Save to DB ──
            final_video_id = db.create_final_video(chapter_id, final_path)

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "final_video_id": final_video_id,
                    "clip_count": len(clip_paths),
                    "output_path": final_path,
                },
            )

            return AgentResult(
                success=True,
                data={
                    "final_video_path": final_path,
                    "clip_count": len(clip_paths),
                    "total_duration": sum(
                        c.get("duration_sec", 0) for c in shots
                    ),
                },
            )

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(
                self.agent_name, chapter_id, "failed",
                {"error": str(e)}, level="ERROR",
            )
            return AgentResult(success=False, error=str(e))

    def _compose(
        self,
        clip_paths: list[str],
        clip_scene_ids: list[int | None],
        output_path: str,
        chapter_id: int,
        db: Database,
    ) -> str:
        """Compose video clips with scene-aware transitions.

        Fade-in on the first clip, fade-out on the last clip. Between clips:
        - Same scene: hard cut (no transition)
        - Scene change: 0.3s fade-out at clip end (next clip starts clean)

        Override this in tests to skip actual rendering.
        """
        from moviepy import (
            VideoFileClip,
            concatenate_videoclips,
        )
        from moviepy.video.fx import FadeIn, FadeOut

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load clips
        video_clips = []
        for fp in clip_paths:
            try:
                vc = VideoFileClip(fp)
                video_clips.append(vc)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                db.log(
                    self.agent_name, chapter_id, "clip_load_failed",
                    {"file_path": fp, "error": str(e)},
                    level="WARNING",
                )

        if not video_clips:
            raise RuntimeError("Failed to load any video clips")

        # ── Apply transitions: only at scene boundaries ──
        processed = []
        for i, clip in enumerate(video_clips):
            is_first = (i == 0)
            is_last = (i == len(video_clips) - 1)
            # Scene change: current clip's scene differs from next clip's scene
            scene_changes = (
                not is_last
                and clip_scene_ids[i] is not None
                and clip_scene_ids[i + 1] is not None
                and clip_scene_ids[i] != clip_scene_ids[i + 1]
            )

            effects = []
            if is_first:
                effects.append(FadeIn(0.3))
            if is_last or scene_changes:
                effects.append(FadeOut(0.3))

            if effects:
                clip = clip.with_effects(effects)
            processed.append(clip)

        # Concatenate
        final = concatenate_videoclips(processed)
        try:
            final.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=24,
            )
        finally:
            for c in video_clips:
                try:
                    c.close()
                except Exception:
                    pass
            try:
                final.close()
            except Exception:
                pass

        return output_path
