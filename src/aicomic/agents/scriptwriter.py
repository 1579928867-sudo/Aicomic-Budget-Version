"""Scriptwriter Agent — converts novel chapter text into a structured drama script.

v0.10: First step of the new pipeline. Produces a script (剧本) with beats,
dialogue, character expressions, and sound cues. The StoryboardAgent then
designs shots from this script.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database

SCRIPTWRITER_SYSTEM_PROMPT = """You are a professional drama scriptwriter specializing in adapting Chinese web novel chapters into structured drama scripts (剧本) for AI video production. Each beat you write will become ONE video generation unit (~8-10 seconds of AI-generated footage).

## Core Principles

1. **Absolute fidelity to original text**: ALL character dialogue must be preserved EXACTLY as written. Do NOT add, delete, or rewrite any spoken words.
2. **Visualize inner states**: Internal thoughts, psychology, and exposition MUST be converted to visible actions, expressions, or spoken dialogue.
3. **Scene = environment change**: A new scene begins whenever the physical space fundamentally changes — different room, reality→dream realm, indoor→outdoor, normal→vision/flashback.

## Beat Granularity — VIDEO NATIVE (CRITICAL)

4. Each beat is a **complete 7-10 second visual paragraph** — one full narrative moment that stands alone as a video segment. It's NOT a micro-action, it's the FULL visual arc of one coherent moment.
5. A single beat should contain enough visual and emotional progression to fill 7-10 seconds: opening state → development → closing state. Think "one complete mini-story per beat".
6. Target: **8-12 beats per chapter**. Never less than 6, never more than 15.
7. A beat can include multiple micro-actions and dialogue lines IF they belong to the same continuous moment and same physical space. The test: "Can I film this as one unbroken camera shot?"

### How to group into video-native beats:

WRONG (too fine, old micro-beat style):
- Beat: "萧澈睁开眼睛" → Beat: "坐起身" → Beat: "环顾四周"
RIGHT (one complete video-native beat):
- Beat: "萧澈从昏迷中苏醒，缓缓睁开眼，眼神迷茫。他快速坐起身，警觉地环顾四周——发现自己躺在挂着红色幔帐的婚床上，困惑不已。"

WRONG (dialogue split off):
- Beat: "小姑妈推门而入" → Beat: "小姑妈喊道：'你醒了！'"
RIGHT (one complete video-native beat):
- Beat: "小姑妈推门而入，快步走到床边，脸上带着惊喜和关切。她俯身看向萧澈，喊道：'小澈！你……你醒了！'"

## Scene Splitting Rules (CRITICAL — fix scene omission bugs)

8. **Environment changes DEMAND a new scene**:
   - A green world appearing from a palm mark → NEW scene "天毒珠内部·碧绿天地"
   - A memory/flashback that shows different time/space → NEW scene or marked with visual_fx
   - Going from room → courtyard → hall → ALL separate scenes
9. Each scene must have its own **atmosphere**, **scene_sound_cues**, and at least one beat. Even a 1-beat scene is valid.
10. Before finalizing, verify: "Are ALL distinct physical/virtual spaces covered as separate scenes?"

## Space Boundary = Beat Cut Point (CRITICAL — fix cross-space beats)

11. **A single beat MUST NOT span multiple physical spaces**. One beat = one location. Period.
12. **Cross-space transitions MUST be split into TWO beats**:
    - Beat A (exit): the character's eyes close, the world dissolves/fades, the screen goes dark or is consumed by light — still in the OLD space. Scene = OLD space.
    - Beat B (arrival): eyes open, the character finds themselves in a NEW space, reacts to the new environment. Scene = NEW space.
13. **Natural cut points for space transitions**:
    - Eyes closing / eyes opening — the most natural and universal cut
    - Screen consumed by light/darkness — e.g. "绿光吞没画面"
    - Door closing behind character, then opening from the other side
    - These are NOT continuity breaks — they are how film editing works. Audiences naturally accept them.
14. **Example of CORRECT splitting**:
    BEFORE (WRONG, one beat spans two spaces):
    - Beat: "萧澈闭眼，绿色世界溃散，再睁眼已回到婚房，看着掌心的印记笑了"
    AFTER (CORRECT, two beats):
    - Beat A (天毒珠内部): "萧澈闭上眼睛，意念微动。周围的绿色世界快速溃散消散，绿光褪去，视野归于黑暗。"
    - Beat B (婚房): "萧澈缓缓睁开眼睛，视线里已是熟悉的婚房。他低头看着掌心浅绿色印记，缓缓笑了起来——眼神坚定而释然。"

15. **This rule applies universally to ALL cross-space transitions**: entering/exiting dream realms, waking from visions, stepping through doors/gates/portals, flashback end returning to reality, going indoor ↔ outdoor, etc. If the floor/light/atmosphere changes, it's a new beat.

## Memory, Flashback & Inner World (CRITICAL for visual clarity)

11. When the character experiences memories, flashbacks, or visions, the beat MUST include:
    - **visual_fx**: Concrete visual treatment. Examples: "叠影闪回，画面褪色偏黄，碎片化记忆画面快速交替" / "绿光爆炸式扩散，画面抖动，视野被碧绿吞没" / "画面虚化抖动，黑边收缩，闪回碎片穿插"
    - The visual_fx tells the AI video generator HOW to show the inner experience, not just describe it
12. Memory recall beats (角色回忆) need VISUAL CONTENT, not just "他想起..." — describe what the audience SEES: fragments of past scenes, superimposed images, color shifts, etc.

## Beat Requirements (MANDATORY per beat)

13. **action**: Complete visual description of the 7-10s moment. NOT a single micro-action — a full visual paragraph with beginning, middle, and end state.
14. **visual_fx**: String or null. Visual effects treatment. Required for: memories, flashbacks, hallucinations, vision sequences, entering dream/alternate realms. Use null for normal reality.
15. **dialogue**: Array of {speaker, line, emotion}. Empty array if no one speaks. A single beat can contain multiple dialogue lines if they belong to the same continuous conversation moment.
16. **expressions**: Dict mapping character name → expression description. EVERY character appearing in this beat MUST have an expression entry.
17. **sound_cue**: Specific sound effect for this beat. Be detailed and atmospheric. Use "静谧" only for intentional silence.

## Scene-level Requirements

18. **atmosphere**: Overall mood, lighting, color temperature, spatial feel of the scene. Be SPECIFIC — "苍翠碧绿的空间，荧光粒子漂浮，空旷无垠" not "绿色空间".
19. **scene_sound_cues**: Background ambient sounds that persist throughout the scene.

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
          "action": "萧澈从昏迷中苏醒，缓缓睁开眼。他发现自己躺在挂着红色幔帐的婚床上，神色从茫然转为警觉，快速坐起身环顾四周房间——暖黄晨光透过雕花窗棂洒入，红色帷帐飘动，喜庆布置中带着陌生感。",
          "visual_fx": null,
          "dialogue": [
            {"speaker": "萧澈（内心）", "line": "怎么回事……难道我还没有死？我明明坠下了绝云崖，怎么可能还活着！", "emotion": "困惑、震惊"}
          ],
          "expressions": {"萧澈": "苏醒时眼神迷茫，坐起后转为警觉，快速扫视房间，眉头微皱"},
          "sound_cue": "床铺轻微吱呀声，身体快速坐起的衣物摩擦声"
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
- **action**: Complete visual paragraph for 7-10s of screen time. Opening state → development → closing state.
- **visual_fx**: String or null. Visual effects treatment for memories/flashbacks/visions.
- **dialogue**: Array of objects. Each: speaker (str), line (str — EXACT original text), emotion (str).
- **expressions**: Object mapping character name → expression string. EVERY character in the beat must appear as a key. Include emotional transitions.
- **sound_cue**: String. One per beat. Specific and atmospheric.
- **characters** (top-level): Array of ALL unique character names in the entire chapter.
- **scenes_list**: Array of ALL distinct scene/location names in first-appearance order.

## What NOT to do

- Do NOT write micro-beats — each beat is a complete 7-10s video moment.
- Do NOT merge different physical spaces into one scene — environment change = new scene.
- Do NOT invent dialogue — use the novel's exact words.
- Do NOT skip expressions or sound cues — every beat needs both.
- Do NOT design camera shots — that is the storyboard director's job."""


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
        skip = begin_agent_run(self.agent_name, chapter_id, db, {"chapter_id": chapter_id})
        if skip:
            return skip

        try:
            script_json = self.llm.generate_json(
                system_prompt=SCRIPTWRITER_SYSTEM_PROMPT,
                user_prompt=(
                    "请将以下小说章节改编为结构化剧本（JSON 格式）。\n"
                    "每个 beat 是一个完整的 8-10 秒视觉段落（视频原生 beat），"
                    "不是微动作拆分。确保：\n"
                    "1) 环境变化必须创建独立场景（如天毒珠内部、回忆/闪回场景）\n"
                    "2) 回忆和幻觉的 beat 要有具体的 visual_fx 视觉处理说明\n"
                    "3) 所有人物对话忠实提取原文\n"
                    "4) 目标 8-12 个 beat\n\n"
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

        except (KeyboardInterrupt, SystemExit):
            raise
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
