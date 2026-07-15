"""Video Composer Agent — stitches video clips into a final video with subtitles.

Uses MoviePy to concatenate all video_clips for a script, overlay narration
and dialogue subtitles, add crossfade transitions, and output a final_video.
"""

from pathlib import Path
from typing import Any

from ..interface import AgentInterface, AgentResult
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
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"script_id": script_id})

        try:
            # ── Load video clips ──
            clips = db.get_video_clips(script_id)
            if not clips:
                raise ValueError(f"No video clips found for script_id={script_id}")

            # Filter to existing files (skip missing)
            clip_paths: list[str] = []
            for c in clips:
                cd = dict(c)
                fp = cd.get("file_path", "")
                if fp and Path(fp).exists():
                    clip_paths.append(fp)
                else:
                    db.log(
                        self.agent_name, chapter_id, "clip_missing",
                        {"clip_id": cd["id"], "file_path": fp},
                        level="WARNING",
                    )

            if not clip_paths:
                raise ValueError("No existing video clip files to compose")

            # ── Load shots for subtitle text ──
            shots = db.get_storyboard_shots(script_id)

            # ── Compose ──
            output_path = str(
                self.output_dir / f"final_{chapter_id}.mp4"
            )
            final_path = self._compose(clip_paths, shots, output_path, chapter_id, db)

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
        shots: list[dict],
        output_path: str,
        chapter_id: int,
        db: Database,
    ) -> str:
        """Compose video clips with subtitles and transitions using MoviePy.

        Override this in tests to skip actual rendering.
        """
        from moviepy import (
            VideoFileClip,
            TextClip,
            CompositeVideoClip,
            concatenate_videoclips,
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load clips
        video_clips = []
        for fp in clip_paths:
            try:
                vc = VideoFileClip(fp)
                video_clips.append(vc)
            except Exception as e:
                db.log(
                    self.agent_name, chapter_id, "clip_load_failed",
                    {"file_path": fp, "error": str(e)},
                    level="WARNING",
                )

        if not video_clips:
            raise RuntimeError("Failed to load any video clips")

        # Match shots to clips (1:1 by index)
        processed = []
        for i, clip in enumerate(video_clips):
            shot = shots[i] if i < len(shots) else {}
            narration = shot.get("narration", "")
            dialogue = shot.get("dialogue", "")

            if narration or dialogue:
                overlays = [clip]

                if narration:
                    txt_narration = TextClip(
                        text=narration,
                        font_size=24,
                        color="white",
                        bg_color="black@0.5",
                        method="caption",
                        size=(clip.w * 0.9, None),
                    ).with_position(("center", clip.h * 0.82)).with_duration(clip.duration)

                    overlays.append(txt_narration)

                if dialogue:
                    txt_dialogue = TextClip(
                        text=dialogue,
                        font_size=32,
                        color="white",
                        stroke_color="black",
                        stroke_width=2,
                        method="caption",
                        size=(clip.w * 0.9, None),
                    ).with_position(("center", clip.h * 0.70)).with_duration(clip.duration)

                    overlays.append(txt_dialogue)

                clip = CompositeVideoClip(overlays)

            # Fade in/out on each clip
            clip = clip.fadein(0.3).fadeout(0.3)

            processed.append(clip)

        # Concatenate all processed clips
        final = concatenate_videoclips(processed)
        final.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            fps=24,
        )

        # Clean up
        for c in video_clips:
            c.close()
        final.close()

        return output_path
