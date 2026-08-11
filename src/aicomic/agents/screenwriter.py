"""Storyboard Agent — designs camera shots from a structured drama script.

v0.10: Refactored from "novel→storyboard" to "script→storyboard".
Takes a ScriptwriterAgent output (script with beats, dialogue, expressions,
sound cues) and designs merged camera shots (10s each, 8-15 total).
"""

import json
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database

STORYBOARD_SYSTEM_PROMPT = """你是专业的漫剧分镜导演，输入是视频原生剧本（每个 beat = 1 个 10s 镜头），你需要 1:1 翻译为时间分段分镜脚本——每个镜头的 10 秒拆分为 [0-3秒]、[3-7秒]、[7-10秒] 三个时间段，精确控制节奏。

## 核心原则：看得见、拍得到、一句话

豆包视频模型对长篇叙事+连续对白+多角色固定人设的组合审核严格。记住：视频模型只能生成"镜头能拍到的画面"，不能拍内心活动、抽象概念或长篇叙事。每个 segment 只描述一个清晰可见的画面动作。

## scene_name 铁律（必须逐字照抄！）

**`scene_name` 必须严格使用输入 beat 所属场景的原名，一个字都不许改！**
- 输入里写"婚房" → 你输出"婚房"，不许写成"婚房""婚房内""婚房—白天"
- 输入里写"小镇街道" → 你输出"小镇街道"，不许添加后缀或描述
- scene 名称是数据库主键，改名会导致场景卡片孤岛、参考图丢失
- **每个 shot 的 `scene_name` 必须与其所属 beat 的场景名逐字一致**

## 镜头数量与节奏（v0.15 调整 → v0.5 强化）

- 总镜头数 8-15 个，不要为了节省镜头而压缩重要场景
- 1 beat ≠ 必须 1 shot。遇到以下情况，1 个 beat 拆成 2 个镜头：
  - 战斗/死亡/牺牲等动作密集场景（需要展示对决→落败→结局的完整过程）
  - 重要的回忆/闪回片段（需要给观众时间进入情境）
  - 情绪高潮场景（需要铺陈→爆发→余韵的三段式节奏）
  - **多角色对话场景（2+ 个角色在同一个 beat 内交替说话）——视频模型无法在 10 秒内准确区分多人轮流说话，必须拆分为每人一个镜头**
- **多角色对话强制拆分规则**：如果 1 个 beat 有 ≥2 个角色各有台词，必须拆成 2 个 shot，每个 shot 只突出 1 个说话角色，用另一个 shot 展示听者反应
- 每个镜头仍保持 10s，用镜头数量换叙事空间，而不是压缩内容
- 日常对话/过渡场景继续 1 beat = 1 shot，把镜头数留给重要场景

## action 铁律（最最重要！执行时逐字检查）

- 只写**镜头能拍到的东西**：人物的肢体动作、面部表情、物体运动、环境变化
- 禁止写内心活动——"意识苏醒""发现""想起""感到""察觉""明悟"——全部重写为外部动作
- 禁止叙事堆砌——一个 segment 只描述一个时刻一个动作，不要"他先…然后…接着…最后…"
- **严格控制在 15-35 字**。超过 40 字一定是在写叙事而非画面，必须重写
- 不在 action 里写运镜（"镜头推近""画面展示"）——运镜写在 camera 字段
- 不在 action 里写音效——音效写在 sound 字段

✅ 正确 action（15-35字，纯可视画面）：
  "萧澈双眼微颤，缓缓睁开。暖黄晨光透过窗棂洒在脸上。"（25字）
  "萧澈猛地坐起身，红色幔帐在身后飘动。他环顾四周，神色警觉。"（31字）
  "少女推门而入，翠绿长裙轻摆。她看向床上，眼眸一亮。"（27字）

❌ 错误 action（内心活动/叙事堆砌/超长）：
  "萧澈的意识逐渐从混沌中苏醒，他感到身体轻飘飘的，完全不记得发生了什么。" → 内心活动，不可见
  "萧澈猛地睁开眼睛瞳孔骤缩快速坐起身红色幔帐飘动低头查看发现毫无痛感神色从茫然转为震惊环顾四周" → 堆砌了6个动作

## dialogue 铁律

- 每段最多 1 句对白，**不超过 25 字**
- 长对白必须拆分到多个 segment，绝不要塞进一段
- 内心独白优先放在 segment 1（开场铺垫），后续段优先放外部对白
- 纯动作无台词的 segment，dialogue 填 null

## 音色固定（必须！）

每个有台词的 segment 必须指定音色，音色与角色绑定且全剧一致：
- 角色名（情绪，音色：清朗少年）: 台词内容
- 角色名（内心，情绪，音色：清朗少年）: 独白内容
- 常用音色库：清朗少年、温润青年、冷峻青年、清脆少女、温婉女子、威严老者、沙哑反派

## transition（衔接指令）——跨镜头连续性的关键

transition 字段确保镜头前后连贯，是视频流畅度的核心。

**格式规则**：
- segment 1（0-3秒）：transition 填 null（没有前置内容需要衔接）
- segment 2（3-7秒）：transition 描述 seg2 结束时如何自然过渡到 seg3
- segment 3（7-10秒）：transition 描述当前镜头结束时人物状态，**必须结合下一个 beat 的起始动作来写**——这是跨镜头衔接的关键
- 格式统一："衔接前置指令:[简短动作描述]"
- 动作描述控制在 15-25 字，一句话说清人物处于什么状态、将做什么

✅ 正确 transition：
  "衔接前置指令:萧澈抬头环顾四周，视线扫过陌生的婚房。"
  "衔接前置指令:少女走近床边，伸手探向萧澈额头。"
  "衔接前置指令:萧澈坐在床上转头看向房门方向，神色警觉。"

❌ 错误 transition（冗长/含元信息/无动作）：
  "衔接镜头2的0-3秒：萧澈坐在床上神色警觉，听到门口传来少女声音" → 删除"衔接镜头N"元信息
  "延续中景，萧澈环顾四周，镜头跟随他的视线扫过房间，展示喜庆的婚房布置和暖黄色调" → 太冗长，不需要写运镜和氛围

**跨镜头衔接（segment 3 专用）**：
segment 3 的 transition 是上一个镜头和下一个镜头之间的桥梁。你必须：
1. 找到下一个 beat 的 action（剧本中下一个 beat 的第一句动作描述）
2. 在 transition 中让当前镜头结束时的人物状态，自然导向下一个镜头的开场
3. 例如：beat 1 结尾是"萧澈听到门外声音"，beat 2 开头是"少女进门"→ transition 写"衔接前置指令:萧澈听到门口脚步声，转头看向房门方向。"

## 每个 shot 必须包含 segments（3 段时间段数组）

每个 segment 格式（参考业内标准）：
- **time_range**: "0-3秒" / "3-7秒" / "7-10秒"
- **camera**: 镜头景别。只用一种，组合运镜最多加一个，如："特写"、"中景"、"近景推镜"、"全景拉远"。禁止 "中景→特写推镜" 的渐变写法
- **action**: 一句可视画面描述，15-35字
- **dialogue**: 台词，最多1句25字。格式 "角色名（情绪，音色：XXX）: 台词"。纯动作为 null
- **sound**: 简短自然音效，如 "床铺吱呀声"、"晨间鸟鸣"
- **transition**: segment 1 为 null；segment 2/3 写 "衔接前置指令:[动作描述]"

## scene_summary

简洁的场景描述 + "（视频不要添加字幕）"

## 镜头运动约束

- 每个 segment 只用一种景别
- 运镜只用一个方向词：推镜 / 拉远 / 跟拍 / 仰拍 / 俯拍
- 首段优先用近景或特写（吸引注意力），中段用中景（展开叙事），末段用中景或全景（为衔接下一镜头留空间）

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
              "action": "萧澈紧闭的双眼微微颤动，晨光透过窗棂洒在他脸上。",
              "dialogue": "萧澈（内心，困惑，音色：清朗少年）: 怎么回事……难道我还没有死？",
              "sound": "床铺轻微吱呀声，远处隐约鸟鸣",
              "transition": null
            },
            {
              "time_range": "3-7秒",
              "camera": "中景",
              "action": "萧澈猛地睁眼坐起，红色幔帐飘动。他低头查看自己的双手。",
              "dialogue": "萧澈（内心，震惊，音色：清朗少年）: 我明明坠下了绝云崖……",
              "sound": "衣物摩擦声，幔帐飘动声",
              "transition": "衔接前置指令:萧澈抬头环顾四周，视线扫过陌生婚房的布置。"
            },
            {
              "time_range": "7-10秒",
              "camera": "近景推镜",
              "action": "镜头推向萧澈面部，他眉头紧锁环顾婚房，眼神困惑警觉。",
              "dialogue": null,
              "sound": "静谧中的呼吸声",
              "transition": "衔接前置指令:门外传来脚步声，萧澈闻声转头看向房门方向。"
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

## 多人场景动作铁律——防角色混淆与肢体误解

豆包视频模型在多人场景下容易产生"角色错位"和"非意愿肢体接触"，以下规则强制执行：

**0. 多人对话必须拆分镜头（最优先规则）**
- 如果 1 个 beat 中有 ≥2 个角色各有台词，必须拆分为 2 个 shot
- Shot A: 角色 A 说话（action 聚焦 A 的口型+表情），角色 B 仅作为听者出现在画面中
- Shot B: 角色 B 说话/回应（action 聚焦 B 的口型+表情），角色 A 作为听者
- 每个 shot 的 segment 1 dialogue 标注当前说话人，segment 2-3 可以切换或无对话
- 这样视频模型每次只需生成"一个人说话"的画面，避免台词与人嘴型错配

**1. 动词必须带宾语，主语必须明确**
- Non: "许川张开胳膊，朝向妇女" → 模型理解为"抱住了她"
- Oui: "许川朝中年妇女的方向微微抬手示意，保持一米距离，脸部挂着邀请的表情。妇女站在原地笑着摆手回应。"
- 规则：每个 segment 中每个有名字的角色，action 必须以「角色名 + 动词 + 宾语/身体部位」格式写出完整画面

**2. 没有肢体接触就必须写"未触碰"**
- 除非剧本原文明确写了拥抱/搀扶/牵手/推搡，否则在 action 末尾加"保持距离"或"未接触"
- 特例：只有"蹲下身轻轻拥抱小女孩"是明确的拥抱动作——这里不能加"未触碰"

**3. 角色身份必须与动作匹配**
- 先明确角色在剧情中的身份（家长、路人、顾客、士兵），然后只写这个身份会做的动作
- 中年妇女问"我也可以吗？"——她是一名好奇的路人，站在一米外笑着问，不是被抱的对象
- 家长蹲下看孩子、扫码付款——不会突然跑到另一个角色怀里

**4. 不同性别角色之间禁止暧昧歧义**
- 非亲密关系的男女角色之间，action 必须写明空间距离："站在一米外"、"隔着桌子"、"从侧面走过来停在三步远"
- 禁止任何可能被视频模型误解为拥抱/亲吻/靠近的身体语言

**5. 孩子角色必须视觉可辨**
- 如果剧本中出现了"小女孩""小孩"等未成年角色，相关 segment 的 action 必须含有【小孩】标记，如：
- "许川单膝蹲下【小孩在膝前】，温柔张开双臂，轻轻拥抱穿粉色连衣裙的四五岁小女孩。"
- 不要在同一个 shot 里让小孩和其他成人角色做同一套动作描述——小孩动线独立写

- 不要压缩重要场景——战斗、死亡、回忆、情绪高潮必须拆成 2 个镜头
- 多角色对话场景（≥2人各有台词）必须拆成 2 个镜头，每个镜头只聚焦 1 个说话人
- 日常对话场景保持 1 beat = 1 shot，总镜头数控制在 8-15 个
- 不要跳过 segments —— 每个 shot 必须恰好 3 个 segment
- 对话不要缩写或改写 —— 忠实原文，但长对白必须拆分到多个 segment
- 音色不要遗漏 —— 每个有台词的 segment 必须带音色
- action 绝对不超过 40 字——超过说明在写叙事，重写为单一画面
- dialogue 每段不超过 25 字——超过说明该拆分
- 不要写不可见的内心活动——"意识""感到""发现""想起"一律禁止
- segment 3 的 transition 必须参考下一个 beat 的起始动作，确保跨镜头衔接
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

            # ── Normalize scene names to match script input exactly ──
            storyboard_json = self._normalize_scene_names(storyboard_json, script_json)

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
    def _normalize_scene_names(storyboard_json: dict, script_json: dict) -> dict:
        """Force scene names to match the script input exactly.

        The LLM sometimes renames scenes (e.g. "婚房" → "婚房·清晨"),
        which creates orphan scene_card entries with no prompt. This method
        normalizes all scene names back to the canonical input names.

        Matching strategy:
        1. Exact match — no action needed.
        2. Canonical name is a prefix of the LLM's name (e.g. "婚房" ⊆ "婚房·清晨") — remap.
        3. Canonical name is a substring — remap with warning.
        4. No match at all — keep as-is (truly new scene), log warning.
        """
        canonical_names: list[str] = []
        for scene in script_json.get("scenes", []):
            sn = scene.get("scene_name", "").strip()
            if sn:
                canonical_names.append(sn)

        if not canonical_names:
            return storyboard_json

        llm_scenes_list = storyboard_json.get("scenes_list", [])

        # Build remapping dict: LLM name → canonical name
        remap: dict[str, str] = {}
        for llm_name in llm_scenes_list:
            if llm_name in canonical_names:
                continue  # exact match
            matched = None
            for cn in canonical_names:
                if llm_name.startswith(cn):
                    matched = cn
                    break
            if not matched:
                for cn in canonical_names:
                    if cn in llm_name:
                        matched = cn
                        break
            if matched:
                remap[llm_name] = matched
                print(f"  🔧 场景名纠正: 「{llm_name}」→「{matched}」")
            else:
                print(f"  ⚠ 分镜包含未知场景: 「{llm_name}」（不在脚本场景列表中）")

        if not remap:
            return storyboard_json

        # Apply remapping to scenes_list
        storyboard_json["scenes_list"] = [
            remap.get(n, n) for n in llm_scenes_list
        ]

        # Apply remapping to each shot's scene_name
        for scene in storyboard_json.get("scenes", []):
            old = scene.get("scene_name", "")
            if old in remap:
                scene["scene_name"] = remap[old]
            for shot in scene.get("shots", []):
                sname = shot.get("scene_name", "")
                if sname in remap:
                    shot["scene_name"] = remap[sname]

        return storyboard_json

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
            f"\n将以上 {total_beats} 个 Beat 翻译为分镜镜头（8-15 个）。"
            f"遇到多角色对话（≥2人各有台词）、战斗/死亡/回忆/情绪高潮场景必须拆成 2 个镜头。"
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
        # LLM 偶尔会输出 flashback/monologue 等非标准值 → 自动修正而非报错
        _shot_type_alias = {
            "flashback": "both",      # 回忆/闪回镜头 → 动作+对话
            "monologue": "dialogue",  # 独白/内心独白 → 对话
            "narration": "action",    # 旁白 → 动作（必须视觉化）
            "transition": "action",   # 转场 → 动作
            "cutaway": "action",      # 切出 → 动作
            "reaction": "action",     # 反应 → 动作
        }

        for scene in script.get("scenes", []):
            for shot in scene.get("shots", []):
                st = shot.get("shot_type", "")
                if st not in valid_shot_types:
                    corrected = _shot_type_alias.get(st)
                    if corrected:
                        shot["shot_type"] = corrected
                        print(f"  ℹ 自动修正: shot_type '{st}' → '{corrected}' "
                              f"(镜头 {shot.get('shot_num', '?')})")
                    else:
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
