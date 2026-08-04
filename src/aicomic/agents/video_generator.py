"""Video Generator Agent — converts storyboard shots into video clips.

Loads shots with image_prompts, optimizes them for video generation
via LLM, and calls the VideoGenerator service to produce video clips.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database
from ..doubao.client import VideoGenerator

VIDEO_PROMPT_OPTIMIZER_SYSTEM = """You are a professional video prompt engineer specializing in AI video generation (AI 视频生成). Your task is to convert static image-generation prompts into dynamic video-generation prompts.

## Key Differences: Image vs Video Prompts

**Image prompts** describe a single frozen moment:
- Static composition, fixed pose, single frame
- "特写镜头，人物面部占画面主体..."
- "中景，人物居中，暖色调..."

**Video prompts** describe continuous motion over time:
- Camera movement (push in, pull out, pan, zoom)
- Character movement (walking, turning, gesturing, expressions changing)
- Environmental changes (lighting shifts, wind, particles, dust)
- Temporal progression (a sequence of actions)

## Rules

1. **Start from the image_prompt**, keep all visual details (character appearance, scene, lighting, style).
2. **Add motion** based on camera_movement and the shot's narration:
   - LS/Pan: describe sweeping landscape, camera gliding across scene
   - MS: character body movement, walking, gesturing
   - CU: facial expression changes, head turns, eye movement, subtle breathing
   - ECU: micro-movements — fingers twitching, lips parting, eyelid flutter
   - Push: camera slowly moving forward, background blurring into bokeh
   - FT: camera tracking with character, background parallax
   - HA/LA: dramatic angle with slow tilt
   - OTS: subtle shoulder/head shift of foreground character
3. **Duration-aware**: A 3s shot needs 1 sharp action. A 8s shot can describe a sequence of 2-3 beats.
4. **Keep it dense**: Video prompts should be 100-200 Chinese characters. Don't pad; every word adds motion detail.
5. **Style prefix**: Keep era style prefix (古代仙侠风格). Add "高质量AI视频，流畅运镜，电影级画面".
6. **Output ONLY the video prompt** — no composition notes, no mood tags. Just the prompt.

## Output Format

Return ONLY valid JSON (no other text):

{
  "shots": [
    {"shot_num": 1, "video_prompt": "古代仙侠风格，高质量AI视频..."},
    {"shot_num": 2, "video_prompt": "古代仙侠风格，高质量AI视频..."}
  ]
}
"""


class VideoGeneratorAgent(AgentInterface):
    """Generates video clips from storyboard shots using AI video generation.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"clips_created": int, "total_shots": int}
    """

    agent_name = "video-generator"

    def __init__(self, llm_client: Any, video_generator: VideoGenerator):
        """Initialize with LLM for prompt optimization and VideoGenerator for production.

        Args:
            llm_client: LLM client with generate_json() method for prompt optimization.
            video_generator: VideoGenerator implementation for actual video production.
        """
        self.llm = llm_client
        self.video_gen = video_generator

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
            # ── Load shots from DB ──
            shots = db.get_storyboard_shots(script_id)
            if not shots:
                raise ValueError(f"No storyboard shots for script_id={script_id}")

            # Filter shots that already have video clips
            shots_to_generate = []
            already_done = []
            for s in shots:
                sd = dict(s)
                existing = db.get_video_clips_for_shot(sd["id"])
                if existing:
                    already_done.append(sd["shot_num"])
                else:
                    shots_to_generate.append(sd)

            if not shots_to_generate:
                db.log(
                    self.agent_name, chapter_id, "skipped",
                    {"reason": "all shots already have video clips"},
                )
                db.set_agent_status(self.agent_name, chapter_id, "done")
                return AgentResult(
                    success=True,
                    data={"clips_created": 0, "total_shots": len(shots), "skipped_all": True},
                )

            # ── Step A: Optimize image_prompts → video_prompts via LLM ──
            optimized = self._optimize_prompts(shots_to_generate)

            # ── Step B: Generate video clips ──
            clips_created = 0
            for s in shots_to_generate:
                sd = dict(s)
                shot_num = sd["shot_num"]
                image_prompt = sd.get("image_prompt", "")
                duration = sd.get("duration_sec", 5.0)

                # Use optimized prompt if available, fall back to image_prompt
                video_prompt = optimized.get(shot_num, image_prompt)

                result = self.video_gen.generate(
                    prompt=video_prompt,
                    duration_sec=duration,
                )

                if result.success:
                    db.create_video_clip(
                        shot_id=sd["id"],
                        file_path=result.file_path,
                        duration_sec=result.duration_sec,
                    )
                    clips_created += 1
                else:
                    db.log(
                        self.agent_name, chapter_id, "shot_failed",
                        {"shot_num": shot_num, "error": result.error},
                        level="WARNING",
                    )

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "clips_created": clips_created,
                    "total_shots": len(shots),
                    "already_done": len(already_done),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "clips_created": clips_created,
                    "total_shots": len(shots),
                    "already_done": len(already_done),
                },
            )

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))

    def _optimize_prompts(self, shots: list[dict]) -> dict[int, str]:
        """Use LLM to optimize image_prompts into video_prompts.

        Returns a mapping of shot_num → video_prompt.
        """
        # Build shot summary for LLM
        lines = []
        for s in shots:
            sd = dict(s)
            lines.append(
                f"Shot #{sd['shot_num']} [{sd.get('camera_movement', 'MS')}] "
                f"({sd.get('duration_sec', 5.0)}s)\n"
                f"  image_prompt: {sd.get('image_prompt', '')}\n"
                f"  narration: {sd.get('narration', '')}\n"
                f"  dialogue: {sd.get('dialogue', '')}"
            )

        user_prompt = (
            "请将以下静态画面提示词转换为动态视频生成提示词（JSON 格式）：\n\n"
            + "\n\n".join(lines)
        )

        result = self.llm.generate_json(
            system_prompt=VIDEO_PROMPT_OPTIMIZER_SYSTEM,
            user_prompt=user_prompt,
            max_tokens=8192,
        )

        # Parse result
        optimized: dict[int, str] = {}
        for item in result.get("shots", []):
            sn = item.get("shot_num")
            vp = item.get("video_prompt", "")
            if sn and vp:
                optimized[sn] = vp

        return optimized
