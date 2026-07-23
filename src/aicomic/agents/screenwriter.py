"""Storyboard Agent — designs camera shots from a structured drama script.

v0.10: Refactored from "novel→storyboard" to "script→storyboard".
Takes a ScriptwriterAgent output (script with beats, dialogue, expressions,
sound cues) and designs merged camera shots (≤10s each, 5-8 total).
"""

import json
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database

STORYBOARD_SYSTEM_PROMPT = """你是专业的漫剧分镜导演，输入是视频原生剧本（每个 beat = 1 个 10s 镜头），你需要 1:1 翻译为时间分段分镜脚本——每个镜头的 10 秒拆分为 [0-3秒]、[3-7秒]、[7-10秒] 三个时间段，精确控制节奏。

## 每个 shot 必须包含 segments（3 段时间段数组）

每个 segment 是一个时间段内的精确拍摄指令：
- **time_range**: "0-3秒" / "3-7秒" / "7-10秒"
- **camera**: 镜头景别和运镜。景别：特写、大特写、近景、中景、全景、远景、过肩。运镜可组合：推镜、拉远、跟拍、环绕、仰拍、俯拍、手持跟甩、360°环绕。例如 "特写推镜"、"全景拉远"、"中景环绕"、"低角度仰拍跟拍"
- **action**: 该时间段内的完整画面描述——人物在做什么、表情变化、身体动作、环境变化。必须足够细致，能让 AI 理解这一段的完整视觉内容
- **dialogue**: 台词，格式为 "角色名（情绪，音色：XXX）: 台词内容"。纯动作无台词则为 null
- **sound**: 音效描述，例如 "床铺轻微吱呀声"、"拳脚破空闷响"、"静谧中的呼吸声"
- **transition**: 该时间段与下一时间段的衔接指令（从第二个镜头开始，如果是衔接前一个镜头的内容则说明）。0-3秒可为 null

## 音色固定（必须！）

每个有台词的 segment 必须指定音色，音色与角色绑定且全剧一致：
- 对话格式：角色名（情绪，音色：清朗少年）: 台词内容
- 内心独白格式：角色名（内心，情绪，音色：清朗少年）: 独白内容
- 常用音色库：清朗少年、温润青年、冷峻青年、清脆少女、温婉女子、威严老者、沙哑反派
- 每个角色首次出场时确定音色，后续保持一致

## 衔接规则（从第二个镜头开始）

第三个段（7-10秒）的最后一句要自然过渡到下一个镜头：
- transition 字段写 "衔接镜头{N+1}的0-3秒，[简述如何过渡]"
- 动作不重复——下一镜头起始必须是上一镜头结束的自然延续

## 场景总结

每个 shot 末尾必须有一句场景总结（单列字段 scene_summary）：
格式："场景: [地点描述]，[光线/氛围描述]。（视频不要添加字幕）"

## Output Format

只输出 JSON，格式如下：

{
  "scenes": [
    {
      "scene_name": "婚房",
      "scene_index": 1,
      "shots": [
        {
          "shot_num": 1,
          "shot_type": "both",
          "duration_sec": 10.0,
          "characters": [{"name": "萧澈", "variant": "default"}],
          "scene_name": "婚房",
          "segments": [
            {
              "time_range": "0-3秒",
              "camera": "特写推镜",
              "action": "萧澈紧闭的双眼微微颤动，意识从混沌中苏醒。暖黄晨光透过雕花窗棂洒在他脸上，睫毛轻颤。",
              "dialogue": "萧澈（内心，困惑，音色：清朗少年）: 怎么回事……难道我还没有死？",
              "sound": "床铺轻微吱呀声，远处隐约鸟鸣",
              "transition": null
            },
            {
              "time_range": "3-7秒",
              "camera": "中景",
              "action": "萧澈猛地睁开眼睛，瞳孔骤缩。他快速坐起身，红色幔帐在他身后飘动。他低头查看自己的身体，发现毫无痛感，神色从茫然转为震惊，环顾四周喜庆的婚房布置。",
              "dialogue": "萧澈（内心，震惊，音色：清朗少年）: 我明明坠下了绝云崖，怎么可能还活着！而且身上居然没有痛感……",
              "sound": "身体快速坐起的衣物摩擦声，幔帐飘动的沙沙声",
              "transition": "延续中景，萧澈环顾四周，镜头跟随他的视线扫过房间"
            },
            {
              "time_range": "7-10秒",
              "camera": "中景→特写推镜",
              "action": "萧澈的视线扫过婚房——红色帷帐、喜字剪纸、暖黄烛光。镜头缓缓推近到他的面部特写，他眉头紧锁，嘴唇微张，眼神中充满困惑和警觉。",
              "dialogue": null,
              "sound": "静谧中呼吸声，远处风声",
              "transition": "衔接镜头2的0-3秒：萧澈坐在床上神色警觉，听到门口方向传来声音，缓缓转头"
            }
          ],
          "scene_summary": "场景：中国古代婚房，清晨暖光透过窗棂洒入，红色帷帐飘动，喜庆中带着昏沉。（视频不要添加字幕）"
        }
      ]
    }
  ],
  "characters": ["萧澈"],
  "scenes_list": ["婚房"]
}

## 重点禁止

- 不要合并 beats —— 1 beat = 1 shot
- 不要跳过 segments —— 每个 shot 必须恰好 3 个 segment
- 对话不要缩写或改写 —— 忠实原文
- 音色不要遗漏 —— 每个有台词的 segment 必须带音色
- 不要输出多余文字 —— 只输出 JSON
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
                        "duration_sec": shot.get("duration_sec", 10.0),
                        "char_ids": char_ids,
                        "scene_id": scene_id,
                        "segments": shot.get("segments", []),
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
        parts.append("## 剧本 (视频原生 Beat)\n")
        parts.append(f"时代背景: {script_json.get('era_background', '中国古代·仙侠')}")

        total_beats = sum(
            len(s.get("beats", [])) for s in script_json.get("scenes", [])
        )
        parts.append(f"总 Beat 数: {total_beats} → 每个 beat 翻译为 1 个含 3 段的 shot")
        parts.append("")

        for scene in script_json.get("scenes", []):
            sn = scene.get("scene_name", "?")
            atm = scene.get("atmosphere", "")
            parts.append(f"### 场景: {sn}")
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
                visual_fx = b.get("visual_fx")

                parts.append(f"  Beat {bn}: {action}")
                if visual_fx:
                    parts.append(f"    🎬 visual_fx: {visual_fx}")
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
            f"\n将以上 {total_beats} 个 Beat 一一对应翻译为 {total_beats} 个分镜镜头。"
            f"每个镜头的 10 秒拆分为 3 个时间段([0-3秒][3-7秒][7-10秒])，"
            f"每段包含景别运镜、画面描述、台词音效。"
            f"每个有台词的角色必须指定音色并在全剧保持一致。"
            f"第二个镜头开始必须写衔接指令。"
        )
        return "\n".join(parts)

    @staticmethod
    def _validate_storyboard(script: dict):
        """Validate storyboard JSON has required fields and valid segments."""
        if not isinstance(script, dict):
            raise ValueError("Storyboard JSON must be a dict")
        for field in ("scenes", "characters", "scenes_list"):
            if field not in script:
                raise ValueError(f"Storyboard JSON missing '{field}'")

        valid_shot_types = {"action", "dialogue", "both"}

        for scene in script.get("scenes", []):
            for shot in scene.get("shots", []):
                st = shot.get("shot_type", "")
                if st not in valid_shot_types:
                    raise ValueError(
                        f"Invalid shot_type '{st}' in shot {shot.get('shot_num', '?')}"
                    )
                dur = shot.get("duration_sec", 0)
                if dur < 7.0 or dur > 10.0:
                    raise ValueError(
                        f"Shot {shot.get('shot_num', '?')} duration {dur}s out of range"
                    )
                segments = shot.get("segments", [])
                if len(segments) != 3:
                    raise ValueError(
                        f"Shot {shot.get('shot_num', '?')} must have exactly 3 segments, got {len(segments)}"
                    )
                for seg in segments:
                    if not seg.get("camera"):
                        raise ValueError(
                            f"Shot {shot.get('shot_num', '?')} segment missing camera"
                        )
                    if not seg.get("action"):
                        raise ValueError(
                            f"Shot {shot.get('shot_num', '?')} segment missing action"
                        )
