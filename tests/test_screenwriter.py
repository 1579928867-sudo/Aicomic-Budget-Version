"""Tests for Screenwriter Agent."""

import json
import tempfile
from pathlib import Path

from aicomic.interface import AgentResult
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.db.repository import Database


# ── Fake ClaudeClient that returns a canned response ──

class FakeClaudeClient:
    """Returns a fixed script JSON instead of calling the real API."""

    def __init__(self, canned_response: dict | None = None):
        self.canned = canned_response or _make_canned_script()
        self.calls: list[dict] = []

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
        })
        return self.canned


def _make_canned_script() -> dict:
    return {
        "scenes": [
            {
                "scene_name": "大殿",
                "scene_index": 1,
                "shots": [
                    {
                        "shot_num": 1,
                        "shot_type": "both",
                        "duration_sec": 8.0,
                        "characters": [
                            {"name": "张三", "variant": "default"},
                            {"name": "李四", "variant": "default"},
                        ],
                        "scene_name": "大殿",
                        "narration": "张三缓步走入大殿。",
                        "dialogue": "张三: 终于到了。",
                        "camera_movement": "slow_push_in",
                    },
                    {
                        "shot_num": 2,
                        "shot_type": "dialogue",
                        "duration_sec": 6.0,
                        "characters": [{"name": "张三", "variant": "default"}],
                        "scene_name": "大殿",
                        "narration": "",
                        "dialogue": "张三: 这里就是传说中的圣地...",
                        "camera_movement": "static",
                    },
                ],
            }
        ],
        "characters": ["张三", "李四"],
        "scenes_list": ["大殿"],
    }


# ── Fixtures ──

def make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    return db, db_path


# ── Tests ──

def test_screenwriter_validate_input_valid():
    agent = ScreenwriterAgent(llm_client=FakeClaudeClient())
    assert agent.validate_input({"chapter_id": 1, "raw_text": "some text"}) is True


def test_screenwriter_validate_input_missing_chapter_id():
    agent = ScreenwriterAgent(llm_client=FakeClaudeClient())
    assert agent.validate_input({"raw_text": "text"}) is False


def test_screenwriter_validate_input_missing_raw_text():
    agent = ScreenwriterAgent(llm_client=FakeClaudeClient())
    assert agent.validate_input({"chapter_id": 1}) is False


def test_screenwriter_execute_success():
    db, db_path = make_db()
    try:
        novel_id = db.create_novel("测试小说", "")
        chapter_id = db.create_chapter(novel_id, 1, "张三走入大殿，遇见了李四。")

        agent = ScreenwriterAgent(llm_client=FakeClaudeClient())
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "张三走入大殿，遇见了李四。"},
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["script_id"] == 1
        assert set(result.data["characters"]) == {"张三", "李四"}
        assert result.data["scenes_list"] == ["大殿"]

        # Verify script was saved to DB
        rows = db.conn.execute("SELECT * FROM script WHERE chapter_id = ?", (chapter_id,)).fetchall()
        assert len(rows) == 1
        saved_json = json.loads(rows[0]["raw_json"])
        assert len(saved_json["scenes"]) == 1

        # Verify storyboard shots were saved
        shots = db.get_storyboard_shots(1)
        assert len(shots) == 2
        assert shots[0]["shot_num"] == 1
        assert shots[0]["dialogue"] == "张三: 终于到了。"

        # Verify characters were registered
        char_rows = db.conn.execute("SELECT * FROM character_card").fetchall()
        char_names = {r["name"] for r in char_rows}
        assert "张三" in char_names
        assert "李四" in char_names

        # Verify scenes were registered
        scene_rows = db.conn.execute("SELECT * FROM scene_card").fetchall()
        scene_names = {r["name"] for r in scene_rows}
        assert "大殿" in scene_names

        # Verify agent status was set
        status = db.get_agent_status("screenwriter", chapter_id)
        assert status == "done"
    finally:
        db.close()
        db_path.unlink()


def test_screenwriter_execute_claude_returns_bad_json():
    """When Claude returns unparseable text, the agent should catch it."""
    db, db_path = make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        bad_client = FakeClaudeClient(canned_response={"scenes": []})  # missing 'characters' and 'scenes_list'
        agent = ScreenwriterAgent(llm_client=bad_client)
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"},
            db,
        )

        assert result.success is False
        assert result.error is not None
    finally:
        db.close()
        db_path.unlink()
