"""Tests for Video Generator Agent."""

import tempfile
from pathlib import Path

from aicomic.agents.video_generator import VideoGeneratorAgent
from aicomic.db.repository import Database
from aicomic.doubao.client import MockVideoGenerator


# ── Fake LLM for video prompt optimization ──

class FakeLLM:
    """Returns canned video prompt optimization."""

    def __init__(self, canned_response: dict | None = None):
        self.canned = canned_response or {
            "shots": [
                {"shot_num": 1, "video_prompt": "优化后的视频提示词1"},
                {"shot_num": 2, "video_prompt": "优化后的视频提示词2"},
            ],
        }
        self.calls: list[dict] = []

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        self.calls.append({"system_prompt": system_prompt, "user_prompt": user_prompt, "max_tokens": max_tokens})
        return self.canned


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()
    return db, db_path


def _setup_shots(db: Database) -> tuple[int, int, int]:
    """Create a novel, chapter, script, and 2 storyboard shots. Returns (chapter_id, script_id, [shot_ids])."""
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")
    script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})
    shot_ids = db.save_storyboard_shots(script_id, [
        {
            "shot_num": 1, "narration": "测试镜头1", "dialogue": "",
            "camera_movement": "CU", "duration_sec": 5.0,
            "char_ids": [], "scene_id": None,
        },
        {
            "shot_num": 2, "narration": "测试镜头2", "dialogue": "角色: 你好",
            "camera_movement": "MS", "duration_sec": 3.0,
            "char_ids": [], "scene_id": None,
        },
    ])
    # Set image_prompts on shots
    for sid in shot_ids:
        db.update_shot_image_prompt(sid, f"静态画面提示词 shot {sid}")
    return chapter_id, script_id


# ── Tests ──

def test_validate_input_valid():
    agent = VideoGeneratorAgent(
        llm_client=FakeLLM(),
        video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
    )
    assert agent.validate_input({"chapter_id": 1, "script_id": 1}) is True


def test_validate_input_missing_script_id():
    agent = VideoGeneratorAgent(
        llm_client=FakeLLM(),
        video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
    )
    assert agent.validate_input({"chapter_id": 1}) is False


def test_validate_input_missing_chapter_id():
    agent = VideoGeneratorAgent(
        llm_client=FakeLLM(),
        video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
    )
    assert agent.validate_input({"script_id": 1}) is False


def test_execute_success():
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_shots(db)

        agent = VideoGeneratorAgent(
            llm_client=FakeLLM(),
            video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
        )
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["clips_created"] == 2
        assert result.data["total_shots"] == 2

        # Verify video_clip rows exist
        clips = db.get_video_clips(script_id)
        assert len(clips) == 2
        for c in clips:
            assert c["file_path"] != ""
            assert c["status"] == "done"

        # Check agent status
        assert db.get_agent_status("video-generator", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_execute_skips_when_already_done():
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_shots(db)

        agent = VideoGeneratorAgent(
            llm_client=FakeLLM(),
            video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
        )

        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )
        assert result1.success is True
        assert result1.data["clips_created"] == 2

        # Second run — should skip because agent status is "done"
        result2 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )
        assert result2.success is True
        assert result2.data.get("status") == "skipped"
    finally:
        db.close()
        db_path.unlink()


def test_execute_respects_existing_clips():
    """If some shots already have video_clips, only generate missing ones."""
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_shots(db)

        # Pre-create a video_clip for shot 1
        shots = db.get_storyboard_shots(script_id)
        db.create_video_clip(shots[0]["id"], "existing.mp4", 5.0)

        agent = VideoGeneratorAgent(
            llm_client=FakeLLM({"shots": [{"shot_num": 2, "video_prompt": "新视频提示词"}]}),
            video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
        )
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        # Only 1 new clip created (shot 2), shot 1 already has a clip
        assert result.data["clips_created"] == 1
    finally:
        db.close()
        db_path.unlink()
