"""Storyboard Agent — designs camera shots from a structured drama script.

v0.10: Refactored from "novel→storyboard" to "script→storyboard".
Takes a ScriptwriterAgent output (script with beats, dialogue, expressions,
sound cues) and designs merged camera shots (≤10s each, 5-8 total).
"""

import json
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database

STORYBOARD_SYSTEM_PROMPT = """You are a professional storyboard director (分镜导演) for Chinese short-drama (竖屏漫剧) production. Your input is a complete drama script with fine-grained beats (each beat = one micro-action or one line of dialogue). Your output is a set of merged camera shots.

## Core Task

Read the script's beats. Merge adjacent same-scene beats into camera shots (5-8 shots total per chapter, each ≤10s). Design camera movement, shot type, and visual narration for each merged shot.

## Shot Merging Rules (CRITICAL)

1. **Merge adjacent same-scene beats**: Beats in the same scene (same scene_name) with related characters and connectable action should be merged into ONE shot.
2. **Duration cap**: Each merged shot MUST be ≤10s. Assign realistic durations:
   - Pure action beat: 1-3s depending on complexity
   - Pure dialogue: 1s per 3 Chinese characters
   - If merging would exceed 10s, split into two shots.
3. **Camera transitions**: When merging beats with different ideal camera distances, use "→" notation:
   - "CU→MS": start close-up, pull back to medium shot
   - "Push→ECU": push in from push to extreme close-up
   - "LS→FT": start wide, then follow character
   Single-camera shots just use one value (e.g. "CU", "MS").
4. **No ≤2s orphan shots**: Any resulting shot ≤2s must be merged into an adjacent shot. Minimum shot duration is 2.5s.
5. **Total shots**: 5-6 shots for the entire chapter. 7 max in rare cases. NOT 8+.

## Camera Types

Use these EXACT values (single or combined with "→"):

| Value | Description |
|-------|-------------|
| "LS" | Long Shot — full body, environment dominant |
| "MS" | Medium Shot — knees up, balanced |
| "CU" | Close-Up — chest up, expression focus |
| "ECU" | Extreme Close-Up — local detail (hands, eyes, props) |
| "HA" | High Angle — looking down |
| "LA" | Low Angle — looking up |
| "OTS" | Over-the-Shoulder — dialogue confrontations |
| "FT" | Follow Tracking — character movement |
| "Pan" | Panning — horizontal sweep |
| "Push" | Push In — camera pushes forward |

**Examples of valid camera_movement values:**
- "CU" (single camera)
- "CU→MS" (start CU, pull to MS)
- "LS→FT→CU" (establishing → follow → close-up)

## Shot Boundary Design — Anti-Mutation Rules (CRITICAL)

AI video generation is imperfect: a character's face and clothing can subtly shift between consecutive shots. The director MUST design shot boundaries so these shifts are invisible to the viewer.

1. **Cut on completed action**: Every shot must complete its micro-action before the cut. Cut on the RESULT, not mid-process.
   - BAD: Shot 1 ends "他缓缓拉开弓", Shot 2 starts "箭已在空中" → action split mid-tension feels unnatural
   - GOOD: Shot 1 ends "他松开弓弦，箭矢离弦而出", Shot 2 starts "箭矢破空飞行" → complete action, new subject, natural cut
   - BAD: "她抬手，手指触到门环——" CUT "——她推开门" → cut mid-gesture
   - GOOD: "她抬起手，握住门环，轻轻推开房门，跨过门槛" → all one shot, natural completion

2. **Buffer between same-character shots**: Never show the same character's face at the same camera distance in two consecutive shots.
   - After a character CU → insert: object detail (hands, prop, environment), another character's reaction, or LS establishing shot
   - In dialogue: alternate camera positions to avoid showing the same face twice at the same angle
   - Exceptions: rapid action sequence where the camera is following/panning (FT, Pan) and tracking the same subject through one continuous motion — this masks mutation

3. **Scene open = wide establishing shot**: The first shot of a new scene (or returning to a scene) MUST be LS or at least MS showing FULL BODY. This gives the AI a complete visual reference and anchors spatial context.
   - Scene opener: LS, environment dominant, character full body visible
   - Internal shots: any camera distance

4. **Prefer long takes over fragmentation**: Fewer shots = fewer mutation surfaces. The ideal is 5-6 shots per chapter (merged). Push the 8-10s ceiling. Only split when:
   - Duration would exceed 10s
   - Scene changes
   - An essential camera-angle shift (e.g., from wide action to intimate reaction — and even then, consider "→" notation within one shot)

## Narration (visual description)

The `narration` field describes what the viewer sees throughout the merged shot. Compose it by joining beat actions in time order:
- "萧澈缓缓睁开眼睛，眼神茫然。随后他快速坐起，环顾四周，发现自己躺在一张挂着红色幔帐的大床上。"
- Include expressions from the script: "...眼神茫然..." "...满脸喜色..."
- Do NOT repeat dialogue in narration — dialogue goes in the `dialogue` field.

## Dialogue

Merge dialogue lines from all beats in the shot. Format: "Name: 内容" separated by newlines.
- Include emotion hints from the script: "萧澈（困惑）: 小姑妈？"
- If no dialogue in the merged shot, use empty string "".

## Shot Type

- "action": no dialogue
- "dialogue": pure speech
- "both": action + dialogue simultaneously

## Characters

List every character appearing in this shot. Use "default" variant unless the script indicates outfit changes.

## Output Format

Return ONLY valid JSON:

{
  "scenes": [
    {
      "scene_name": "婚房",
      "scene_index": 1,
      "shots": [
        {
          "shot_num": 1,
          "shot_type": "both",
          "duration_sec": 8.0,
          "characters": [{"name": "萧澈", "variant": "default"}],
          "scene_name": "婚房",
          "narration": "萧澈缓缓睁开眼睛，眼神茫然，快速坐起环顾四周。红色幔帐飘动，暖黄晨光洒入房间。",
          "dialogue": "萧澈（困惑）: 这...这是哪里？",
          "camera_movement": "CU→MS"
        }
      ]
    }
  ],
  "characters": ["萧澈"],
  "scenes_list": ["婚房"]
}

## Field Requirements

- **shot_num**: Globally sequential (1, 2, 3, ... N).
- **shot_type**: "action", "dialogue", or "both".
- **duration_sec**: 2.5–10.0 seconds. Sum of merged beat durations.
- **camera_movement**: Single value or "→" separated sequence.
- **narration**: Complete visual description of the merged shot. Include expressions, atmosphere.
- **dialogue**: Merged dialogue lines, or empty string.
- **scene_name**: MUST match the script's scene_name exactly.
"""


class ScreenwriterAgent(AgentInterface):
    """Designs camera shots from a structured drama script (v0.10 StoryboardAgent).

    Input:  {"chapter_id": int, "script_id": int}
            Reads the script (ScriptwriterAgent output) from DB via script_id.
    Output: {"shots_created": int, "total_shots": int}

    Saves storyboard shots to the DB (same format as before v0.10).
    """

    agent_name = "storyboard-agent"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

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
            # ── Load the script from DB ──
            script_rows = db.conn.execute(
                "SELECT raw_json FROM script WHERE id = ?", (script_id,)
            ).fetchone()
            if not script_rows:
                raise ValueError(f"Script not found for id={script_id}")
            script_json = json.loads(script_rows["raw_json"])

            # ── Build user prompt from script beats ──
            user_prompt = self._build_user_prompt(script_json)

            # ── Call LLM ──
            storyboard_json = self.llm.generate_json(
                system_prompt=STORYBOARD_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=8192,
            )

            # ── Validate structure ──
            self._validate_storyboard(storyboard_json)

            # ── Register characters (may already exist, idempotent) ──
            char_name_to_id: dict[str, int] = {}
            characters = storyboard_json.get("characters", [])
            for name in characters:
                char_id, _ = db.get_or_create_character(name)
                char_name_to_id[name] = char_id

            # ── Register scenes (may already exist) ──
            scene_name_to_id: dict[str, int] = {}
            scenes_list = storyboard_json.get("scenes_list", [])
            for name in scenes_list:
                scene_id = db.get_or_create_scene(name)
                scene_name_to_id[name] = scene_id

            # ── Flatten & save storyboard shots ──
            shots_flat: list[dict] = []
            for scene in storyboard_json.get("scenes", []):
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
                        "camera_movement": shot.get("camera_movement", "MS"),
                        "duration_sec": shot.get("duration_sec", 8.0),
                        "char_ids": char_ids,
                        "scene_id": scene_id,
                    })

            db.save_storyboard_shots(script_id, shots_flat)

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
                    "shots_created": len(shots_flat),
                    "total_shots": len(shots_flat),
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(
                self.agent_name, chapter_id, "failed",
                {"error": str(e)}, level="ERROR",
            )
            return AgentResult(success=False, error=str(e))

    def _build_user_prompt(self, script_json: dict) -> str:
        """Build the LLM user prompt from script beats."""
        parts = []
        parts.append("## 剧本\n")
        parts.append(f"时代背景: {script_json.get('era_background', '中国古代·仙侠')}")

        for scene in script_json.get("scenes", []):
            sn = scene.get("scene_name", "?")
            atm = scene.get("atmosphere", "")
            parts.append(f"\n### 场景: {sn}")
            parts.append(f"氛围: {atm}")
            parts.append(f"环境音: {scene.get('scene_sound_cues', [])}")

            beats = scene.get("beats", [])
            parts.append(f"Beats ({len(beats)}个):")
            for b in beats:
                bn = b.get("beat_num", "?")
                action = b.get("action", "")
                dialogue = b.get("dialogue", [])
                expr = b.get("expressions", {})
                sound = b.get("sound_cue", "")

                parts.append(f"  Beat {bn}: {action}")
                if dialogue:
                    for d in dialogue:
                        parts.append(
                            f"    💬 {d.get('speaker','?')}"
                            f"（{d.get('emotion','')}）: {d.get('line','')}"
                        )
                if expr:
                    for char, exp in expr.items():
                        parts.append(f"    🎭 {char}: {exp}")
                if sound:
                    parts.append(f"    🔊 {sound}")

        parts.append(
            "\n请将以上剧本 beats 合并为 5-8 个分镜镜头（每个 ≤10s），"
            "同场景相邻 beats 合并在一起。"
        )
        return "\n".join(parts)

    @staticmethod
    def _validate_storyboard(script: dict):
        """Raise ValueError if the storyboard JSON is missing required fields."""
        if not isinstance(script, dict):
            raise ValueError("Storyboard JSON must be a dict")
        for field in ("scenes", "characters", "scenes_list"):
            if field not in script:
                raise ValueError(f"Storyboard JSON missing '{field}'")

        # Validate shots — camera_movement now accepts "→" sequences
        valid_cameras = {
            "LS", "MS", "CU", "ECU", "HA", "LA", "OTS", "FT", "Pan", "Push",
            "Pull", "Zoom",
            "static",
        }
        valid_shot_types = {"action", "dialogue", "both"}

        for scene in script.get("scenes", []):
            for shot in scene.get("shots", []):
                # Check camera_movement: split on "→", "->", or similar arrow chars
                # (LLMs occasionally use different arrow variants or encoding)
                cam = shot.get("camera_movement", "")
                import re
                segments = re.split(r"\s*[-–—→⇒➔>]+\s*", cam)
                for seg in segments:
                    seg = seg.strip()
                    if seg and seg not in valid_cameras:
                        raise ValueError(
                            f"Invalid camera '{seg}' in shot "
                            f"{shot.get('shot_num', '?')} (full: '{cam}')"
                        )
                st = shot.get("shot_type", "")
                if st not in valid_shot_types:
                    raise ValueError(
                        f"Invalid shot_type '{st}' in shot {shot.get('shot_num', '?')}"
                    )
                dur = shot.get("duration_sec", 0)
                if dur < 1 or dur > 10:
                    raise ValueError(
                        f"Shot {shot.get('shot_num', '?')} duration {dur}s "
                        f"out of range (1-10s)"
                    )
