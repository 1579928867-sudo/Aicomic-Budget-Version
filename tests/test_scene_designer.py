"""Tests for Scene Designer Agent."""

import json
import tempfile
from pathlib import Path

from aicomic.agents.scene_designer import SceneDesignerAgent
from aicomic.db.repository import Database


# ── Fake LLM ──

class FakeLLM:
    """Returns a canned scene design JSON."""

    def __init__(self, canned_response: dict | None = None):
        self.canned = canned_response or _make_canned_response()
        self.calls: list[dict] = []

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
        })
        return self.canned


def _make_canned_response() -> dict:
    return {
        "era_background": "中国古代·仙侠",
        "scenes": [
            {
                "name": "山门",
                "description": "巍峨山门，青石台阶延伸至云雾中",
                "lighting": "晨光透过云层，金色光束洒落",
                "style": "中式仙侠宗门建筑",
                "environment_type": "室外山门",
                "time_of_day": "清晨",
                "atmosphere": "肃穆庄严",
                "visual_features": "青石牌坊，云雾缭绕，古松挺立",
                "full_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景展示场景全貌，横向16:9电影级场景设定图。山门｜巍峨山门，青石台阶，云雾缭绕，晨光金色光束洒落，古松挺立，肃穆庄严。",
                "wide_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景广角展示场景全貌，横向16:9电影级场景设定图。山门｜巍峨山门全景，青石台阶从画面底部延伸至云雾中的牌坊，两侧古松挺立，晨光金色光束从左上角洒落，云雾缭绕青山背景。",
                "mid_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，中景展示场景核心区域，横向16:9电影级场景设定图。山门｜青石牌坊正立面中景，匾额清晰可见，石阶纹理精细，古松树根盘踞台阶两侧，晨光斑驳。",
                "close_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，特写展示场景关键细节，横向16:9电影级场景设定图。山门｜青石牌坊匾额特写，石刻纹理清晰可见，青苔斑驳，晨光在石面上形成暖色高光，精细材质质感。",
            },
            {
                "name": "大殿",
                "description": "宽敞华美的大殿，立柱高耸，宝座居中",
                "lighting": "室内烛光为主，光线温暖幽暗",
                "style": "中式古典宫殿",
                "environment_type": "室内大殿",
                "time_of_day": "早晨",
                "atmosphere": "威严华贵",
                "visual_features": "金色宝座，雕龙石柱，红毯铺地，烛台排列",
                "full_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景展示场景全貌，横向16:9电影级场景设定图。大殿｜宽敞华美，金色宝座居中，雕龙石柱高耸，红毯铺地，烛台排列，光线温暖幽暗，威严华贵。",
                "wide_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景广角展示场景全貌，横向16:9电影级场景设定图。大殿｜宽敞华美大殿全景，金色宝座居于画面正中远端，两排雕龙石柱高耸，红毯从画面底部延伸至宝座，烛台沿两侧排列。",
                "mid_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，中景展示场景核心区域，横向16:9电影级场景设定图。大殿｜金色宝座中景，雕龙扶手细节可见，红毯纹理清晰，背景中石柱虚化，烛光在宝座上形成暖色高光。",
                "close_view_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，特写展示场景关键细节，横向16:9电影级场景设定图。大殿｜雕龙石柱龙纹特写，石刻鳞片精细，烛光在浮雕上闪烁，冷暖光影对比，精细材质质感。",
            },
        ],
    }


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    return db, db_path


# ── Tests ──

def test_validate_input_valid():
    agent = SceneDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({
        "chapter_id": 1,
        "raw_text": "text",
        "scenes_list": ["山门"],
    }) is True


def test_validate_input_missing_scenes_list():
    agent = SceneDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1, "raw_text": "text"}) is False


def test_validate_input_empty_scenes_list():
    agent = SceneDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({
        "chapter_id": 1, "raw_text": "text", "scenes_list": [],
    }) is False


def test_execute_success():
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走入山门，进入大殿。")

        # Pre-register scenes in DB (as Screenwriter would)
        db.get_or_create_scene("山门")
        db.get_or_create_scene("大殿")

        agent = SceneDesignerAgent(llm_client=FakeLLM())
        result = agent.execute(
            {
                "chapter_id": chapter_id,
                "raw_text": "叶凡走入山门，进入大殿。",
                "scenes_list": ["山门", "大殿"],
                "script_id": 1,
            },
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["scenes_updated"] == 2
        assert set(result.data["scene_names"]) == {"山门", "大殿"}

        # Verify scene_card rows have been updated
        for name in ["山门", "大殿"]:
            scene_row = db.get_scene_by_name(chapter_id, name)
            assert scene_row is not None, f"scene '{name}' not found"
            assert scene_row["description"] != "", f"scene '{name}' description is empty"
            assert scene_row["lighting"] != "", f"scene '{name}' lighting is empty"
            assert scene_row["style"] != "", f"scene '{name}' style is empty"
            # v0.5: view prompts populated
            assert scene_row["wide_view"] != "", f"scene '{name}' wide_view is empty"
            assert scene_row["mid_view"] != "", f"scene '{name}' mid_view is empty"
            assert scene_row["close_view"] != "", f"scene '{name}' close_view is empty"
            assert scene_row["status"] == "done"

        # Check agent status
        status = db.get_agent_status("scene-designer", chapter_id)
        assert status == "done"
    finally:
        db.close()
        db_path.unlink()


def test_execute_skips_when_already_done():
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        db.get_or_create_scene("山门")

        agent = SceneDesignerAgent(llm_client=FakeLLM())

        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容", "scenes_list": ["山门"]},
            db,
        )
        assert result1.success is True

        # Second run — should skip
        result2 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容", "scenes_list": ["山门"]},
            db,
        )
        assert result2.success is True
        assert result2.data.get("status") == "skipped"
    finally:
        db.close()
        db_path.unlink()
