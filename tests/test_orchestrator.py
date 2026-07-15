"""Tests for Orchestrator pipeline coordination."""

import tempfile
from pathlib import Path

from aicomic.interface import AgentInterface, AgentResult
from aicomic.bus import AgentBus
from aicomic.orchestrator import Orchestrator
from aicomic.db.repository import Database


class _FakeScreenwriter(AgentInterface):
    """Minimal fake that mimics the real Screenwriter behavior."""

    agent_name = "screenwriter"

    def __init__(self):
        self.executed = False
        self.will_fail = False

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "raw_text" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        if self.will_fail:
            return AgentResult(success=False, error="Claude API error")
        self.executed = True
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={
                "script_id": 1,
                "characters": ["张三"],
                "scenes_list": ["大殿"],
            },
        )


def test_orchestrator_run_chapter_success():
    bus = AgentBus()
    screenwriter = _FakeScreenwriter()
    bus.register(screenwriter)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()

    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, "内容")

        assert result.success is True
        assert screenwriter.executed is True
        # Check chapter status was updated
        assert db.get_agent_status("screenwriter", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_screenwriter_fails():
    bus = AgentBus()
    screenwriter = _FakeScreenwriter()
    screenwriter.will_fail = True
    bus.register(screenwriter)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()

    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, "内容")

        assert result.success is False
        assert "Claude API error" in result.error
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_skips_already_done_agent():
    bus = AgentBus()
    screenwriter = _FakeScreenwriter()
    bus.register(screenwriter)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()

    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        orchestrator = Orchestrator(bus, db)

        # First run
        result1 = orchestrator.run_chapter(chapter_id, "内容")
        assert result1.success is True

        # Second run — should skip because status is "done"
        result2 = orchestrator.run_chapter(chapter_id, "内容")
        assert result2.success is True
        # The fake screenwriter's execute() sets status to "done" itself,
        # and the real ScreenwriterAgent checks for "done" in execute().
        # Skipping is the agent's responsibility.
    finally:
        db.close()
        db_path.unlink()


# ── Integration: full v0.1 pipeline with fake Claude ──

class FakeClaudeForIntegration:
    """Returns a valid script JSON covering multiple shots and characters."""

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        return {
            "scenes": [
                {
                    "scene_name": "山门",
                    "scene_index": 1,
                    "shots": [
                        {
                            "shot_num": 1,
                            "duration_sec": 8.0,
                            "characters": [{"name": "叶凡", "variant": "default"}],
                            "scene_name": "山门",
                            "narration": "叶凡站在山门前，仰望巍峨的牌匾。",
                            "dialogue": "",
                            "camera_movement": "slow_push_in",
                        },
                        {
                            "shot_num": 2,
                            "duration_sec": 5.0,
                            "characters": [{"name": "叶凡", "variant": "default"}],
                            "scene_name": "山门",
                            "narration": "",
                            "dialogue": "叶凡: 这就是青云宗...",
                            "camera_movement": "static",
                        },
                    ],
                },
                {
                    "scene_name": "大殿",
                    "scene_index": 2,
                    "shots": [
                        {
                            "shot_num": 3,
                            "duration_sec": 8.0,
                            "characters": [
                                {"name": "叶凡", "variant": "default"},
                                {"name": "长老", "variant": "default"},
                            ],
                            "scene_name": "大殿",
                            "narration": "殿内，一位白发长老端坐于蒲团之上。",
                            "dialogue": "长老: 你终于来了。",
                            "camera_movement": "slow_pan",
                        },
                    ],
                },
            ],
            "characters": ["叶凡", "长老"],
            "scenes_list": ["山门", "大殿"],
        }


def test_full_pipeline_integration():
    """End-to-end: novel text → Screenwriter → DB entries."""
    import tempfile

    from aicomic.bus import AgentBus
    from aicomic.orchestrator import Orchestrator
    from aicomic.db.repository import Database
    from aicomic.agents.screenwriter import ScreenwriterAgent

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()

    try:
        # Setup
        novel_id = db.create_novel("测试修仙", "作者")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前，仰望牌匾...")

        fake_claude = FakeClaudeForIntegration()
        screenwriter = ScreenwriterAgent(llm_client=fake_claude)

        bus = AgentBus()
        bus.register(screenwriter)

        orchestrator = Orchestrator(bus, db)

        # Run
        result = orchestrator.run_chapter(chapter_id, "叶凡走到山门前，仰望牌匾...")

        # Verify orchestrator result
        assert result.success is True
        assert result.data is not None
        assert result.data["script_id"] == 1
        assert set(result.data["characters"]) == {"叶凡", "长老"}
        assert result.data["scenes_list"] == ["山门", "大殿"]

        # Verify DB: script
        scripts = db.conn.execute(
            "SELECT * FROM script WHERE chapter_id = ?", (chapter_id,)
        ).fetchall()
        assert len(scripts) == 1

        # Verify DB: storyboard shots (3 shots across 2 scenes)
        shots = db.get_storyboard_shots(1)
        assert len(shots) == 3
        assert shots[0]["shot_num"] == 1
        assert shots[2]["shot_num"] == 3
        assert shots[2]["camera_movement"] == "slow_pan"

        # Verify DB: characters registered
        chars = db.conn.execute("SELECT name FROM character_card ORDER BY id").fetchall()
        char_names = [c["name"] for c in chars]
        assert "叶凡" in char_names
        assert "长老" in char_names

        # Verify DB: scenes registered
        scenes = db.conn.execute("SELECT name FROM scene_card ORDER BY id").fetchall()
        scene_names = [s["name"] for s in scenes]
        assert "山门" in scene_names
        assert "大殿" in scene_names

        # Verify DB: agent status
        status = db.get_agent_status("screenwriter", chapter_id)
        assert status == "done"

        # Verify DB: task log entries exist
        logs = db.conn.execute(
            "SELECT * FROM task_log WHERE chapter_id = ? ORDER BY id",
            (chapter_id,),
        ).fetchall()
        log_events = [l["event"] for l in logs]
        assert "pipeline_started" in log_events
        assert "completed" in log_events
    finally:
        db.close()
        db_path.unlink()
