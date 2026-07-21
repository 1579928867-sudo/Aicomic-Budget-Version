"""Outfit Manager Agent — detects outfit changes and manages outfit lookups.

v0.9: Replaces the old variant system. Each character has one default outfit
(design sheet image) and zero or more tagged alternate outfits. This agent
detects long-term outfit changes during scene transitions and triggers new
design sheet generation on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database


# ── Keywords that signal possible outfit changes ──
_OUTFIT_CHANGE_KEYWORDS = [
    "换上", "换了", "穿上", "换了一身", "换装", "更衣",
    "道袍", "校服", "战甲", "新衣", "换上了", "披上",
    "着装", "打扮", "装束", "服饰", "衣袍", "长袍",
    "宗门", "学院", "制服", "铠甲", "戎装",
]

# ── LLM prompt for detecting long-term outfit changes ──
OUTFIT_DETECTOR_SYSTEM_PROMPT = """You are a script analyst. Your task: detect whether a shot describes a LONG-TERM outfit change for a character.

## Long-term outfit changes (signal "new" or "existing"):
- Joining a sect/school and wearing their uniform (宗门道袍, 学院制服)
- Donning armor before battle (战甲)
- Time skip with new appearance
- Permanent costume change (disguise, transformation)

## Temporary changes (signal None — do NOT trigger):
- Getting wet, dirty, or bloody (temporary state)
- Throwing on a cloak for a moment
- Removing an outer layer briefly
- Minor accessory changes (taking off a ring)

## Input
You will receive:
- The shot text (narration + dialogue)
- The character name
- A list of existing outfit tags for this character

## Output
Return ONLY valid JSON:
- If no outfit change: {"has_change": false}
- If an EXISTING outfit matches: {"has_change": true, "tag": "宗门道袍"}
- If a NEW outfit is needed: {"has_change": true, "tag": "宗门道袍", "clothing_desc": "白底蓝边道袍，左胸绣苍风玄府徽记...", "activation_condition": "萧澈正式加入苍风玄府后"}
"""


# ── LLM prompt for generating new outfit design prompts ──
OUTFIT_PROMPT_GENERATOR_SYSTEM_PROMPT = """You are a professional character designer. Generate a complete character design sheet prompt (人物设定图提示词) for a character with a new outfit.

Follow this format exactly:
【时代背景】角色名（代称），性别 年龄岁，8k 类 3D 游戏 cg 电影风格，
包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，
带一些人物简介：[角色简介]。
画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），
中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。
三视图间距均匀，同一水平线对齐。
[角色外貌与新衣着细节]
所有画面底下可以给一套法宝细节图，[法宝描述]。
底部标注：[outfit_tag]

IMPORTANT: Keep the character's face, hairstyle, body type, and equipment/artifacts UNCHANGED. Only replace the clothing description.

Return ONLY valid JSON:
{"design_prompt": "..."}"""


@dataclass
class OutfitDecision:
    """Result of outfit change detection."""
    tag: str
    change_type: str          # "existing" or "new"
    clothing_desc: str = ""   # Only for "new"
    activation_condition: str = ""  # Only for "new"


class OutfitManagerAgent(AgentInterface):
    """Detects outfit changes and manages outfit lookups per shot.

    This agent is called inline during shot processing (not as a standalone
    pipeline step). Its main entry points are detect_outfit_change() and
    get_active_outfit() — both are called by the Orchestrator.

    Input (for execute):  {"chapter_id": int, "script_id": int}
    Output: {"outfits_generated": int, "shots_tagged": int}
    """

    agent_name = "outfit-manager"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    # ── Detection ──

    def _has_outfit_keywords(self, text: str) -> bool:
        """Check if text contains any outfit-change keywords."""
        for kw in _OUTFIT_CHANGE_KEYWORDS:
            if kw in text:
                return True
        return False

    def _llm_detect_outfit(
        self, shot_text: str, character_name: str, existing_tags: list[str],
        db: Database,
    ) -> dict | None:
        """Call LLM to determine if an outfit change is happening."""
        try:
            tag_list = "、".join(existing_tags) if existing_tags else "无"
            user_prompt = (
                f"角色：{character_name}\n"
                f"已有服饰标签：{tag_list}\n\n"
                f"镜头内容：\n{shot_text[:800]}"
            )
            result = self.llm.generate_json(
                system_prompt=OUTFIT_DETECTOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return result
        except Exception:
            db.log(self.agent_name, self._chapter_id, "llm_detect_error",
                   {"character": character_name}, level="ERROR")
            return None

    def _generate_outfit_prompt(
        self, character_name: str, tag: str, clothing_desc: str,
        activation_condition: str, db: Database,
    ) -> str:
        """Generate a design_prompt for a new outfit via LLM.

        Swaps clothing descriptions while keeping face/body/props from the
        known character. The prompt is used by ImageGenerator to create the
        outfit's design sheet image.
        """
        try:
            user_prompt = (
                f"为角色生成新的换装设定图提示词。\n\n"
                f"角色：{character_name}\n"
                f"新服饰标签：{tag}\n"
                f"新衣着描述：{clothing_desc}\n"
                f"激活条件：{activation_condition}\n\n"
                f"请生成完整的人物设定图提示词（design_prompt），格式遵循：\n"
                f"【时代背景】角色名，性别 年龄岁，8k 类 3D 游戏 cg 电影风格，\n"
                f"包括左侧人物全身设计图含衣着细节，右侧画面三视图...\n"
                f"保留角色的面部特征、发型、体型、法宝装备等不变，只更换衣着描述。\n"
                f"在底部标注：[{tag}]。\n"
                f"返回 JSON：{{\"design_prompt\": \"...\"}}"
            )
            result = self.llm.generate_json(
                system_prompt=OUTFIT_PROMPT_GENERATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            return result.get("design_prompt", "")
        except Exception:
            db.log(self.agent_name, self._chapter_id, "generate_prompt_error",
                   {"character": character_name, "tag": tag}, level="ERROR")
            return ""

    def detect_outfit_change(
        self, shot_text: str, character_id: int, character_name: str,
        db: Database,
    ) -> OutfitDecision | None:
        """Detect if this shot triggers an outfit change.

        Returns OutfitDecision or None (no change detected).
        Only runs LLM when keyword pre-filter passes.
        """
        # Step 1: Keyword pre-filter
        if not self._has_outfit_keywords(shot_text):
            return None

        # Step 2: Check existing outfits' activation_conditions
        existing_outfits = db.get_character_outfits(character_id)
        existing_tags = [o["tag"] for o in existing_outfits if o["tag"] != "默认"]

        for outfit in existing_outfits:
            cond = outfit.get("activation_condition", "")
            if cond and cond in shot_text:
                return OutfitDecision(
                    tag=outfit["tag"],
                    change_type="existing",
                )

        # Step 3: LLM detection
        result = self._llm_detect_outfit(shot_text, character_name, existing_tags, db)
        if not result or not result.get("has_change"):
            return None

        tag = result.get("tag", "")
        if not tag:
            return None

        if tag in existing_tags:
            return OutfitDecision(tag=tag, change_type="existing")

        return OutfitDecision(
            tag=tag,
            change_type="new",
            clothing_desc=result.get("clothing_desc", ""),
            activation_condition=result.get("activation_condition", ""),
        )

    # ── Lookup ──

    def get_active_outfit(
        self, character_id: int, outfit_tag: str | None, db: Database,
    ) -> dict | None:
        """Get the active outfit for a character in a shot.

        Args:
            character_id: character_card.id
            outfit_tag: shot's outfit_tag (None → use default)
            db: Database instance

        Returns:
            character_outfit row dict, or None
        """
        if outfit_tag:
            outfit = db.get_character_outfit(character_id, outfit_tag)
            if outfit:
                return outfit
            # Fallback to default if tag not found
        return db.get_character_outfit(character_id, None)  # default

    # ── Helpers for execute ──

    def _resolve_character_name(self, char_id: int, db: Database) -> str:
        """Look up character name by id from character_card table."""
        row = db.conn.execute(
            "SELECT name FROM character_card WHERE id = ?", (char_id,)
        ).fetchone()
        return row["name"] if row else "未知"

    def _apply_outfit_decision(
        self, decision: OutfitDecision | None, char_id: int, shot_id: int,
        char_current_tags: dict, db: Database, char_name: str,
    ) -> tuple[int, int]:
        """Handle the three decision branches, update db and tag tracking.

        Returns:
            (outfits_generated_delta, shots_tagged_delta)
        """
        if decision is None:
            current_tag = char_current_tags.get(char_id)
            db.update_shot_outfit_tag(shot_id, current_tag)
            return (0, 1 if current_tag else 0)

        if decision.change_type == "existing":
            char_current_tags[char_id] = decision.tag
            db.update_shot_outfit_tag(shot_id, decision.tag)
            return (0, 1)

        # decision.change_type == "new"
        design_prompt = self._generate_outfit_prompt(
            char_name, decision.tag,
            decision.clothing_desc,
            decision.activation_condition,
            db,
        )
        if not design_prompt:
            return (0, 0)  # LLM failed — don't create a dead outfit row

        db.create_character_outfit(
            character_id=char_id,
            tag=decision.tag,
            prompt=design_prompt,
            image_path="",
            is_default=0,
            activation_condition=decision.activation_condition,
        )
        char_current_tags[char_id] = decision.tag
        db.update_shot_outfit_tag(shot_id, decision.tag)
        return (1, 1)

    # ── Standalone execute (runs per-chapter, pre-processes all shots) ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        """Pre-process all shots for outfit changes. Called as pipeline step.

        Scans shots at scene transitions, detects outfit changes, and creates
        outfit records for new outfits (images generated later by ImageGenerator).
        """
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]
        self._chapter_id = chapter_id

        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped",
                   {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started",
               {"script_id": script_id})

        try:
            shots = db.get_storyboard_shots(script_id)
            if not shots:
                db.set_agent_status(self.agent_name, chapter_id, "done")
                return AgentResult(success=True,
                                   data={"outfits_generated": 0,
                                         "shots_tagged": 0})

            outfits_generated = 0
            shots_tagged = 0
            char_current_tags: dict[int, str | None] = {}
            prev_scene_id = None

            for shot in shots:
                sd = dict(shot)
                scene_id = sd.get("scene_id")
                shot_id = sd["id"]
                shot_text = f"{sd.get('narration', '')} {sd.get('dialogue', '')}"

                # Resolve characters in this shot
                char_ids_raw = sd.get("char_ids", "[]")
                try:
                    char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
                except (json.JSONDecodeError, TypeError):
                    char_ids = []

                is_scene_transition = (prev_scene_id is not None and scene_id != prev_scene_id)
                prev_scene_id = scene_id

                for char_id in char_ids:
                    char_name = self._resolve_character_name(char_id, db)
                    current_tag = char_current_tags.get(char_id)

                    # Throttle: only detect on scene transitions
                    if not is_scene_transition and current_tag is not None:
                        db.update_shot_outfit_tag(shot_id, current_tag)
                        shots_tagged += 1
                        continue

                    decision = self.detect_outfit_change(
                        shot_text, char_id, char_name, db,
                    )
                    og, st = self._apply_outfit_decision(
                        decision, char_id, shot_id,
                        char_current_tags, db, char_name,
                    )
                    outfits_generated += og
                    shots_tagged += st

            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(self.agent_name, chapter_id, "completed", {
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
            })

            return AgentResult(success=True, data={
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
            })

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed",
                   {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
