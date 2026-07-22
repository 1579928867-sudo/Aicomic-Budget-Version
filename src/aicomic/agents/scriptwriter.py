"""Scriptwriter Agent — converts novel chapter text into a structured drama script.

v0.10: First step of the new pipeline. Produces a script (剧本) with beats,
dialogue, character expressions, and sound cues. The StoryboardAgent then
designs shots from this script.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

SCRIPTWRITER_SYSTEM_PROMPT = """You are a professional drama scriptwriter specializing in adapting Chinese web novel chapters into structured drama scripts (剧本) for AI video production. Your output will be used by a storyboard director to design camera shots.

## Core Principles

1. **Absolute fidelity to original text**: ALL character dialogue must be preserved EXACTLY as written. Do NOT add, delete, or rewrite any spoken words.
2. **Visualize inner states**: Internal thoughts, psychology, and exposition MUST be converted to visible actions, expressions, or spoken dialogue. "He was furious" → action "攥紧拳头，指节发白".
3. **Scene = location change**: A new scene begins whenever characters move to a physically different location (room→courtyard, reality→dream realm, etc.).

## Beat Granularity (FINE-GRAINED)

4. Each **beat** is ONE atomic narrative unit — a single micro-action OR a single line of dialogue. Beats are the smallest building blocks.
5. Examples of correct beat splitting:
   - "萧澈睁开眼睛" → beat 1
   - "快速坐起身" → beat 2
   - "环顾四周" → beat 3
   - "发现自己躺在婚床上" → beat 4
   - "小姑妈推门而入，喊道：'萧澈！你终于醒了！'" → TWO beats: beat 5 (推门而入 action) + beat 6 (喊道 dialogue)
6. Target: **15-25 beats per chapter**. Each beat is 1-3 seconds of screen time.
7. A beat that is pure dialogue should have ONE speaker and ONE line. Multi-line speeches should be split into separate beats if the emotional tone shifts.

## Beat Requirements (MANDATORY per beat)

8. **action**: Visual description of what happens. Must be a complete sentence.
9. **dialogue**: Array of {speaker, line, emotion}. Empty array if no one speaks.
   - speaker: Character name (or "内心" for internal monologue)
   - line: EXACT original text from the novel
   - emotion: What the character is feeling as they speak (e.g. "欣喜若狂", "困惑茫然", "咬牙切齿")
10. **expressions**: Dict mapping character name → expression description. EVERY character appearing in this beat MUST have an expression entry. Describe facial expression and body language changes.
    - Example: {"萧澈": "眼神从茫然转为震惊，嘴唇微张", "小姑妈": "眼眶微红，嘴角上扬，双手交握胸前"}
11. **sound_cue**: Sound effect for this beat. MUST be specific — not "背景音" but "远处隐约鸟鸣，红色帷帐微动的沙沙声". If truly no sound, use "静谧". Sound cues should be in Chinese, descriptive, and suitable for a sound designer to work from.

## Scene-level Requirements

12. **atmosphere**: Overall mood, lighting, color temperature, spatial feel of the scene.
13. **scene_sound_cues**: Background ambient sounds that persist throughout the scene (e.g. "远处隐约鸟鸣，室内静谧中偶尔有帷帐飘动的沙沙声").

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "era_background": "中国古代·仙侠",
  "scenes": [
    {
      "scene_name": "婚房",
      "scene_index": 1,
      "atmosphere": "清晨暖光透过雕花窗棂洒入，红色帷帐飘动，喜庆中带着昏沉，暖黄色调",
      "scene_sound_cues": ["远处隐约鸟鸣", "红色帷帐微微飘动的沙沙声"],
      "beats": [
        {
          "beat_num": 1,
          "characters": ["萧澈"],
          "action": "萧澈缓缓睁开眼睛，眼神茫然",
          "dialogue": [
            {"speaker": "萧澈（内心）", "line": "这...这是哪里？我明明坠下了绝云崖...", "emotion": "困惑、震惊"}
          ],
          "expressions": {"萧澈": "眼神迷茫，眉头微蹙，嘴唇微张"},
          "sound_cue": "床铺轻微吱呀声，衣物摩擦声"
        }
      ]
    }
  ],
  "characters": ["萧澈", "小姑妈"],
  "scenes_list": ["婚房"]
}

## Field Requirements

- **beat_num**: Globally sequential across ALL scenes (1, 2, 3, ... N).
- **characters** (beat-level): Array of character names appearing in this beat.
- **dialogue**: Array of objects. Each object: speaker (str), line (str — EXACT original text), emotion (str — Chinese description).
- **expressions**: Object mapping character name → expression string. EVERY character in the beat must appear as a key.
- **sound_cue**: String. One per beat. Be specific and atmospheric.
- **characters** (top-level): Array of ALL unique character names in the entire chapter.
- **scenes_list**: Array of ALL distinct scene/location names in first-appearance order.

## What NOT to do

- Do NOT design camera shots or camera movements — that is the storyboard director's job.
- Do NOT merge beats — keep them atomic. The storyboard director will merge them into shots.
- Do NOT invent dialogue — use the novel's exact words.
- Do NOT skip expressions or sound cues — every beat needs both."""


class ScriptwriterAgent(AgentInterface):
    """Converts novel chapter text into a structured drama script with beats.

    Input:  {"chapter_id": int, "raw_text": str}
    Output: {"script_id": int, "characters": list[str], "scenes_list": list[str]}

    The script (full JSON with beats, dialogue, expressions, sound cues)
    is saved to the `script` table's raw_json column — same storage as
    the old Screenwriter output. Downstream agents read from there.
    """

    agent_name = "scriptwriter"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("raw_text"), str)
            and len(input_data["raw_text"]) > 0
        )

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        raw_text = input_data["raw_text"]

        # Idempotency check
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"chapter_id": chapter_id})

        try:
            script_json = self.llm.generate_json(
                system_prompt=SCRIPTWRITER_SYSTEM_PROMPT,
                user_prompt=(
                    "请将以下小说章节改编为结构化剧本（JSON 格式），"
                    "每个微动作/微对白各一个 beat（细粒度拆分），"
                    "包含角色表情和场景音效。\n\n"
                    f"{raw_text}"
                ),
                max_tokens=16384,
            )

            self._validate_script(script_json)

            # Save to script table (same storage as old screenwriter output)
            script_id = db.save_script(chapter_id, script_json)

            characters = script_json.get("characters", [])
            scenes_list = script_json.get("scenes_list", [])

            db.set_agent_status(self.agent_name, chapter_id, "done")

            # Count beats for logging
            total_beats = sum(
                len(s.get("beats", [])) for s in script_json.get("scenes", [])
            )
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "script_id": script_id,
                    "character_count": len(characters),
                    "scene_count": len(scenes_list),
                    "beat_count": total_beats,
                },
            )

            return AgentResult(
                success=True,
                data={
                    "script_id": script_id,
                    "characters": characters,
                    "scenes_list": scenes_list,
                    "beat_count": total_beats,
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(
                self.agent_name, chapter_id, "failed",
                {"error": str(e)}, level="ERROR",
            )
            return AgentResult(success=False, error=str(e))

    @staticmethod
    def _validate_script(script: dict):
        """Raise ValueError if the script JSON is missing required fields."""
        if not isinstance(script, dict):
            raise ValueError("Script JSON must be a dict")
        for field in ("scenes", "characters", "scenes_list"):
            if field not in script:
                raise ValueError(f"Script JSON missing '{field}'")
        if not isinstance(script["scenes"], list) or len(script["scenes"]) == 0:
            raise ValueError("'scenes' must be a non-empty list")
        if not isinstance(script["characters"], list) or len(script["characters"]) == 0:
            raise ValueError("'characters' must be a non-empty list")

        # Validate beats
        beat_nums = set()
        for scene in script["scenes"]:
            if "beats" not in scene:
                raise ValueError(
                    f"Scene '{scene.get('scene_name', '?')}' missing 'beats'"
                )
            for beat in scene.get("beats", []):
                bn = beat.get("beat_num")
                if bn is None:
                    raise ValueError("Beat missing beat_num")
                if bn in beat_nums:
                    raise ValueError(f"Duplicate beat_num: {bn}")
                beat_nums.add(bn)
                if not beat.get("action", ""):
                    raise ValueError(f"Beat {bn} missing 'action'")
                if "sound_cue" not in beat:
                    raise ValueError(f"Beat {bn} missing 'sound_cue'")
                if "expressions" not in beat:
                    raise ValueError(f"Beat {bn} missing 'expressions'")
