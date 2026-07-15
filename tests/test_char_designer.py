"""Tests for Character Designer Agent."""

import json
import tempfile
from pathlib import Path

from aicomic.agents.char_designer import CharacterDesignerAgent
from aicomic.db.repository import Database


# ── Fake LLM ──

class FakeLLM:
    """Returns a canned character design JSON."""

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
        "characters": [
            {
                "name": "叶凡",
                "aliases": [],
                "gender": "男",
                "age": 18,
                "height_cm": 178,
                "is_human": True,
                "variants": [
                    {
                        "variant_name": "default",
                        "hair": "黑色长发束髻",
                        "head_accessories": "白玉发冠",
                        "makeup": "剑眉星目，清秀面容",
                        "face": "清秀俊朗，肤色白净",
                        "aura": "气质坚毅",
                        "upper_body": "白色交领长袍，云纹刺绣",
                        "lower_body": "同色系长衫，墨玉腰带",
                        "footwear": "黑色云纹布靴",
                        "accessories": "左手天毒珠印记",
                        "full_prompt": "古代仙侠风格，【中国古代·仙侠】叶凡，男 18岁，身高178cm，九头身比例，写实电影感风格，正面，站立的全身图片，图片人物背景为纯白色。黑色长发束髻，白玉发冠束发；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅；上身白色交领长袍，云纹刺绣；下身同色系长衫，墨玉腰带；脚上黑色云纹布靴；配饰左手天毒珠印记；双手自然下垂，手里无任何物品。",
                        "front_view_prompt": "古代仙侠风格，【中国古代·仙侠】叶凡，男 18岁，身高178cm，九头身比例，写实电影感风格，正面特写全身站立图片，人物居中，图片背景为纯白色。黑色长发束髻，白玉发冠束发；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅；上身白色交领长袍，云纹刺绣；下身同色系长衫，墨玉腰带；脚上黑色云纹布靴；配饰左手天毒珠印记；双手自然下垂。",
                        "side_view_prompt": "古代仙侠风格，【中国古代·仙侠】叶凡，男 18岁，身高178cm，九头身比例，写实电影感风格，侧面全身站立图片，展示身体侧轮廓和服装侧面细节，图片背景为纯白色。黑色长发束髻侧面，白玉发冠侧影；上身白色交领长袍侧面云纹刺绣；下身同色系长衫侧面，墨玉腰带；脚上黑色云纹布靴侧面；双手自然下垂。",
                        "back_view_prompt": "古代仙侠风格，【中国古代·仙侠】叶凡，男 18岁，身高178cm，九头身比例，写实电影感风格，背面全身站立图片，展示背面发型和服装背面设计，图片背景为纯白色。黑色长发束髻背面，白玉发冠背面；上身白色交领长袍背面云纹刺绣；下身同色系长衫背面，墨玉腰带；脚上黑色云纹布靴背面；双手自然下垂。",
                    }
                ],
            },
            {
                "name": "长老",
                "aliases": [],
                "gender": "男",
                "age": 60,
                "height_cm": 170,
                "is_human": True,
                "variants": [
                    {
                        "variant_name": "default",
                        "hair": "白色长发束髻",
                        "head_accessories": "木质道冠",
                        "makeup": "白眉长须，仙风道骨",
                        "face": "面容清瘦，皱纹深刻",
                        "aura": "气质威严深邃",
                        "upper_body": "灰色宽袖道袍，八卦纹样",
                        "lower_body": "同色系长裤",
                        "footwear": "黑色布鞋",
                        "accessories": "手持拂尘",
                        "full_prompt": "古代仙侠风格，【中国古代·仙侠】长老，男 60岁，身高170cm，九头身比例，写实电影感风格，正面，站立的全身图片，图片人物背景为纯白色。白色长发束髻，木质道冠束发；白眉长须，仙风道骨，面容清瘦，皱纹深刻，气质威严深邃；上身灰色宽袖道袍，八卦纹样；下身同色系长裤；脚上黑色布鞋；配饰手持拂尘；双手自然下垂，手里无任何物品。",
                        "front_view_prompt": "古代仙侠风格，【中国古代·仙侠】长老，男 60岁，身高170cm，写实电影感风格，正面特写全身站立，纯白背景。白色长发束髻，木质道冠束发；白眉长须，仙风道骨；灰色宽袖道袍；手持拂尘。",
                        "side_view_prompt": "古代仙侠风格，【中国古代·仙侠】长老，男 60岁，身高170cm，写实电影感风格，侧面全身站立，展示道袍侧轮廓，纯白背景。白色长发束髻侧面，木质道冠侧影；灰色宽袖道袍侧面；手持拂尘侧面。",
                        "back_view_prompt": "古代仙侠风格，【中国古代·仙侠】长老，男 60岁，身高170cm，写实电影感风格，背面全身站立，展示道袍背面设计，纯白背景。白色长发束髻背面，木质道冠背面；灰色宽袖道袍背面。",
                    }
                ],
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
    agent = CharacterDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({
        "chapter_id": 1,
        "raw_text": "text",
        "characters": ["叶凡"],
    }) is True


def test_validate_input_missing_characters():
    agent = CharacterDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1, "raw_text": "text"}) is False


def test_validate_input_empty_characters():
    agent = CharacterDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({
        "chapter_id": 1, "raw_text": "text", "characters": [],
    }) is False


def test_validate_input_missing_chapter_id():
    agent = CharacterDesignerAgent(llm_client=FakeLLM())
    assert agent.validate_input({"raw_text": "text", "characters": ["叶凡"]}) is False


def test_execute_success():
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前。")

        # Pre-register characters in DB (as Screenwriter would)
        db.get_or_create_character("叶凡")
        db.get_or_create_character("长老")

        agent = CharacterDesignerAgent(llm_client=FakeLLM())
        result = agent.execute(
            {
                "chapter_id": chapter_id,
                "raw_text": "叶凡走到山门前。",
                "characters": ["叶凡", "长老"],
                "character_variants": {},
            },
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["variants_created"] == 2
        assert set(result.data["character_names"]) == {"叶凡", "长老"}

        # Verify appearance_variant rows exist
        variants = db.conn.execute(
            "SELECT * FROM appearance_variant ORDER BY id"
        ).fetchall()
        assert len(variants) == 2

        # Verify character.default_look_id is set
        for v in variants:
            vd = dict(v)
            assert vd["status"] == "done"
            assert vd["variant_name"] == "default"
            appearance = json.loads(vd["appearance_json"])
            assert "full_prompt" in appearance
            assert "古代仙侠风格" in appearance["full_prompt"]
            # v0.5: view prompts present
            assert "front_view_prompt" in appearance, f"front_view_prompt missing for {vd['variant_name']}"
            assert "side_view_prompt" in appearance, f"side_view_prompt missing for {vd['variant_name']}"
            assert "back_view_prompt" in appearance, f"back_view_prompt missing for {vd['variant_name']}"
            assert appearance["front_view_prompt"] != ""
            assert appearance["side_view_prompt"] != ""
            assert appearance["back_view_prompt"] != ""

            # v0.5: verify DB view columns populated
            assert vd["front_view"] != "", f"front_view is empty for variant {vd['id']}"
            assert vd["side_view"] != "", f"side_view is empty for variant {vd['id']}"
            assert vd["back_view"] != "", f"back_view is empty for variant {vd['id']}"

        # Check character default_look_id
        char_rows = db.conn.execute(
            "SELECT * FROM character_card ORDER BY id"
        ).fetchall()
        for c in char_rows:
            cd = dict(c)
            assert cd["default_look_id"] is not None, f"default_look_id is NULL for {cd['name']}"

        # Check agent status
        status = db.get_agent_status("char-designer", chapter_id)
        assert status == "done"
    finally:
        db.close()
        db_path.unlink()


def test_execute_skips_when_already_done():
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        db.get_or_create_character("叶凡")

        agent = CharacterDesignerAgent(llm_client=FakeLLM())

        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容", "characters": ["叶凡"]},
            db,
        )
        assert result1.success is True

        # Second run — should skip
        result2 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容", "characters": ["叶凡"]},
            db,
        )
        assert result2.success is True
        assert result2.data.get("status") == "skipped"
    finally:
        db.close()
        db_path.unlink()
