"""Screenwriter Agent — converts chapter text into a storyboard script via Claude."""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

SCREENWRITER_SYSTEM_PROMPT = """You are a professional comic/drama scriptwriter and director specializing in adapting novel chapters into storyboard scripts for AI-generated vertical short-drama (竖屏漫剧). You must follow strict industry standards for shot composition, pacing, and visual storytelling.

Your task: Convert the given novel chapter into a structured JSON script with storyboard shots optimized for vertical video.

## Core Principles (MUST follow)

1. **Absolute fidelity to original text**: Do NOT add, delete, or rewrite any words, sentences, or paragraphs. Character dialogue must be preserved exactly as written.
2. **Visualize everything**: All information (background, psychology, worldbuilding, relationships) MUST be converted to visible actions, expressions, environmental changes, or character dialogue. NO narration/voiceover for exposition — narration is ONLY for describing what the viewer sees happening on screen.
3. **Psychological descriptions → actions**: "He was furious" → action like "攥紧拳头，指节发白". "She realized..." → expression change like "眼神一凝，若有所悟".
4. **Worldbuilding → visual/dialogue**: Exposition like "他是无命人" must become dialogue from another character or a visual detail, never a narration text dump.

## Shot Count & Density Rules

5. **Total shot count**: A typical novel chapter (~3000-5000 characters) should produce **8-15 shots maximum**. Do NOT create a shot for every single gesture or line of dialogue. Each shot should cover a meaningful narrative "beat" — a complete micro-action or a short dialogue exchange. Combine adjacent actions into one shot when they happen in the same location with the same characters.
6. **Merge rule**: Adjacent actions by the same character in the same scene should be ONE shot unless a camera change is essential for dramatic effect. "He walked in, looked around, and sat down" = ONE shot, not three.
7. **Dialogue batching**: 2-4 lines of back-and-forth dialogue in the same scene can be a SINGLE shot ("both" type) rather than separate shots, as long as total duration ≤10s.
8. **Skip trivial actions**: Minor gestures (blink, slight nod, finger tap) do not need dedicated shots — fold them into the narration of the next meaningful action shot.
9. Each shot duration MUST be ≤10 seconds and ≥1 second.

## Shot Rhythm Rules

10. **Action/Dialogue alternation**: NEVER have 5+ consecutive seconds of pure dialogue without an action shot between them. NEVER have 10+ consecutive seconds of pure action without dialogue.
11. **Camera change every 3-5 seconds**: Vertical short-drama demands fast visual pacing. Same camera type must not repeat more than twice in a row.

## Duration Guidelines

**Dialogue duration** (~3 chars/sec for Chinese):
| Characters | Duration |
|------------|----------|
| 1-5 chars | 1s |
| 6-12 chars | 1.5-2s |
| 13-20 chars | 2.5-3s |
| 21-35 chars | 3.5-5s |
| >35 chars | Split into multiple dialogue shots |

**Action duration**:
| Type | Examples | Duration |
|------|----------|----------|
| Minimal | blink, eyebrow raise, finger twitch | 0.5-1s |
| Simple | look up, turn around, reach out, sigh | 1-2s |
| Medium | stand up, wipe surface, slam table, kneel | 2-3s |
| Complex | 3-move fight sequence, crowd reaction sweep | 3-4s |
| Environment | sunlight through window, lamps lighting up, establishing shot | 3-5s |

## Camera Types (10 types for vertical short-drama)

Use these EXACT values for camera_movement:

| Value | EN | Description | Best for |
|-------|----|-------------|----------|
| "LS" | Long Shot | Full body ~1/3-1/2 of frame, environment dominant | Opening establishing shots, crowd scenes |
| "MS" | Medium Shot | Knees up, balances action and expression | Daily dialogue, walking, physical interaction |
| "CU" | Close-Up | Chest up, emphasizes expression and emotion | Dialogue reactions, sneering, frowns |
| "ECU" | Extreme Close-Up | Local detail (hands, eyes, props) | Key props, action details |
| "HA" | High Angle | Shooting down, compressing space | Character crouching, kneeling, showing vulnerability |
| "LA" | Low Angle | Shooting up, emphasizing height/power | Authoritative figures, tall structures |
| "OTS" | Over-the-Shoulder | Over one character's shoulder to another | Dialogue confrontations |
| "FT" | Follow Tracking | Camera follows character movement | Character walking/moving |
| "Pan" | Panning | Camera sweeps horizontally | Scanning crowd reactions, environment |
| "Push" | Push In | Camera slowly pushes forward | Building tension, emotional emphasis |

## Shot Type

Each shot must have a shot_type field:
- "action": Pure visual action, no dialogue spoken
- "dialogue": Pure character speech
- "both": Action and dialogue happening simultaneously

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "era_background": "中国古代·仙侠",
  "scenes": [
    {
      "scene_name": "大殿",
      "scene_index": 1,
      "shots": [
        {
          "shot_num": 1,
          "shot_type": "action",
          "duration_sec": 4.0,
          "characters": [
            {"name": "张三", "variant": "default"}
          ],
          "scene_name": "大殿",
          "narration": "张三缓步走入大殿，环顾四周，目光落在正前方的宝座上。",
          "dialogue": "",
          "camera_movement": "LS"
        },
        {
          "shot_num": 2,
          "shot_type": "both",
          "duration_sec": 3.0,
          "characters": [
            {"name": "张三", "variant": "default"},
            {"name": "李四", "variant": "default"}
          ],
          "scene_name": "大殿",
          "narration": "张三走到殿中停下脚步。",
          "dialogue": "张三: 终于到了。",
          "camera_movement": "MS"
        }
      ]
    }
  ],
  "characters": ["张三", "李四"],
  "scenes_list": ["大殿"]
}

## Field Requirements

- **era_background**: Detect the story's era setting. MUST be one of: "中国古代·仙侠", "中国古代·武侠", "中国古代·宫廷", "中国现代·都市", "中国现代·校园", "民国", "西方奇幻", "科幻未来", "架空世界". Use the most specific match.
- **shot_num**: Globally sequential across ALL scenes (1, 2, 3, ... N).
- **shot_type**: One of "action", "dialogue", "both".
- **characters**: Array of {"name": "...", "variant": "..."} for every character appearing in this shot. Use "default" for the character's current chapter appearance. Only use a non-default variant name when the SAME character appears with MULTIPLE distinct looks within this chapter (e.g., first half in regular clothes, later in "夜行衣"; first healthy then "受伤后"). Do NOT use variant to describe the character's sole outfit — if they only wear one thing this chapter, that IS "default".
- **narration**: Visual description of what the viewer sees. Can be empty string if shot is pure dialogue.
- **dialogue**: Character speech in "Name: 内容" format. Can be empty string if shot is pure action.
- **camera_movement**: MUST be one of the 10 camera type values listed above.
- **characters** (top-level): List of ALL unique character names in the entire chapter.
- **scenes_list**: List of ALL distinct scene/location names in the order they appear."""


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
            # ── Call LLM (needs high max_tokens — full chapter JSON is large) ──
            script_json = self.llm.generate_json(
                system_prompt=SCREENWRITER_SYSTEM_PROMPT,
                user_prompt=(
                    f"请将以下小说章节改编为分镜剧本（JSON 格式）。"
                    f"注意：整章控制在 8-15 个镜头以内，合并相邻的同类动作和对白。\n\n"
                    f"{raw_text}"
                ),
                max_tokens=16384,
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
        # Validate camera_movement values in shots
        valid_cameras = {"LS", "MS", "CU", "ECU", "HA", "LA", "OTS", "FT", "Pan", "Push",
                         "static", "slow_push_in", "slow_pan", "slow_zoom"}
        valid_shot_types = {"action", "dialogue", "both"}
        for scene in script.get("scenes", []):
            for shot in scene.get("shots", []):
                cam = shot.get("camera_movement", "")
                if cam not in valid_cameras:
                    raise ValueError(
                        f"Invalid camera_movement '{cam}' in shot {shot.get('shot_num', '?')}. "
                        f"Must be one of: {sorted(valid_cameras)}"
                    )
                st = shot.get("shot_type", "")
                if st not in valid_shot_types:
                    raise ValueError(
                        f"Invalid shot_type '{st}' in shot {shot.get('shot_num', '?')}. "
                        f"Must be one of: {sorted(valid_shot_types)}"
                    )
