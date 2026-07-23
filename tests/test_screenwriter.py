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
    """Canned storyboard output — v0.13 industry format with time segments."""
    return {
        "scenes": [
            {
                "scene_name": "大殿",
                "scene_index": 1,
                "shots": [
                    {
                        "shot_num": 1,
                        "shot_type": "both",
                        "duration_sec": 10.0,
                        "characters": [
                            {"name": "张三", "variant": "default"},
                            {"name": "李四", "variant": "default"},
                        ],
                        "scene_name": "大殿",
                        "segments": [
                            {
                                "time_range": "0-3秒",
                                "camera": "全景",
                                "action": "张三缓步走入大殿，环顾四周。",
                                "dialogue": "张三（感慨，音色：清朗少年）: 终于到了。",
                                "sound": "脚步声回荡",
                                "transition": None,
                            },
                            {
                                "time_range": "3-7秒",
                                "camera": "中景",
                                "action": "李四从宝座上站起，面带微笑。",
                                "dialogue": "李四（平静，音色：威严老者）: 你来了。",
                                "sound": "衣物摩擦声",
                                "transition": "延续中景，李四起身面向张三",
                            },
                            {
                                "time_range": "7-10秒",
                                "camera": "近景",
                                "action": "张三抬头望向李四，眼神坚定。",
                                "dialogue": None,
                                "sound": "静谧中的呼吸声",
                                "transition": "衔接镜头2的0-3秒：张三立于殿中，抬头望向宝座上的李四",
                            },
                        ],
                        "scene_summary": "场景：仙侠大殿，宏伟庄严，光线幽暗。（视频不要添加字幕）",
                    },
                    {
                        "shot_num": 2,
                        "shot_type": "dialogue",
                        "duration_sec": 8.0,
                        "characters": [{"name": "张三", "variant": "default"}],
                        "scene_name": "大殿",
                        "segments": [
                            {
                                "time_range": "0-3秒",
                                "camera": "近景",
                                "action": "张三立于殿中，抬头望向宝座上的李四，眼神坚定。",
                                "dialogue": "张三（深沉，音色：清朗少年）: 这里就是传说中的圣地...",
                                "sound": "静谧中的呼吸声",
                                "transition": None,
                            },
                            {
                                "time_range": "3-7秒",
                                "camera": "中景",
                                "action": "张三向前迈出一步，双手抱拳行礼。",
                                "dialogue": None,
                                "sound": "脚步声，衣物摩擦声",
                                "transition": "延续中景，张三抱拳行礼",
                            },
                            {
                                "time_range": "7-10秒",
                                "camera": "全景",
                                "action": "大殿全景，张三站在殿中，李四端坐宝座之上，气氛庄严。",
                                "dialogue": None,
                                "sound": "钟声回荡",
                                "transition": None,
                            },
                        ],
                        "scene_summary": "场景：仙侠大殿，宏伟庄严，光线幽暗。（视频不要添加字幕）",
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
    db.migrate_schema()
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
        assert len(shots[0]["dialogue"]) > 0  # dialogue derived from segments

        # Verify v0.13+ segments are stored
        import json
        segs1 = json.loads(shots[0].get("segments_json", "[]"))
        assert len(segs1) == 3
        assert segs1[0]["time_range"] == "0-3秒"

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
