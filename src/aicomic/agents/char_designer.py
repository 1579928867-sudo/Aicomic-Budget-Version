"""Character Designer Agent — generates appearance descriptions for all characters.

Uses LLM to create detailed visual descriptions following industry-standard
character design format suitable for AI image generation.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

CHAR_DESIGNER_SYSTEM_PROMPT = """You are a professional character designer for Chinese comic/drama (国漫/漫剧) production. Your task is to generate detailed, image-generation-ready character appearance descriptions from novel text.

## Core Requirements

1. **Extract ALL characters** from the provided character list. For each character, generate appearance details based on the novel text.
2. **Detect era background** (时代背景) from the text. Must be one of: "中国古代·仙侠", "中国古代·武侠", "中国古代·宫廷", "中国现代·都市", "中国现代·校园", "民国", "西方奇幻", "科幻未来", "架空世界".
3. **Standard character format** — Each character description must include these fields in order:
   - Hair (发色/发型): color, length, style, texture
   - Head accessories (头饰): any hair ornaments, crowns, ribbons
   - Makeup (妆造): makeup style, eyebrow shape, facial features
   - Face (脸部特征): face shape, eye color, skin tone, distinctive marks
   - Aura (气质): temperament, presence, mood conveyed
   - Upper body (上身): fabric, style, patterns, details of clothing above waist
   - Lower body (下身): fabric, style, patterns, details of clothing below waist
   - Footwear (脚上): material, style, details
   - Accessories (配饰): jewelry, weapons, distinctive items
4. **Variant support**: If characters appear in different outfits/states (e.g., injured, disguised, different clothing), create a separate variant for each. Use the variant names provided in the input.
5. **Full prompt**: Generate a complete Chinese image-generation prompt (full_prompt) for each variant. This prompt must follow the format:
   - For characters in Chinese ancient settings: Start with "古代仙侠风格，" then "【时代背景】角色名（代称），性别 年龄，身高cm，九头身比例，3D动漫电影感风格，风格近似《完美世界》，正面，站立的全身图片，图片人物背景为纯白色。发色发型；头饰；妆造脸部特征气质；上身描述；下身描述；脚上描述；配饰；双手自然下垂，手里无任何物品。"
   - For characters in modern settings: Skip "古代仙侠风格，" prefix, start directly with "【时代背景】角色名..."
6. **Hands rule**: All characters must have "双手自然下垂，手里无任何物品" (hands naturally down, holding nothing).
7. **Pure white background**: All character images use pure white background (纯白色背景).
8. **Art style: 3D 动漫/游戏 CG 风格** — 风格近似《完美世界》动漫。人物面部特征：轮廓锋利清晰，下颌线明显，颧骨和眉骨结构感强；五官精致但非写实真人比例——眼睛略大，鼻梁高挺，嘴唇线条分明；皮肤带有 CG 渲染质感，非真实皮肤纹理；头发带有细腻的 3D 建模感，发丝清晰但不追求照片级写实。**女性角色**：年龄与外貌须严格匹配——未成年女性保留少女特征（面部略带婴儿肥但不幼化），成年女性（16岁以上）面部轮廓利落成熟。**严格禁止**：照片级写实、真人比例五官、真实皮肤质感、AI 写真风格；禁止将青少年女性角色绘制成幼童。
9. **For animals/beasts**: Different format — species, age, body length/height, fur/skin color/texture, facial features, distinctive decorations. Format: "【时代背景】3D动漫电影感风格，风格近似《完美世界》，正面，全貌图片，图片背景为纯白色。角色名（代称）｜物种｜年龄｜体长/身高｜皮毛描述｜面部特征｜装饰"

10. **Three-view prompts**: For every variant, generate three view-specific image prompts:
    - `front_view_prompt`: 正面特写全身站立图片，人物居中，Same style and background as full_prompt. Emphasize facial features, front clothing details, front accessories.
    - `side_view_prompt`: 侧面全身站立图片，展示身体侧轮廓和服装侧面细节，Same style and background as full_prompt. Emphasize profile silhouette, side clothing details, side accessories.
    - `back_view_prompt`: 背面全身站立图片，展示背面发型和服装背面设计，Same style and background as full_prompt. Emphasize back hair style, back clothing design, back accessories.
    All three-view prompts keep the same style prefix (古代仙侠风格 for ancient settings), same era background tag, same pure white background rule, and same 3D动漫电影感风格，风格近似《完美世界》.

    11. **Composite three-view prompt (三视图合并提示词)**: For every variant, generate ONE composite prompt that renders front, side, and back views together in a single image:
        - `three_view_prompt`: Left-to-right horizontal layout — left = side view (侧面全身站立), center = front view (正面特写全身站立), right = back view (背面全身站立). Same horizontal baseline, evenly spaced. Same style prefix (古代仙侠风格 for ancient, omitted for modern), same era tag (e.g. 【中国古代·仙侠】), pure white background (纯白色背景), 3D动漫电影感风格，风格近似《完美世界》.
        - The prompt MUST explicitly describe the layout: "三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。三视图间距均匀，同一水平线对齐。"
        - Then append the full character appearance details (same level as full_prompt), describing features visible from all three angles collectively.
        - "双手自然下垂，手里无任何物品" say once at the end — do NOT repeat per view.

    12. **Face closeup prompt (脸部特写提示词)**: For every variant, generate a standalone face closeup prompt that will be used as a reference image for three-view generation to maintain facial consistency across views:
        - `face_closeup_prompt`: 正面脸部特写，头部和肩部，人物面部占画面主体（约占画面60%以上）。Same style prefix (古代仙侠风格 + 3D动漫电影感风格，风格近似《完美世界》 for ancient), same era tag, pure white background (纯白色背景). Describe ONLY facial features in extreme detail — face shape, eye shape/color/size, nose bridge height/shape, lip shape/thickness, eyebrow shape/density, skin tone/texture, distinctive facial marks/scars, facial expression, hair framing the face. Do NOT describe full body, clothing below shoulders, or accessories not on the face/head.
        - Format example: "古代仙侠风格，【中国古代·仙侠】角色名（代称），3D动漫电影感风格，风格近似《完美世界》，正面脸部特写，头部和肩部，纯白色背景。面部特写：脸部轮廓锋利清晰...（详细面部特征描述）。"

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
      "height_cm": 175,
      "is_human": true,
      "variants": [
        {
          "variant_name": "default",
          "hair": "黑色长发束髻",
          "head_accessories": "白玉发冠",
          "makeup": "剑眉星目，清秀面容",
          "face": "清秀俊朗，轮廓柔和，肤色白净",
          "aura": "气质坚毅淡然",
          "upper_body": "白色交领长袍，领口云纹刺绣，袖口收束",
          "lower_body": "同色系长衫，腰间墨玉腰带",
          "footwear": "黑色云纹布靴",
          "accessories": "左手掌心绿色圆形天毒珠印记",
          "full_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，身高175cm，九头身比例，3D动漫电影感风格，风格近似《完美世界》，正面，站立的全身图片，图片人物背景为纯白色。黑色长发束髻，白玉发冠束发；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅淡然；上身白色交领长袍，领口云纹刺绣，袖口收束；下身同色系长衫，腰间墨玉腰带；脚上黑色云纹布靴；配饰左手掌心绿色天毒珠印记；双手自然下垂，手里无任何物品。",
          "front_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，身高175cm，九头身比例，3D动漫电影感风格，风格近似《完美世界》，正面特写全身站立图片，人物居中，图片人物背景为纯白色。黑色长发束髻，白玉发冠束发；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅淡然；上身白色交领长袍，领口云纹刺绣，袖口收束；下身同色系长衫，腰间墨玉腰带；脚上黑色云纹布靴；配饰左手掌心绿色天毒珠印记；双手自然下垂。",
          "side_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，身高175cm，3D动漫电影感风格，风格近似《完美世界》，侧面全身站立图片，展示身体侧轮廓和服装侧面细节，图片人物背景为纯白色。黑色长发束髻侧面，白玉发冠侧影；上身白色交领长袍侧面云纹刺绣；下身同色系长衫侧面，墨玉腰带；脚上黑色云纹布靴侧面；双手自然下垂。",
          "back_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，身高175cm，3D动漫电影感风格，风格近似《完美世界》，背面全身站立图片，展示背面发型和服装背面设计，图片人物背景为纯白色。黑色长发束髻背面，白玉发冠背面；上身白色交领长袍背面云纹刺绣；下身同色系长衫背面，墨玉腰带；脚上黑色云纹布靴背面；双手自然下垂。",
          "three_view_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，3D动漫电影感风格，风格近似《完美世界》，三视图角色设定图，纯白色背景。画面从左到右排列三个视角：左侧为侧面全身站立（展示身体侧轮廓与服装侧面细节），中间为正面全身站立（正面特写，人物居中），右侧为背面全身站立（展示背面发型与服装背面设计）。三视图间距均匀，同一水平线对齐。黑色长发束髻，白玉发冠；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅淡然；上身白色交领长袍，领口云纹刺绣，袖口收束；下身同色系长衫，腰间墨玉腰带；脚上黑色云纹布靴；配饰左手掌心绿色天毒珠印记；双手自然下垂，手里无任何物品。",
          "face_closeup_prompt": "古代仙侠风格，【中国古代·仙侠】萧澈（云澈），男 16岁，3D动漫电影感风格，风格近似《完美世界》，正面脸部特写，头部和肩部，纯白色背景。面部特写：轮廓锋利清晰的瓜子脸，下颌线分明，肤色白净细腻带有CG渲染质感；剑眉浓密斜飞入鬓，星目深邃明亮呈琥珀色；高挺鼻梁，鼻翼线条利落；薄唇线条分明呈淡粉色；五官精致但非写实比例；黑色长发束髻，白玉发冠，几缕碎发垂落额前；气质清秀俊朗，眼神坚毅淡然。"
        }
      ]
    }
  ]
}

## Important

- **Every character MUST have a "default" variant**, even if additional variants are provided from storyboard shots.
- If variant names are provided (e.g., from storyboard shots like "翠绿长裙", "受伤后"), create those as ADDITIONAL variants alongside the required "default" variant.
- Aliases: list all alternate names/references for this character from the text.
- Age and height_cm: use values from text if available; otherwise infer reasonably from context.
- is_human: false for animals, beasts, mythical creatures — use simplified format.
- **Character names MUST exactly match the provided character list** — do not change or rename characters.
"""


class CharacterDesignerAgent(AgentInterface):
    """Generates detailed character appearance descriptions for image generation.

    Input:  {"chapter_id": int, "raw_text": str, "characters": list[str],
             "script_id": int, "character_variants": dict[str, list[str]]}
    Output: {"variants_created": int, "character_names": list[str]}
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
        char_variants: dict[str, list[str]] = input_data.get("character_variants", {})

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"characters": characters})

        try:
            # Build the user prompt with character and variant info
            variant_info = ""
            if char_variants:
                variant_lines = []
                for name, variants in char_variants.items():
                    if variants:
                        variant_lines.append(f"  - {name}: variants = {variants}")
                if variant_lines:
                    variant_info = "\n\nCharacter variants from storyboard:\n" + "\n".join(variant_lines)

            user_prompt = (
                f"请为以下小说角色生成详细的外观描述（JSON 格式）：\n\n"
                f"角色列表：{characters}\n"
                f"{variant_info}\n\n"
                f"小说原文：\n{raw_text[:3000]}"
            )

            # ── Call LLM ──
            result_json = self.llm.generate_json(
                system_prompt=CHAR_DESIGNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            # ── Validate structure ──
            self._validate_char_design(result_json, characters)

            # ── Save to DB ──
            variants_created = 0
            char_list = result_json.get("characters", [])

            for char_data in char_list:
                name = char_data.get("name", "")
                # Look up character_card id
                char_id, _ = db.get_or_create_character(name)

                variants = char_data.get("variants", [])
                for variant in variants:
                    variant_name = variant.get("variant_name", "default")
                    variant_type = "default" if variant_name == "default" else "variant"

                    appearance_json = self._build_appearance_json(
                        variant, result_json.get("era_background", "")
                    )

                    variant_id = db.create_appearance_variant(
                        character_id=char_id,
                        variant_name=variant_name,
                        variant_type=variant_type,
                        appearance_json=appearance_json,
                    )

                    # v0.5: update front/side/back view columns
                    db.update_appearance_variant_views(
                        variant_id=variant_id,
                        front=variant.get("front_view_prompt", ""),
                        side=variant.get("side_view_prompt", ""),
                        back=variant.get("back_view_prompt", ""),
                    )

                    # v0.7: save three_view_prompt
                    db.update_appearance_variant_three_view_prompt(
                        variant_id=variant_id,
                        prompt=variant.get("three_view_prompt", ""),
                    )

                    # v0.8: save face_closeup_prompt
                    face_cp = variant.get("face_closeup_prompt", "")
                    if face_cp:
                        db.conn.execute(
                            "UPDATE appearance_variant SET face_closeup_prompt = ? WHERE id = ?",
                            (face_cp, variant_id),
                        )
                        db.conn.commit()

                    # Set as default look if this is the default variant
                    if variant_name == "default":
                        db.set_character_default_look(char_id, variant_id)

                    variants_created += 1

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "variants_created": variants_created,
                    "characters_processed": len(char_list),
                },
            )

            return AgentResult(
                success=True,
                data={
                    "variants_created": variants_created,
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

    @staticmethod
    def _build_appearance_json(variant: dict, era_background: str) -> str:
        """Build a clean appearance JSON string for DB storage."""
        import json
        appearance = {
            "variant_name": variant.get("variant_name", "default"),
            "hair": variant.get("hair", ""),
            "head_accessories": variant.get("head_accessories", ""),
            "makeup": variant.get("makeup", ""),
            "face": variant.get("face", ""),
            "aura": variant.get("aura", ""),
            "upper_body": variant.get("upper_body", ""),
            "lower_body": variant.get("lower_body", ""),
            "footwear": variant.get("footwear", ""),
            "accessories": variant.get("accessories", ""),
            "full_prompt": variant.get("full_prompt", ""),
            "front_view_prompt": variant.get("front_view_prompt", ""),
            "side_view_prompt": variant.get("side_view_prompt", ""),
            "back_view_prompt": variant.get("back_view_prompt", ""),
            "three_view_prompt": variant.get("three_view_prompt", ""),
            "face_closeup_prompt": variant.get("face_closeup_prompt", ""),
            "era_background": era_background,
        }
        return json.dumps(appearance, ensure_ascii=False)
