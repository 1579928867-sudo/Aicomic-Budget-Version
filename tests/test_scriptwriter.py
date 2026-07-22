"""Tests for Scriptwriter Agent (novel → structured drama script).

v0.10: ScriptwriterAgent converts raw novel text into a structured script
with beats, dialogue, expressions, and sound cues. This is the first step
of the new pipeline, before the StoryboardAgent.
"""

import tempfile
from pathlib import Path

import pytest

from aicomic.agents.scriptwriter import ScriptwriterAgent
from aicomic.db.repository import Database


# ── Fake LLM client ──

class FakeLLM:
    """Returns a canned script JSON."""

    def __init__(self, canned_response: dict | None = None):
        self.canned = canned_response or _make_canned_script()
        self.calls: list[dict] = []

    def generate_json(self, system_prompt: str, user_prompt: str,
                      max_tokens: int = 4096) -> dict:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
        })
        return self.canned


class FailingLLM:
    """LLM that always raises."""

    def generate_json(self, system_prompt: str, user_prompt: str,
                      max_tokens: int = 4096) -> dict:
        raise RuntimeError("LLM API error")


def _make_canned_script() -> dict:
    """Canned script output matching ScriptwriterAgent's expected format."""
    return {
        "era_background": "中国古代·仙侠",
        "scenes": [
            {
                "scene_name": "婚房",
                "scene_index": 1,
                "atmosphere": "清晨暖光透过雕花窗棂洒入，红色帷帐飘动",
                "scene_sound_cues": ["远处隐约鸟鸣", "帷帐飘动的沙沙声"],
                "beats": [
                    {
                        "beat_num": 1,
                        "characters": ["萧澈"],
                        "action": "萧澈缓缓睁开眼睛，眼神茫然",
                        "dialogue": [
                            {
                                "speaker": "萧澈（内心）",
                                "line": "这...这是哪里？",
                                "emotion": "困惑、震惊",
                            }
                        ],
                        "expressions": {"萧澈": "眼神迷茫，眉头微蹙"},
                        "sound_cue": "床铺轻微吱呀声",
                    },
                    {
                        "beat_num": 2,
                        "characters": ["萧澈"],
                        "action": "萧澈快速坐起身",
                        "dialogue": [],
                        "expressions": {"萧澈": "神色警觉，动作迅捷"},
                        "sound_cue": "被褥翻动声",
                    },
                    {
                        "beat_num": 3,
                        "characters": ["萧澈", "小姑妈"],
                        "action": "小姑妈推门而入",
                        "dialogue": [
                            {
                                "speaker": "小姑妈",
                                "line": "萧澈！你终于醒了！",
                                "emotion": "欣喜若狂",
                            }
                        ],
                        "expressions": {
                            "萧澈": "转头看向门口，表情惊讶",
                            "小姑妈": "眼眶微红，嘴角上扬",
                        },
                        "sound_cue": "木门推开声，急促脚步声",
                    },
                ],
            }
        ],
        "characters": ["萧澈", "小姑妈"],
        "scenes_list": ["婚房"],
    }


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    return db, db_path


# ── validate_input tests ──

def test_validate_input_valid():
    """Valid input: chapter_id (int) + raw_text (non-empty str)."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1, "raw_text": "萧澈睁开了眼睛。"}) is True


def test_validate_input_missing_chapter_id():
    """Missing chapter_id should fail."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"raw_text": "text"}) is False


def test_validate_input_chapter_id_not_int():
    """chapter_id must be an int."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": "1", "raw_text": "text"}) is False


def test_validate_input_missing_raw_text():
    """Missing raw_text should fail."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1}) is False


def test_validate_input_empty_raw_text():
    """Empty raw_text should fail."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1, "raw_text": ""}) is False


def test_validate_input_raw_text_not_string():
    """raw_text must be a string."""
    agent = ScriptwriterAgent(llm_client=FakeLLM())
    assert agent.validate_input({"chapter_id": 1, "raw_text": 123}) is False


# ── execute tests ──

def test_execute_success():
    """Full execute: LLM returns valid script, saved to DB, status set."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试小说", "")
        chapter_id = db.create_chapter(
            novel_id, 1,
            "萧澈缓缓睁开眼睛，发现自己躺在陌生的婚床上。"
            "小姑妈推门而入，喊道：'萧澈！你终于醒了！'"
        )

        agent = ScriptwriterAgent(llm_client=FakeLLM())
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "萧澈睁开了眼睛。"},
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert isinstance(result.data["script_id"], int)
        assert "萧澈" in result.data["characters"]
        assert "小姑妈" in result.data["characters"]
        assert "婚房" in result.data["scenes_list"]
        assert result.data["beat_count"] == 3

        # Verify script JSON was saved correctly
        script_id = result.data["script_id"]
        row = db.conn.execute(
            "SELECT raw_json FROM script WHERE id = ?", (script_id,)
        ).fetchone()
        assert row is not None
        import json
        script_data = json.loads(row["raw_json"])
        assert len(script_data["scenes"]) == 1
        assert len(script_data["scenes"][0]["beats"]) == 3

        # Verify agent status
        status = db.get_agent_status("scriptwriter", chapter_id)
        assert status == "done"
    finally:
        db.close()
        db_path.unlink()


def test_execute_skips_when_already_done():
    """Idempotency: second run returns skipped status."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        agent = ScriptwriterAgent(llm_client=FakeLLM())

        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )
        assert result1.success is True
        assert result1.data.get("status") != "skipped"

        # Second run — should skip
        result2 = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )
        assert result2.success is True
        assert result2.data.get("status") == "skipped"
    finally:
        db.close()
        db_path.unlink()


def test_execute_llm_raises_exception():
    """LLM throws — agent returns failure and sets failed status."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        agent = ScriptwriterAgent(llm_client=FailingLLM())
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )

        assert result.success is False
        assert "LLM API error" in result.error

        status = db.get_agent_status("scriptwriter", chapter_id)
        assert status == "failed"
    finally:
        db.close()
        db_path.unlink()


def test_execute_bad_llm_json_missing_scenes():
    """LLM returns JSON missing 'scenes' → failure."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        bad_llm = FakeLLM(canned_response={
            "characters": ["张三"],
            "scenes_list": ["大殿"],
            # missing 'scenes'
        })
        agent = ScriptwriterAgent(llm_client=bad_llm)
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )

        assert result.success is False
        assert result.error is not None
        assert "scenes" in result.error.lower()
    finally:
        db.close()
        db_path.unlink()


def test_execute_bad_llm_json_missing_characters():
    """LLM returns JSON missing 'characters' → failure."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        bad_llm = FakeLLM(canned_response={
            "scenes": [{"scene_name": "x", "scene_index": 1, "beats": []}],
            "scenes_list": ["x"],
            # missing 'characters'
        })
        agent = ScriptwriterAgent(llm_client=bad_llm)
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )

        assert result.success is False
        assert "characters" in result.error.lower()
    finally:
        db.close()
        db_path.unlink()


def test_execute_bad_llm_json_empty_scenes():
    """LLM returns JSON with empty scenes list → failure."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        bad_llm = FakeLLM(canned_response={
            "scenes": [],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })
        agent = ScriptwriterAgent(llm_client=bad_llm)
        result = agent.execute(
            {"chapter_id": chapter_id, "raw_text": "内容"}, db,
        )

        assert result.success is False
    finally:
        db.close()
        db_path.unlink()


# ── _validate_script static method tests ──

def test_validate_script_valid():
    """A well-formed script should pass validation without raising."""
    script = _make_canned_script()
    # Should not raise
    ScriptwriterAgent._validate_script(script)


def test_validate_script_not_dict():
    """Non-dict input should raise ValueError."""
    with pytest.raises(ValueError, match="must be a dict"):
        ScriptwriterAgent._validate_script("not a dict")


def test_validate_script_missing_scenes():
    """Script missing 'scenes' field should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*scenes"):
        ScriptwriterAgent._validate_script({
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_missing_characters():
    """Script missing 'characters' field should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*characters"):
        ScriptwriterAgent._validate_script({
            "scenes": [{"scene_name": "x", "scene_index": 1, "beats": []}],
            "scenes_list": ["x"],
        })


def test_validate_script_missing_scenes_list():
    """Script missing 'scenes_list' field should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*scenes_list"):
        ScriptwriterAgent._validate_script({
            "scenes": [{"scene_name": "x", "scene_index": 1, "beats": []}],
            "characters": ["张三"],
        })


def test_validate_script_empty_characters():
    """Empty characters list should raise ValueError."""
    with pytest.raises(ValueError, match="characters.*non-empty"):
        ScriptwriterAgent._validate_script({
            "scenes": [{"scene_name": "x", "scene_index": 1, "beats": []}],
            "characters": [],
            "scenes_list": ["x"],
        })


def test_validate_script_scene_missing_beats():
    """Scene missing 'beats' should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*beats"):
        ScriptwriterAgent._validate_script({
            "scenes": [{"scene_name": "大殿", "scene_index": 1}],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_beat_missing_beat_num():
    """Beat missing beat_num should raise ValueError."""
    with pytest.raises(ValueError, match="missing beat_num"):
        ScriptwriterAgent._validate_script({
            "scenes": [{
                "scene_name": "大殿", "scene_index": 1,
                "beats": [{"action": "test", "sound_cue": "...", "expressions": {}}],
            }],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_duplicate_beat_num():
    """Duplicate beat_num across beats should raise ValueError."""
    with pytest.raises(ValueError, match="Duplicate beat_num"):
        ScriptwriterAgent._validate_script({
            "scenes": [{
                "scene_name": "大殿", "scene_index": 1,
                "beats": [
                    {"beat_num": 1, "action": "a", "sound_cue": "s", "expressions": {}},
                    {"beat_num": 1, "action": "b", "sound_cue": "s", "expressions": {}},
                ],
            }],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_beat_missing_action():
    """Beat missing 'action' should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*action"):
        ScriptwriterAgent._validate_script({
            "scenes": [{
                "scene_name": "大殿", "scene_index": 1,
                "beats": [
                    {"beat_num": 1, "action": "", "sound_cue": "s", "expressions": {}},
                ],
            }],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_beat_missing_sound_cue():
    """Beat missing 'sound_cue' key should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*sound_cue"):
        ScriptwriterAgent._validate_script({
            "scenes": [{
                "scene_name": "大殿", "scene_index": 1,
                "beats": [
                    {"beat_num": 1, "action": "test", "expressions": {}},
                ],
            }],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })


def test_validate_script_beat_missing_expressions():
    """Beat missing 'expressions' key should raise ValueError."""
    with pytest.raises(ValueError, match="missing.*expressions"):
        ScriptwriterAgent._validate_script({
            "scenes": [{
                "scene_name": "大殿", "scene_index": 1,
                "beats": [
                    {"beat_num": 1, "action": "test", "sound_cue": "安静"},
                ],
            }],
            "characters": ["张三"],
            "scenes_list": ["大殿"],
        })
