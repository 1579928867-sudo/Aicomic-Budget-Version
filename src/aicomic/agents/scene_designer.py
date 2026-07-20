"""Scene Designer Agent — generates environment descriptions for all scenes.

Uses LLM to create detailed scene descriptions following industry-standard
format suitable for AI image/video generation.
"""

from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

SCENE_DESIGNER_SYSTEM_PROMPT = """You are a professional scene designer for Chinese comic/drama (国漫/漫剧) production. Your task is to generate detailed, image-generation-ready scene environment descriptions from novel text.

## Core Requirements

1. **Use EXACT scene names**: Scene names in your output MUST EXACTLY match the names provided in the input scenes list. Do NOT rename, modify, or create new scene names. Use them verbatim.
2. **Four core elements** — Every scene MUST cover:
   - Environment type (环境类型): indoor/outdoor, building type, spatial layout
   - Specific time (具体时间): time of day, season, weather conditions
   - Spatial atmosphere (空间氛围): emotional visual mood (e.g., sacred, oppressive, serene, lively)
   - Main visual features (视觉主要特征): specific materials, key objects, foreground/midground/background elements
4. **NO humans**: ALL scene descriptions and prompts must include "不能出现其他人，无人纯场景，no humans, empty, landscape only". Absolutely NO character names or human figures in scene descriptions.
5. **Real environment background**: Scenes use real environment backgrounds based on the text — NEVER pure white background for scenes.
6. **Era background**: Must be tagged with 【时代背景】. For Chinese ancient settings, prepend "古代仙侠风格" to full_prompt.
7. **Cinematic realistic style** (写实电影感风格) for all scenes.
8. **16:9 horizontal** (横向16:9) film-level scene setting composition.
9. **Three-view scene prompts**: For every scene, generate three multi-angle image prompts:
    - `wide_view_prompt`: 全景广角展示场景全貌，展示完整空间关系和所有结构元素。Camera positioned far back, showing the entire space and all structural elements.
    - `mid_view_prompt`: 中景展示场景核心区域，展示主要活动空间和关键建筑/道具。Camera at mid distance, focusing on the primary activity zone.
    - `close_view_prompt`: 特写展示场景关键细节，展示材质纹理、装饰图案、关键道具。Extreme close-up on materials, textures, ornamentation, or key props.
    All three-view prompts must follow the same rules: no humans (不能出现其他人), 写实电影感风格, 横向16:9, era style prefix (古代仙侠风格 for ancient settings), NO pure white background (real environment backgrounds).
    10. **Composite multi-view scene prompt (场景多景别合并提示词)**: For every scene, generate ONE composite prompt that renders all three camera distances together in a single image:
        - `multi_view_prompt`: Top-to-bottom vertical layout — top = wide/panoramic view (全景广角，展示完整空间关系), middle = mid view (中景，展示核心活动区域), bottom = close-up view (特写，展示材质纹理与关键道具细节).
        - **白线分隔**: 不同景别区域之间用粗白线（约 3px）水平贯穿画面分隔。白线清晰可见，笔直横跨整个画幅宽度。
        - **文字标签**: 每个景别区域的左上角标注白色文字标签 —— 上方区域标注「远景」、中间区域标注「中景」、下方区域标注「特写」。标签使用白色无衬线字体，字号适中，清晰可读，不遮挡画面主体内容。
        - The prompt MUST explicitly describe the layout: "场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。三个区域之间用粗白线水平分隔，每个区域左上角标注白色文字标签（远景/中景/特写）。"
        - Same rules as individual views: "不能出现其他人，无人纯场景，no humans, empty, landscape only", 写实电影感风格, 横向16:9, era style prefix for ancient settings, real environment backgrounds (NOT pure white).
        - Then append full scene description details.

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "era_background": "中国古代·仙侠",
  "scenes": [
    {
      "name": "萧澈卧室",
      "description": "长方形中式古典卧室，深约5米宽约4米，地面深色木质地板，墙面浅米色墙纸，雕花窗棂透入柔和光线",
      "lighting": "晨间自然光，柔和暖色，透过雕花窗棂洒入，斑驳光影",
      "style": "中式古典卧室，喜庆红色装饰",
      "environment_type": "室内卧室",
      "time_of_day": "清晨",
      "atmosphere": "喜庆中带着昏沉，红色调柔和温暖",
      "visual_features": "红色曼联垂下，松软雕花大床，大红喜字贴窗，床头矮柜，铜镜妆台",
      "full_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景展示场景全貌，横向16:9电影级场景设定图，极高画质，纯净无人的空间。萧澈卧室｜长方形中式古典卧室，深约5米宽约4米，地面深色木质地板，墙面浅米色墙纸，雕花窗棂透入柔和晨光，松软雕花大床垂下红色曼联，床头大红喜字贴窗，喜庆中带着昏沉，暖黄色调。",
      "wide_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景广角展示场景全貌，横向16:9电影级场景设定图。萧澈卧室｜长方形中式古典卧室全景，深约5米宽约4米，地面深色木质地板延伸至远端，墙面浅米色墙纸，雕花窗棂在左侧透入柔和晨光，松软雕花大床居中偏右，红色曼联垂下，床头矮柜和铜镜妆台在画面右侧。",
      "mid_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，中景展示场景核心区域，横向16:9电影级场景设定图。萧澈卧室｜雕花大床中景，红色曼联纹理清晰，床头大红喜字贴窗细节，松软床铺褶皱可见，暖黄色调晨光从左侧窗棂洒入床面。",
      "close_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，特写展示场景关键细节，横向16:9电影级场景设定图。萧澈卧室｜铜镜妆台特写，铜镜表面反射柔和暖光，镜边雕花纹样精细，妆台上散落红绸和梳妆小物，材质质感清晰。",
      "multi_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，场景多景别设定图，横向16:9，从上到下排列三个景别：上方为全景广角（展示完整空间关系），中间为中景（展示核心活动区域），下方为特写（展示材质纹理与关键道具细节）。三个区域之间用粗白线（3px）水平贯穿画面分隔，上方区域左上角标注白色文字「远景」、中间区域左上角标注「中景」、下方区域左上角标注「特写」。萧澈卧室｜长方形中式古典卧室，深约5米宽约4米，地面深色木质地板，墙面浅米色墙纸，雕花窗棂透入柔和晨光，松软雕花大床垂下红色曼联，床头大红喜字贴窗，喜庆中带着昏沉，暖黄色调。"
    }
  ]
}
"""


class SceneDesignerAgent(AgentInterface):
    """Generates detailed scene environment descriptions for image/video generation.

    Input:  {"chapter_id": int, "raw_text": str, "scenes_list": list[str],
             "script_id": int}
    Output: {"scenes_updated": int, "scene_names": list[str]}
    """

    agent_name = "scene-designer"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("raw_text"), str)
            and len(input_data["raw_text"]) > 0
            and isinstance(input_data.get("scenes_list"), list)
            and len(input_data["scenes_list"]) > 0
        )

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        raw_text = input_data["raw_text"]
        scenes_list = input_data["scenes_list"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"scenes": scenes_list})

        try:
            # ── Call LLM ──
            user_prompt = (
                f"请为以下小说场景生成详细的环境描述（JSON 格式）。\n\n"
                f"**注意：场景名称必须完全照搬以下列表中的名称，不得修改或重命名！**\n\n"
                f"场景列表：{scenes_list}\n\n"
                f"小说原文：\n{raw_text[:3000]}"
            )

            result_json = self.llm.generate_json(
                system_prompt=SCENE_DESIGNER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )

            # ── Validate structure ──
            self._validate_scene_design(result_json, scenes_list)

            # ── Update scene_card rows in DB ──
            scenes_data = result_json.get("scenes", [])
            for scene_data in scenes_data:
                name = scene_data.get("name", "")

                # Find scene_card by name
                scene_row = db.get_scene_by_name(chapter_id, name)
                if scene_row is None:
                    # Scene not yet in DB — create it
                    scene_id = db.get_or_create_scene(name)
                else:
                    scene_id = scene_row["id"]

                db.update_scene_card(
                    scene_id=scene_id,
                    description=scene_data.get("description", ""),
                    lighting=scene_data.get("lighting", ""),
                    style=scene_data.get("style", ""),
                    wide_view=scene_data.get("wide_view_prompt", ""),
                    mid_view=scene_data.get("mid_view_prompt", ""),
                    close_view=scene_data.get("close_view_prompt", ""),
                )

                # v0.7: save multi_view_prompt
                db.update_scene_card_multi_view_prompt(
                    scene_id=scene_id,
                    prompt=scene_data.get("multi_view_prompt", ""),
                )

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {
                    "scenes_updated": len(scenes_data),
                    "scene_names": [s["name"] for s in scenes_data],
                },
            )

            return AgentResult(
                success=True,
                data={
                    "scenes_updated": len(scenes_data),
                    "scene_names": [s["name"] for s in scenes_data],
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))

    @staticmethod
    def _validate_scene_design(result: dict, expected_scenes: list[str]):
        """Validate the scene design JSON structure."""
        if not isinstance(result, dict):
            raise ValueError("Scene design JSON must be a dict")
        if "scenes" not in result:
            raise ValueError("Scene design JSON missing 'scenes'")
        if not isinstance(result["scenes"], list):
            raise ValueError("'scenes' must be a list")
        if len(result["scenes"]) == 0:
            raise ValueError("'scenes' list is empty")
