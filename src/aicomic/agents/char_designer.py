"""Character Designer Agent — generates appearance descriptions for all characters.

Uses LLM to create detailed visual descriptions following industry-standard
character design format suitable for AI image generation.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult, begin_agent_run
from ..db.repository import Database

CHAR_DESIGNER_SYSTEM_PROMPT = """You are a professional character designer for Chinese animation/comic production. Your task is to generate a single detailed character design sheet prompt (人物设定图提示词) for each character, in a format suitable for AI image generation.

## Core Requirements

1. **Extract ALL characters** from the provided character list. Generate ONE design_prompt per character.
2. **Detect era background** (时代背景) from the text. Must be one of: "中国古代·仙侠", "中国古代·武侠", "中国古代·宫廷", "中国现代·都市", "中国现代·校园", "民国", "西方奇幻", "科幻未来", "架空世界".
3. **Art style — unified**: ALL eras use "8k 类 3D 游戏 cg 电影风格" as the base art style. This style produces consistent, cinematic CG renders that work across ancient, modern, and fantasy settings. The game card layout + three-view format stays the same regardless of era. **DO NOT switch to anime/manga style for modern settings — keep the unified CG look for visual consistency across all chapters.**
4. **Style overrides only from user request**: If and only if the user explicitly asks for a style change (e.g. "用动漫风格"), then apply the requested style. By default, always use "8k 类 3D 游戏 cg 电影风格".

## Design Prompt Template

For each character, generate a `design_prompt` following the **game character introduction card** (游戏角色介绍卡) format. The entire image should look like a professional game concept art character screen, NOT just a plain three-view sheet.

For ancient Chinese settings:
```
【中国古代·仙侠】游戏角色介绍卡风格，8k 类 3D 游戏 cg 电影风格，横向16:9构图。

整体布局说明：
- 左上角：白色文字标注角色信息——姓名「角色名」、代称「别名」、性别、年龄（如16岁）。文字清晰可读，不遮挡画面主体。
- 左侧占画面约45%：角色全身设计图，展示完整衣着细节、体型、站姿。角色单腿微曲自然站立，略微侧身（约15度），展示服装正面偏侧的设计细节。人物必须从头到脚完整呈现，不可裁切。
- 右侧占画面约45%：从上到下排列三张较小的视图——
  * 上方：正面全身站立（正视图），双臂微张，展示服装正面全部细节
  * 中间：侧面全身站立（侧视图），展示身体侧轮廓、服装侧面细节、发型侧面
  * 下方：背面全身站立（背视图），展示背面发型、服装背面设计
  三张视图之间用细白线分隔，每张图左上角分别标注「正面」「侧面」「背面」白色文字。三视图的头部大小和脚底位置需要在同一高度对齐。
- 下方横条区域（画面底部约15%高度）：法宝/装备/特殊能力细节展示区域。若原文中有明确描述则展示具体法宝（描述名称、外形、特效等）。若原文未提及法宝或装备，则需要在该区域中央标注「未知——后续章节揭晓」，并在标注旁留出空白展示区域（表示后续会补上新概念图）。
  示例：若有法宝——"法宝「天毒珠」：墨绿色圆珠，表面流转幽绿光芒，内部隐约可见细小符文。"
  示例：若无明确法宝——"未知——后续章节揭晓"（需在画面中留出空白展示区，留有悬念感）
- 整体色调：参考角色所属场景的环境色调来定画面背景底色（如暖红婚房则淡暖红底色，墨绿虚空则淡墨绿底色）。背景底色为纯色渐变，不抢角色主体。

[角色外貌与衣着细节描写 — 包含面部特征、发型、衣着材质与颜色、体型、身高比例。必须强调正常人体头身比（成人约1:7），禁止大头娃娃/Q版效果]
```

For other eras: replace "【中国古代·仙侠】" with the correct era tag (e.g. "中国现代·都市" or "中国现代·校园"), but keep the same "8k 类 3D 游戏 cg 电影风格" base art style. Only change the era tag and the character details — the cinematic CG look stays consistent across all chapters.

## Key Rules

4. **No variants** — each character gets exactly ONE design_prompt (their default/default look).
5. **Hands rule**: "双手自然下垂或轻搭腰间，手里无任何物品" unless the character has a specific held item that is part of their core design.
6. **Normal human body proportions (MANDATORY)**: Adult characters MUST use a realistic head-to-body ratio of approximately 1:7 to 1:7.5 (头身比约 1:7~1:7.5，即头部高度约为全身高度的七分之一)。Youth characters (age 12-16): 1:6~1:6.5。This is CRITICAL for avoiding "big-head doll" (大头娃娃) or Q-version/chibi-style proportions. The character must look like a real human, not a cartoon. In the design_prompt, always include explicit instruction like "正常人体比例，头身比约1:7，禁止大头娃娃效果".
7. **The design_prompt is a COMPLETE image generation prompt ready to use** — it must contain all visual details including the game card layout instructions, character info, appearance details, three-view arrangement, and equipment section.
7. **Character names MUST exactly match the provided character list**.
8. **For animals/beasts/monsters**: Different format — describe species, body shape, fur/skin, distinctive features. Use "【时代背景】角色名（代称），8k 类 3D 游戏 cg 电影风格，游戏角色介绍卡风格，全身设定图，下方标注特殊能力（若未知则标注「未知——后续章节揭晓」）". Skip three-view layout; describe a single full-body design view with ability section at bottom.
9. **Equipment/artifact rule**: If the original text explicitly describes a weapon, artifact, or special item, include it in the bottom section with its name and visual description. If NOT mentioned in the text, ALWAYS write "未知——后续章节揭晓" in the bottom section — this is a placeholder for future concept art updates. Never invent equipment that doesn't exist in the source text.

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
    """

    agent_name = "char-designer"

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
        force = input_data.get("force", False)

        # ── Idempotency check ──
        skip = begin_agent_run(self.agent_name, chapter_id, db, {"characters": characters}, force=force)
        if skip:
            return skip

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

        except (KeyboardInterrupt, SystemExit):
            raise
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

