"""Tests for Storyboard Agent (ScreenwriterAgent in v0.10).

v0.10: Agent takes script_id, reads script (with beats) from DB,
and designs merged camera shots. Not to be confused with ScriptwriterAgent
which does novel→script.
"""

import json
import tempfile
from pathlib import Path

from aicomic.interface import AgentResult
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.db.repository import Database


# ── Fake LLM client ──

class FakeLLMClient:
    """Returns a fixed storyboard JSON."""

    def __init__(self, canned_response: dict | None = None):
        self.canned = canned_response or _make_canned_storyboard()
        self.calls: list[dict] = []

    def generate_json(self, system_prompt: str, user_prompt: str,
                      max_tokens: int = 4096) -> dict:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
        })
        return self.canned


def _make_canned_storyboard() -> dict:
    """Canned storyboard output with merged shots."""
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
                        "narration": "张三缓步走入大殿，环顾四周。李四从宝座上站起。",
                        "dialogue": "张三: 终于到了。\n李四: 你来了。",
                        "camera_movement": "LS→MS",
                    },
                    {
                        "shot_num": 2,
                        "shot_type": "dialogue",
                        "duration_sec": 6.0,
                        "characters": [{"name": "张三", "variant": "default"}],
                        "scene_name": "大殿",
                        "narration": "张三抬头望向李四。",
                        "dialogue": "张三: 这里就是传说中的圣地...",
                        "camera_movement": "CU",
                    },
                ],
            }
        ],
        "characters": ["张三", "李四"],
        "scenes_list": ["大殿"],
    }


def _make_canned_script() -> dict:
    """Canned script (ScriptwriterAgent output) for DB seeding."""
    return {
        "era_background": "中国古代·仙侠",
        "scenes": [{
            "scene_name": "大殿",
            "scene_index": 1,
            "atmosphere": "宏伟庄严",
            "scene_sound_cues": ["隐约钟声"],
            "beats": [
                {
                    "beat_num": 1,
                    "characters": ["张三"],
                    "action": "张三缓步走入大殿",
                    "dialogue": [],
                    "expressions": {"张三": "表情肃穆"},
                    "sound_cue": "脚步声回荡",
                },
                {
                    "beat_num": 2,
                    "characters": ["张三", "李四"],
                    "action": "李四从宝座上站起",
                    "dialogue": [
                        {"speaker": "李四", "line": "你来了。", "emotion": "平静"}
                    ],
                    "expressions": {"李四": "面带微笑", "张三": "抬头仰望"},
                    "sound_cue": "衣物摩擦声",
                },
            ],
        }],
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


def _seed_script(db, chapter_id: int) -> int:
    """Create a script row in DB (simulating ScriptwriterAgent output)."""
    return db.save_script(chapter_id, _make_canned_script())


# ── Tests ──

def test_storyboard_validate_input_valid():
    """v0.10: validate_input expects chapter_id + script_id."""
    agent = ScreenwriterAgent(llm_client=FakeLLMClient())
    assert agent.validate_input({"chapter_id": 1, "script_id": 1}) is True


def test_storyboard_validate_input_missing_script_id():
    """Missing script_id should fail validation."""
    agent = ScreenwriterAgent(llm_client=FakeLLMClient())
    assert agent.validate_input({"chapter_id": 1}) is False


def test_storyboard_validate_input_missing_chapter_id():
    """Missing chapter_id should fail validation."""
    agent = ScreenwriterAgent(llm_client=FakeLLMClient())
    assert agent.validate_input({"script_id": 1}) is False


def test_storyboard_execute_success():
    """Full execute: read script from DB, design shots, save storyboard."""
    db, db_path = make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "张三走入大殿，遇见了李四。")
        script_id = _seed_script(db, chapter_id)

        agent = ScreenwriterAgent(llm_client=FakeLLMClient())
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["shots_created"] == 2

        # Verify storyboard shots were saved
        shots = db.get_storyboard_shots(script_id)
        assert len(shots) == 2
        assert shots[0]["shot_num"] == 1
        assert "张三: 终于到了。" in shots[0]["dialogue"]

        # Verify merged shot camera has "→" notation
        assert "→" in shots[0]["camera_movement"]

        # Verify agent status was set
        status = db.get_agent_status("storyboard-agent", chapter_id)
        assert status == "done"
    finally:
        db.close()
        db_path.unlink()


def test_storyboard_execute_skips_when_already_done():
    """Idempotency: second run skips."""
    db, db_path = make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")
        script_id = _seed_script(db, chapter_id)

        agent = ScreenwriterAgent(llm_client=FakeLLMClient())
        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id}, db,
        )
        assert result1.success

        # Second run — should skip
        result2 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id}, db,
        )
        assert result2.success
        assert result2.data.get("status") == "skipped"
    finally:
        db.close()
        db_path.unlink()


def test_storyboard_execute_bad_llm_response():
    """LLM returns invalid JSON — agent should return failure."""
    db, db_path = make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")
        script_id = _seed_script(db, chapter_id)

        # Missing 'scenes_list'
        bad_client = FakeLLMClient(canned_response={
            "scenes": [],
            "characters": ["张三"],
        })
        agent = ScreenwriterAgent(llm_client=bad_client)
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id}, db,
        )

        assert result.success is False
        assert result.error is not None
    finally:
        db.close()
        db_path.unlink()
