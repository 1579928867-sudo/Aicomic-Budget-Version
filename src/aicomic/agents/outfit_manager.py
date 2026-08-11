"""Outfit Manager Agent — detects outfit changes and manages outfit lookups.

v0.9: Replaces the old variant system. Each character has one default outfit
(design sheet image) and zero or more tagged alternate outfits. This agent
detects long-term outfit changes during scene transitions and triggers new
design sheet generation on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database
from .prompt_utils import parse_char_ids
from .char_designer import CHAR_DESIGNER_SYSTEM_PROMPT

# Extension for outfit variant generation — swaps clothing while keeping all else identical.
_VARIANT_INSTRUCTION = (
    "\n\n## Outfit Variant Mode\n"
    "You are generating a NEW design_prompt for an existing character who has "
    "changed clothes. CRITICAL: Keep the character's face shape, hairstyle, "
    "body type, height ratio, and equipment/artifacts COMPLETELY UNCHANGED "
    "from the original design. ONLY replace the clothing description. "
    "The design_prompt must remain in the exact same game card format as above."
)


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
        self, chapter_id: int, shot_text: str, character_name: str,
        existing_tags: list[str], db: Database,
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
            db.log(self.agent_name, chapter_id, "llm_detect_error",
                   {"character": character_name}, level="ERROR")
            return None

    def _generate_outfit_prompt(
        self, chapter_id: int, character_name: str, tag: str, clothing_desc: str,
        activation_condition: str, db: Database,
    ) -> str:
        """Generate a design_prompt for a new outfit via LLM.

        Uses the canonical CHAR_DESIGNER_SYSTEM_PROMPT with a variant-mode
        instruction appended, so format changes to the main template
        automatically propagate to outfit generation.
        """
        try:
            user_prompt = (
                f"为角色生成新的换装设定图提示词。\n\n"
                f"角色：{character_name}\n"
                f"新服饰标签：{tag}\n"
                f"新衣着描述：{clothing_desc}\n"
                f"激活条件：{activation_condition}\n\n"
                f"请生成完整的人物设定图提示词（design_prompt），"
                f"保持角色面部、发型、体型、法宝等不变，只更换衣着。"
                f"在底部标注：[{tag}]。"
                f"返回 JSON：{{\"design_prompt\": \"...\"}}"
            )
            result = self.llm.generate_json(
                system_prompt=CHAR_DESIGNER_SYSTEM_PROMPT + _VARIANT_INSTRUCTION,
                user_prompt=user_prompt,
            )
            return result.get("design_prompt", "")
        except Exception:
            db.log(self.agent_name, chapter_id, "generate_prompt_error",
                   {"character": character_name, "tag": tag}, level="ERROR")
            return ""

    def detect_outfit_change(
        self, chapter_id: int, shot_text: str, character_id: int,
        character_name: str, db: Database,
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
        result = self._llm_detect_outfit(chapter_id, shot_text, character_name, existing_tags, db)
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
        chapter_id: int,
    ) -> tuple[int, int]:
        """Handle the three decision branches, update db and tag tracking.

        Returns:
            (outfits_generated_delta, shots_tagged_delta)
        """
        if decision is None:
            current_tag = char_current_tags.get(char_id) or '默认'
            char_current_tags[char_id] = current_tag
            db.set_shot_character_outfit(shot_id, char_id, current_tag)
            return (0, 1)

        if decision.change_type == "existing":
            char_current_tags[char_id] = decision.tag
            db.set_shot_character_outfit(shot_id, char_id, decision.tag)
            return (0, 1)

        # decision.change_type == "new"
        design_prompt = self._generate_outfit_prompt(
            chapter_id, char_name, decision.tag,
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
        db.set_shot_character_outfit(shot_id, char_id, decision.tag)
        return (1, 1)

    # ── Standalone execute (runs per-chapter, pre-processes all shots) ──

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        """Pre-process all shots for outfit changes. Called as pipeline step.

        Scans shots at scene transitions, detects outfit changes, and creates
        outfit records for new outfits (images generated later by ImageGenerator).

        IMPORTANT: Also ensures EVERY character in EVERY shot has a junction
        record in shot_character_outfit. This is essential for LibraryPage
        character listing and audit counts.
        """
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]
        force = input_data.get("force", False)

        skip = begin_agent_run(self.agent_name, chapter_id, db,
                               {"script_id": script_id}, force=force)
        # ── Safety: even if status says "done", verify junction records exist ──
        if skip:
            j_count = db.conn.execute(
                """SELECT COUNT(*) FROM shot_character_outfit sco
                   JOIN storyboard_shot ss ON ss.id=sco.shot_id
                   WHERE ss.script_id=?""",
                (script_id,),
            ).fetchone()[0]
            if j_count == 0:
                skip = begin_agent_run(self.agent_name, chapter_id, db,
                                       {"script_id": script_id}, force=True)
                if skip:
                    return skip
            else:
                return skip

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
                char_ids = parse_char_ids(sd.get("char_ids"))

                is_scene_transition = (prev_scene_id is not None and scene_id != prev_scene_id)
                prev_scene_id = scene_id

                for char_id in char_ids:
                    char_name = self._resolve_character_name(char_id, db)
                    current_tag = char_current_tags.get(char_id)

                    # ── Only do LLM-based detection on scene transitions ──
                    if not is_scene_transition and current_tag is not None:
                        db.set_shot_character_outfit(shot_id, char_id, current_tag)
                        shots_tagged += 1
                        continue

                    decision = self.detect_outfit_change(
                        chapter_id, shot_text, char_id, char_name, db,
                    )
                    og, st = self._apply_outfit_decision(
                        decision, char_id, shot_id,
                        char_current_tags, db, char_name, chapter_id,
                    )
                    outfits_generated += og
                    shots_tagged += st

            # ── BACKFILL: Ensure ALL shots have ALL their char_ids in
            #     shot_character_outfit, even if no outfit changes detected ──
            backfilled = 0
            for shot in shots:
                sd = dict(shot)
                shot_id = sd["id"]
                char_ids = parse_char_ids(sd.get("char_ids"))
                for char_id in char_ids:
                    existing = db.conn.execute(
                        "SELECT 1 FROM shot_character_outfit WHERE shot_id=? AND character_id=?",
                        (shot_id, char_id),
                    ).fetchone()
                    if not existing:
                        tag = char_current_tags.get(char_id) or "默认"
                        db.set_shot_character_outfit(shot_id, char_id, tag)
                        backfilled += 1

            if backfilled > 0:
                print(f"  ℹ outfit-manager: backfilled {backfilled} junction records "
                      f"({shots_tagged} tagged via detection)")

            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(self.agent_name, chapter_id, "completed", {
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
                "junction_backfilled": backfilled,
            })

            return AgentResult(success=True, data={
                "outfits_generated": outfits_generated,
                "shots_tagged": shots_tagged,
            })

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed",
                   {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))
