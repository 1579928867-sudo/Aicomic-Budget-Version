"""Screenwriter Agent — converts chapter text into a storyboard script via Claude."""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

SCREENWRITER_SYSTEM_PROMPT = """You are a professional comic/drama scriptwriter specializing in adapting novel chapters into storyboard scripts for AI-generated video.

Your task: Convert the given novel chapter into a structured JSON script with storyboard shots.

## Rules

1. Each shot must be ≤10 seconds of screen time (duration_sec).
2. Each shot must specify: characters present (with variant), scene location, dialogue (if any), narration (if any), camera movement.
3. Camera movements MUST be one of: "static", "slow_push_in", "slow_pan", "slow_zoom".
4. Extract ALL characters mentioned in the chapter into the "characters" list.
5. Extract ALL distinct scenes/locations into the "scenes_list".
6. Group shots by scene. Use the "scenes" array at top level — each scene has a scene_name, scene_index, and shots array.
7. For each character in a shot, include the "variant" field — use "default" unless the character is described with different clothing/appearance than their standard look. If they change clothes, disguise, get injured, or otherwise change appearance, create a descriptive variant name (e.g., "夜行衣", "受伤后").
8. shot_num must be globally sequential across all scenes (not per-scene).
9. narration is scene description / narration text (what the viewer sees happening). dialogue is character speech. A shot can have narration OR dialogue OR both.

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "scenes": [
    {
      "scene_name": "大殿",
      "scene_index": 1,
      "shots": [
        {
          "shot_num": 1,
          "duration_sec": 8.0,
          "characters": [
            {"name": "张三", "variant": "default"},
            {"name": "李四", "variant": "default"}
          ],
          "scene_name": "大殿",
          "narration": "张三缓步走入大殿，环顾四周。",
          "dialogue": "张三: 终于到了。",
          "camera_movement": "slow_push_in"
        }
      ]
    }
  ],
  "characters": ["张三", "李四"],
  "scenes_list": ["大殿"]
}"""


class ScreenwriterAgent(AgentInterface):
    """Converts chapter text into a storyboard script using Claude.

    Input:  {"chapter_id": int, "raw_text": str}
    Output: {"script_id": int, "characters": list[str], "scenes_list": list[str]}
    """

    agent_name = "screenwriter"

    def __init__(self, llm_client: Any):
        """Initialize with a ClaudeClient-compatible LLM client.

        Args:
            llm_client: An object with a generate_json(system_prompt, user_prompt, max_tokens) method.
        """
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("raw_text"), str)
            and len(input_data["raw_text"]) > 0
        )

    def execute(
        self, input_data: dict[str, Any], db: Database
    ) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        raw_text = input_data["raw_text"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"chapter_id": chapter_id})

        try:
            # ── Call Claude ──
            script_json = self.llm.generate_json(
                system_prompt=SCREENWRITER_SYSTEM_PROMPT,
                user_prompt=f"请将以下小说章节改编为分镜剧本（JSON 格式）：\n\n{raw_text}",
            )

            # ── Validate script structure ──
            self._validate_script_structure(script_json)

            # ── Save script ──
            script_id = db.save_script(chapter_id, script_json)

            # ── Register characters ──
            char_name_to_id: dict[str, int] = {}
            characters = script_json.get("characters", [])
            if not characters:
                raise ValueError("Script JSON missing 'characters' list")
            for name in characters:
                char_id, _ = db.get_or_create_character(name)
                char_name_to_id[name] = char_id

            # ── Register scenes ──
            scene_name_to_id: dict[str, int] = {}
            scenes_list = script_json.get("scenes_list", [])
            if not scenes_list:
                raise ValueError("Script JSON missing 'scenes_list'")
            for name in scenes_list:
                scene_id = db.get_or_create_scene(name)
                scene_name_to_id[name] = scene_id

            # ── Flatten & save storyboard shots ──
            shots_flat: list[dict] = []
            for scene in script_json.get("scenes", []):
                scene_name = scene.get("scene_name", "")
                scene_id = scene_name_to_id.get(scene_name)
                for shot in scene.get("shots", []):
                    shot_chars = shot.get("characters", [])
                    char_ids = [
                        char_name_to_id[c["name"]]
                        for c in shot_chars
                        if c["name"] in char_name_to_id
                    ]
                    shots_flat.append({
                        "shot_num": shot["shot_num"],
                        "narration": shot.get("narration", ""),
                        "dialogue": shot.get("dialogue", ""),
                        "camera_movement": shot.get("camera_movement", "static"),
                        "duration_sec": shot.get("duration_sec", 8.0),
                        "char_ids": char_ids,
                        "scene_id": scene_id,
                    })

            db.save_storyboard_shots(script_id, shots_flat)

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "script_id": script_id,
                    "shot_count": len(shots_flat),
                    "character_count": len(characters),
                    "scene_count": len(scenes_list),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "script_id": script_id,
                    "characters": characters,
                    "scenes_list": scenes_list,
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))

    @staticmethod
    def _validate_script_structure(script: dict):
        """Raise ValueError if the script JSON is missing required fields."""
        if not isinstance(script, dict):
            raise ValueError("Script JSON must be a dict")
        if "scenes" not in script:
            raise ValueError("Script JSON missing 'scenes'")
        if "characters" not in script:
            raise ValueError("Script JSON missing 'characters'")
        if "scenes_list" not in script:
            raise ValueError("Script JSON missing 'scenes_list'")
