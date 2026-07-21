"""Character Designer Agent — generates appearance descriptions for all characters.

Uses LLM to create detailed visual descriptions following industry-standard
character design format suitable for AI image generation.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

CHAR_DESIGNER_SYSTEM_PROMPT = """You are a professional character designer for Chinese animation/comic production. Your task is to generate a single detailed character design sheet prompt (人物设定图提示词) for each character, in a format suitable for AI image generation.

## Core Requirements

1. **Extract ALL characters** from the provided character list. Generate ONE design_prompt per character.
2. **Detect era background** (时代背景) from the text. Must be one of: "中国古代·仙侠", "中国古代·武侠", "中国古代·宫廷", "中国现代·都市", "中国现代·校园", "民国", "西方奇幻", "科幻未来", "架空世界".
3. **Art style**: Always use "8k 类 3D 游戏 cg 电影风格" for ancient/Xianxia settings. The design sheet should look like a professional game concept art sheet.

## Design Prompt Template

For each character, generate a `design_prompt` following this format:

For ancient Chinese settings:
```
【中国古代·仙侠】角色名（代称），性别 年龄岁，8k 类 3D 游戏 cg 电影风格，
包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，
带一些人物简介：[1-2句角色核心背景]。
画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），
中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。
三视图间距均匀，同一水平线对齐。
[角色外貌与衣着细节描写]
[若有法宝/装备]所有画面底下可以给一套法宝细节图，[法宝名称和描述]。
```

For modern settings: replace "【中国古代·仙侠】" with the correct era tag, adjust art style to "8k 高质量 cg 渲染风格".

## Key Rules

4. **No variants** — each character gets exactly ONE design_prompt (their default/default look).
5. **Hands rule**: "双手自然下垂，手里无任何物品" unless the character has a specific held item that is part of their core design.
6. **The design_prompt is a COMPLETE image generation prompt ready to use** — it must contain all visual details.
7. **Character names MUST exactly match the provided character list**.
8. **For animals/beasts/monsters**: Different format — describe species, body shape, fur/skin, distinctive features. Use "【时代背景】角色名（代称），8k 类 3D 游戏 cg 电影风格，全身设定图". Skip three-view layout; describe a single full-body design view.

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "era_background": "中国古代·仙侠",
  "characters": [
    {
      "name": "萧澈",
      "aliases": ["云澈"],
      "gender": "男",
      "age": 16,
      "is_human": true,
      "design_prompt": "【中国古代·仙侠】萧澈（云澈），男 16岁，8k 类 3D 游戏 cg 电影风格，包括左侧人物全身设计图含衣着细节，右侧画面三视图..."
    }
  ]
}
"""


class CharacterDesignerAgent(AgentInterface):
    """Generates character design sheet prompts for image generation.

    Input:  {"chapter_id": int, "raw_text": str, "characters": list[str]}
    Output: {"outfits_created": int, "character_names": list[str]}

    Also exposes generate_outfit_variant() for the OutfitManager to create
    new outfit design prompts when outfit changes are detected mid-pipeline.
    """

    agent_name = "char-designer"

    # Modified prompt for outfit variant generation — allows clothing swaps
    # while keeping face/body/props identical.
    VARIANT_SYSTEM_PROMPT = CHAR_DESIGNER_SYSTEM_PROMPT.replace(
        "**No variants** — each character gets exactly ONE design_prompt (their default/default look).",
        "**Outfit variant mode** — generate a variant design_prompt that swaps ONLY the clothing description. Keep face shape, hairstyle, body type, equipment/artifacts, and all non-clothing details IDENTICAL to the default design. Only the clothing changes.",
    )

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("raw_text"), str)
            and len(input_data["raw_text"]) > 0
            and isinstance(input_data.get("characters"), list)
            and len(input_data["characters"]) > 0
        )

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        raw_text = input_data["raw_text"]
        characters = input_data["characters"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"characters": characters})

        try:
            user_prompt = (
                f"请为以下小说角色生成人物设定图提示词（JSON 格式）：\n\n"
                f"角色列表：{characters}\n\n"
                f"小说原文：\n{raw_text[:3000]}"
            )

            # ── Call LLM ──
            result_json = self.llm.generate_json(
                system_prompt=CHAR_DESIGNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            # ── Validate structure ──
            self._validate_char_design(result_json, characters)

            # ── Save to character_outfit table ──
            outfits_created = 0
            char_list = result_json.get("characters", [])

            for char_data in char_list:
                name = char_data.get("name", "")
                char_id, _ = db.get_or_create_character(name)
                design_prompt = char_data.get("design_prompt", "")

                if not design_prompt:
                    continue

                # Create default outfit record (image_path empty — ImageGenerator fills it)
                db.create_character_outfit(
                    character_id=char_id,
                    tag="默认",
                    prompt=design_prompt,
                    image_path="",
                    is_default=1,
                    activation_condition="",
                )
                outfits_created += 1

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "outfits_created": outfits_created,
                    "characters_processed": len(char_list),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "outfits_created": outfits_created,
                    "character_names": [c["name"] for c in char_list],
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))

    @staticmethod
    def _validate_char_design(result: dict, expected_characters: list[str]):
        """Validate the character design JSON structure."""
        if not isinstance(result, dict):
            raise ValueError("Character design JSON must be a dict")
        if "characters" not in result:
            raise ValueError("Character design JSON missing 'characters'")
        if not isinstance(result["characters"], list):
            raise ValueError("'characters' must be a list")
        if len(result["characters"]) == 0:
            raise ValueError("'characters' list is empty")
        for char in result["characters"]:
            if not char.get("design_prompt", ""):
                raise ValueError(
                    f"Character '{char.get('name', '?')}' missing 'design_prompt'"
                )

    def generate_outfit_variant(
        self, tag: str, clothing_desc: str, activation_condition: str,
        character_name: str, era_background: str, base_info: dict,
        db: Database,
    ) -> int | None:
        """Generate a design_prompt for a new outfit variant.

        Called by OutfitManager when a "new" outfit change is detected.
        Uses LLM to swap clothing descriptions while keeping face/body/props.

        Args:
            tag: Outfit tag name (e.g., "宗门道袍")
            clothing_desc: New clothing description
            activation_condition: When this outfit activates
            character_name: Character name
            era_background: Era tag (e.g. "中国古代·仙侠")
            base_info: Dict with keys: gender, age, aliases, is_human
            db: Database instance

        Returns:
            outfit_id if successful, None on failure
        """
        try:
            user_prompt = (
                f"为角色生成新的换装设定图提示词。\n\n"
                f"角色：{character_name}\n"
                f"时代：{era_background}\n"
                f"原基础信息：性别={base_info.get('gender', '')}, "
                f"年龄={base_info.get('age', '')}岁\n"
                f"新服饰标签：{tag}\n"
                f"新衣着描述：{clothing_desc}\n"
                f"激活条件：{activation_condition}\n\n"
                f"请生成完整的人物设定图提示词（design_prompt），保留角色的"
                f"面部特征、发型、体型、法宝装备等不变，只更换衣着描述。"
                f"在底部法宝区域添加一行标注：[{tag}]。"
                f"返回 JSON：{{\"design_prompt\": \"...\"}}"
            )

            result = self.llm.generate_json(
                system_prompt=self.VARIANT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            design_prompt = result.get("design_prompt", "")
            if not design_prompt:
                return None

            # Get character_id
            char_id, _ = db.get_or_create_character(character_name)

            # Create outfit record
            outfit_id = db.create_character_outfit(
                character_id=char_id,
                tag=tag,
                prompt=design_prompt,
                image_path="",  # ImageGenerator fills this
                is_default=0,
                activation_condition=activation_condition,
            )
            return outfit_id
        except Exception as e:
            db.log(self.agent_name, "generate_outfit_variant", "failed",
                   {"error": str(e), "character": character_name, "tag": tag},
                   level="ERROR")
            return None
