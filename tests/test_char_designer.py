"""Tests for Character Designer Agent."""

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
                "is_human": True,
                "design_prompt": "【中国古代·仙侠】叶凡，男 18岁，8k 类 3D 游戏 cg 电影风格，包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称，带一些人物简介。画面从左到右排列三个视角。黑色长发束髻，白玉发冠；剑眉星目清秀面容；白色交领长袍云纹刺绣；墨玉腰带；黑色云纹布靴；左手天毒珠印记；双手自然下垂。",
            },
            {
                "name": "长老",
                "aliases": [],
                "gender": "男",
                "age": 60,
                "is_human": True,
                "design_prompt": "【中国古代·仙侠】长老，男 60岁，8k 类 3D 游戏 cg 电影风格，包括左侧人物全身设计图含衣着细节，右侧画面三视图，同时左侧上方为人物名称。画面从左到右排列三个视角。白色长发束髻木质道冠；白眉长须面容清瘦；灰色宽袖道袍八卦纹样；手持拂尘。",
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
    db.migrate_schema()
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
            },
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["outfits_created"] == 2
        assert set(result.data["character_names"]) == {"叶凡", "长老"}

        # Verify character_outfit rows exist (not appearance_variant)
        outfits = db.conn.execute(
            "SELECT * FROM character_outfit ORDER BY id"
        ).fetchall()
        assert len(outfits) == 2

        for o in outfits:
            od = dict(o)
            assert od["tag"] == "默认"
            assert od["is_default"] == 1
            assert "古代仙侠" in od["prompt"] or "中国古代" in od["prompt"]

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
