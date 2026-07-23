"""Shot Visualizer Agent — generates per-shot composite image-generation prompts.

Combines character appearance prompts, scene environment prompts, and
shot-specific action/dialogue/camera into ready-to-use image-gen prompts
for each storyboard shot.
"""

import json
from typing import Any

from ..interface import AgentInterface, AgentResult
from ..db.repository import Database

SHOT_VISUALIZER_SYSTEM_PROMPT = """You are a professional cinematographer and visual composer for Chinese comic/drama (国漫/漫剧) production. Your task is to generate detailed, image-generation-ready visual prompts for each storyboard shot by combining character reference, scene reference, and shot-specific action.

## Input

You will receive:
1. **Character references** — each character's visual description (full_prompt for AI image generation)
2. **Scene references** — each scene's environment description (full_prompt for AI image generation)
3. **Storyboard shots** — each shot's shot_num, scene_name, narration (what happens), dialogue (who says what), camera_movement (shot type, possibly multi-stage), and which characters appear

## Your Task

For EACH shot, generate a composite image prompt that blends:
- The scene's environment (where we are)
- Each character's appearance (BUT only the aspects visible from the camera angle)
- The specific action/moment happening in this shot
- The camera composition (framing, angle, movement — including multi-stage transitions)

## Critical Rules

1. **Scene as foundation**: Start with the scene's full_prompt as the environmental backdrop.
2. **Characters in action**: Characters must be described DOING the shot's action, NOT in their "standing pose" reference. Use the character's appearance details (clothing, hair, face) but pose them dynamically according to the narration.
3. **Dialogue-aware visuals**: When a shot has dialogue:
   - Describe the speaking character's MOUTH as open/moving, lips forming words
   - Show the character's FACIAL EXPRESSION matching the dialogue emotion (e.g. 困惑, 欣喜, 愤怒)
   - If the dialogue has emotion hints like "萧澈（困惑）" — use that: "萧澈眉头微蹙，嘴唇翕动，神色困惑"
   - For multi-character dialogue shots, describe each character's reaction and posture
   - The image_prompt should visually "read" like a freeze-frame of someone speaking
4. **Camera-aware composition with multi-stage transitions**: camera_movement may contain "→" separated stages (e.g. "CU→MS", "LS→FT→CU"). For transitions:
   - **CU→MS** (近景→中景): Describe a gradual pull-back — "镜头从面部近景缓缓拉远至中景，展现人物半身及身后环境"
   - **MS→CU** (中景→近景): Describe a gradual push-in — "镜头从中景缓缓推进至近景，聚焦人物面部表情"
   - **LS→MS** (远景→中景): Describe approaching — "镜头从远景推进至中景，人物逐渐清晰"
   - **CU→ECU** (近景→大特写): Describe extreme focus — "镜头从近景推至大特写，聚焦于[具体细节]"
   - **Push→CU** (推进→近景): Describe push to close — "镜头推进至近景特写，突出人物神情"
   - **Three-stage (e.g. LS→FT→CU)**: "镜头从远景建立空间，跟随人物移动，最终推进至近景特写"
   - Single-camera (e.g. "CU", "MS"): Use the standard framing rules below
5. **Standard camera framing** (for single-camera shots or describing the final frame):
   - LS (远景): Full body ~1/3 frame, environment dominant, wide establishing view
   - MS (中景): Knees up, balanced character + environment
   - CU (近景): Chest up, focus on expression and emotion
   - ECU (特写): Extreme close-up on specific detail (eyes, hands, props)
   - HA (俯拍): High angle, looking down, compresses space
   - LA (仰拍): Low angle, looking up, emphasizes height/power
   - OTS (过肩镜头): Over one character's shoulder to another
   - FT (跟拍): Camera follows character movement
   - Pan (摇镜): Horizontal sweeping view
   - Push (推镜): Camera pushing forward, building tension
6. **Avoid redundancy**: Don't copy-paste the full character reference. Extract only what's VISIBLE from this camera angle. A CU shot doesn't need shoe details. A back-view shot doesn't need face details.
7. **Style consistency**: ALL prompts must use "写实电影感风格" (cinematic realistic style). For Chinese ancient settings, prepend "古代仙侠风格". 16:9 horizontal composition (横向16:9).
8. **Moment-specific**: Describe the EXACT moment — expression, gesture, lighting, atmosphere — not a generic scene. If a character is speaking dialogue, show their mouth/speaking posture. If there's an emotional beat, capture it.
9. **Chinese prompt**: All image_prompt text must be in Chinese (except technical terms like "16:9", "8K").
10. **No redundant scene descriptions**: Don't repeat "不能出现其他人，无人纯场景" from scene references — shots WITH characters should have characters. Only pure establishing shots should be character-free.

## Output Format

Return ONLY valid JSON in this exact structure (no other text):

{
  "shots": [
    {
      "shot_num": 1,
      "image_prompt": "古代仙侠风格，写实电影感风格，横向16:9，8K超高清。中式古典婚房内，红色幔帐垂下的大床，晨光透过雕花窗棂洒入。萧澈身穿大红喜衣缓缓睁开眼睛，黑色长发散乱在枕上，表情迷茫，嘴唇微张似乎在自语，双手撑着床面坐起身。镜头从近景缓缓拉远至中景，人物居中，暖黄色调，柔和光线，电影级景深。",
      "composition": "近景→中景拉远（CU→MS），开场聚焦人物迷茫面容，随后展现婚房空间。人物居中偏左，床铺占画面下2/3，红色幔帐框取画面上部",
      "mood": "温暖柔和的晨光，喜庆中带着朦胧和迷茫"
    }
  ]
}

## Field Descriptions

- **image_prompt**: Complete Chinese image-generation prompt (~150-300 chars). Must include: style prefix, scene environment, character action/pose/appearance, camera framing, lighting, mood. If shot has dialogue, the character must be shown speaking. For "→" camera stages, describe the visual transition. Ready to paste into an image generator.
- **composition**: Brief composition note (1-2 sentences) describing framing, character placement, depth of field. For multi-stage camera, describe the transition: "近景→中景拉远，开场聚焦人物面容，随后展现环境空间"
- **mood**: Brief mood/lighting note (1 sentence) describing the emotional tone and color temperature.
"""


class ShotVisualizerAgent(AgentInterface):
    """Generates per-shot image prompts by combining char + scene + shot data.

    Input:  {"chapter_id": int, "script_id": int}
    Output: {"shots_processed": int, "shot_ids": list[int]}
    """

    agent_name = "shot-visualizer"

    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        return (
            isinstance(input_data.get("chapter_id"), int)
            and isinstance(input_data.get("script_id"), int)
        )

    def _build_reference_context(self, db: Database, script_id: int) -> dict:
        """Load all reference data from DB needed for shot visualization.

        v0.12: Reads from character_outfit + shot_character_outfit junction table
        instead of the deprecated appearance_variant.
        """
        # Load storyboard shots
        shots = db.get_storyboard_shots(script_id)
        if not shots:
            raise ValueError(f"No storyboard shots found for script_id={script_id}")

        # Collect all character IDs across shots
        all_char_ids: set[int] = set()
        for shot in shots:
            char_ids_raw = shot.get("char_ids", "[]")
            try:
                char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
            except (json.JSONDecodeError, TypeError):
                char_ids = []
            all_char_ids.update(char_ids)

        # Build character reference from character_outfit (v0.12)
        # Key: "{name}/{outfit_tag}", Value: outfit design_prompt
        char_refs: dict[str, str] = {}
        char_id_to_name: dict[int, str] = {}

        for char_id in all_char_ids:
            char_rows = db.conn.execute(
                "SELECT name FROM character_card WHERE id = ?", (char_id,)
            ).fetchone()
            if not char_rows:
                continue
            char_name = char_rows["name"]
            char_id_to_name[char_id] = char_name

            # Read all outfits (prompts) for this character
            outfits = db.get_character_outfits(char_id)
            for outfit in outfits:
                tag = outfit.get("tag", "默认")
                prompt = outfit.get("prompt", "")
                if prompt:
                    char_refs[f"{char_name}/{tag}"] = prompt

        # Build scene reference: scene_name → composite prompt
        scene_refs: dict[str, str] = {}
        for shot in shots:
            scene_id = shot.get("scene_id")
            if scene_id and scene_id not in scene_refs:
                scene_rows = db.conn.execute(
                    "SELECT name, description, lighting, style FROM scene_card WHERE id = ?",
                    (scene_id,),
                ).fetchone()
                if scene_rows:
                    sr = dict(scene_rows)
                    scene_refs[sr["name"]] = (
                        f"【{sr.get('style', '')}】{sr.get('description', '')} "
                        f"光照：{sr.get('lighting', '')}"
                    )

        # Build shot list with per-character outfit tags from junction table
        simplified_shots = []
        for shot in shots:
            sd = dict(shot)
            char_ids_raw = sd.get("char_ids", "[]")
            try:
                char_ids = json.loads(char_ids_raw) if isinstance(char_ids_raw, str) else char_ids_raw
            except (json.JSONDecodeError, TypeError):
                char_ids = []

            # Per-character outfit tags (v0.12 junction table)
            char_outfits = db.get_shot_character_outfits(sd["id"])

            char_keys = []
            for cid in char_ids:
                cname = char_id_to_name.get(cid, f"char_{cid}")
                ctag = char_outfits.get(cid, "默认")
                char_keys.append(f"{cname}/{ctag}")

            simplified_shots.append({
                "shot_num": sd["shot_num"],
                "scene_name": self._find_scene_name(sd.get("scene_id"), db),
                "narration": sd.get("narration", ""),
                "dialogue": sd.get("dialogue", ""),
                "camera_movement": sd.get("camera_movement", "MS"),
                "character_keys": char_keys,
            })

        return {
            "char_refs": char_refs,
            "scene_refs": scene_refs,
            "shots": simplified_shots,
        }

    @staticmethod
    def _find_scene_name(scene_id, db: Database) -> str:
        """Look up scene name from scene_card table."""
        if not scene_id:
            return "未知场景"
        row = db.conn.execute(
            "SELECT name FROM scene_card WHERE id = ?", (scene_id,)
        ).fetchone()
        return row["name"] if row else "未知场景"

    def execute(self, input_data: dict[str, Any], db: Database) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        script_id = input_data["script_id"]

        # ── Idempotency check ──
        existing_status = db.get_agent_status(self.agent_name, chapter_id)
        if existing_status == "done":
            db.log(self.agent_name, chapter_id, "skipped", {"reason": "already done"})
            return AgentResult(success=True, data={"status": "skipped"})

        # ── Mark running ──
        db.set_agent_status(self.agent_name, chapter_id, "running")
        db.log(self.agent_name, chapter_id, "started", {"script_id": script_id})

        try:
            # ── Load reference context from DB ──
            ctx = self._build_reference_context(db, script_id)
            shots = ctx["shots"]
            if not shots:
                raise ValueError("No storyboard shots to process")

            # Build scene name lookup for shot context
            scene_names_map: dict[int, str] = {}
            orig_shots = db.get_storyboard_shots(script_id)
            for osd in orig_shots:
                sid = osd.get("scene_id")
                if sid and sid not in scene_names_map:
                    srow = db.conn.execute(
                        "SELECT name FROM scene_card WHERE id = ?", (sid,)
                    ).fetchone()
                    if srow:
                        scene_names_map[sid] = srow["name"]

            # Fill in scene names for each shot
            for s in ctx["shots"]:
                orig = next(
                    (o for o in orig_shots if o["shot_num"] == s["shot_num"]), None
                )
                if orig and orig.get("scene_id"):
                    s["scene_name"] = scene_names_map.get(orig["scene_id"], "未知场景")

            # ── Build LLM prompt ──
            user_prompt = self._build_llm_prompt(ctx)

            # ── Call LLM (single batch call) ──
            result_json = self.llm.generate_json(
                system_prompt=SHOT_VISUALIZER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=8192,
            )

            # ── Validate ──
            self._validate_output(result_json, len(shots))

            # ── Save image prompts to DB ──
            shot_results = result_json.get("shots", [])
            shot_num_to_db_id = {
                osd["shot_num"]: osd["id"] for osd in orig_shots
            }
            processed = 0
            for sr in shot_results:
                shot_num = sr.get("shot_num")
                image_prompt = sr.get("image_prompt", "")
                if shot_num and shot_num in shot_num_to_db_id:
                    db.update_shot_image_prompt(shot_num_to_db_id[shot_num], image_prompt)
                    processed += 1

            # ── Mark done ──
            db.set_agent_status(self.agent_name, chapter_id, "done")
            db.log(
                self.agent_name, chapter_id, "completed",
                {"shots_processed": processed, "total_shots": len(shots)},
            )

            return AgentResult(
                success=True,
                data={
                    "shots_processed": processed,
                    "total_shots": len(shots),
                    "shot_ids": [shot_num_to_db_id.get(sr["shot_num"]) for sr in shot_results],
                },
            )

        except Exception as e:
            db.set_agent_status(self.agent_name, chapter_id, "failed")
            db.log(self.agent_name, chapter_id, "failed", {"error": str(e)}, level="ERROR")
            return AgentResult(success=False, error=str(e))

    def _build_llm_prompt(self, ctx: dict) -> str:
        """Build the full user prompt with all reference data."""
        parts = []

        # Character references
        parts.append("## 角色定妆参考 (Character Design References)\n")
        for key, prompt in ctx["char_refs"].items():
            parts.append(f"### {key}\n{prompt}\n")

        # Scene references
        parts.append("## 场景环境参考 (Scene Environment References)\n")
        for key, prompt in ctx["scene_refs"].items():
            parts.append(f"### {key}\n{prompt}\n")

        # Shot list
        parts.append("## 分镜镜头列表 (Storyboard Shots)\n")
        for shot in ctx["shots"]:
            parts.append(
                f"--- Shot #{shot['shot_num']} ---\n"
                f"  场景: {shot.get('scene_name', '?')}\n"
                f"  运镜: {shot.get('camera_movement', 'MS')}\n"
                f"  角色: {shot.get('character_keys', [])}\n"
                f"  画面: {shot.get('narration', '')}\n"
                f"  对白: {shot.get('dialogue', '')}\n"
            )

        parts.append(
            "\n请为以上每个分镜镜头生成 image_prompt（完整中文出图提示词）、"
            "composition（构图说明）和 mood（氛围色调）。"
        )

        return "\n".join(parts)

    @staticmethod
    def _validate_output(result: dict, expected_count: int):
        """Validate the shot visualizer output structure."""
        if not isinstance(result, dict):
            raise ValueError("Shot visualizer JSON must be a dict")
        if "shots" not in result:
            raise ValueError("Shot visualizer JSON missing 'shots'")
        if not isinstance(result["shots"], list):
            raise ValueError("'shots' must be a list")
        if len(result["shots"]) == 0:
            raise ValueError("'shots' list is empty")
        if len(result["shots"]) != expected_count:
            raise ValueError(
                f"Expected {expected_count} shots, got {len(result['shots'])}"
            )
        for s in result["shots"]:
            if not s.get("image_prompt"):
                raise ValueError(f"Shot {s.get('shot_num', '?')} missing image_prompt")
