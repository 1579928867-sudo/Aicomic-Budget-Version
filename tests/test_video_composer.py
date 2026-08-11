"""Tests for Video Composer Agent."""

import shutil
import tempfile
from pathlib import Path

from aicomic.agents.video_composer import VideoComposerAgent
from aicomic.db.repository import Database


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()
    return db, db_path


def _setup_data(db: Database):
    """Create novel, chapter, script, shots, and video_clips. Returns (chapter_id, script_id, clip_dir)."""
    clip_dir = Path(tempfile.mkdtemp(prefix="aicomic_test_clips_"))

    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "测试内容")
    script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})
    shot_ids = db.save_storyboard_shots(script_id, [
        {
            "shot_num": 1, "narration": "旁白一", "dialogue": "角色A: 台词一",
            "camera_movement": "MS", "duration_sec": 3.0,
            "char_ids": [], "scene_id": None,
        },
        {
            "shot_num": 2, "narration": "", "dialogue": "",
            "camera_movement": "CU", "duration_sec": 2.0,
            "char_ids": [], "scene_id": None,
        },
    ])
    # Create actual video clip files + DB rows
    for sid in shot_ids:
        clip_path = clip_dir / f"clip_{sid}.mp4"
        clip_path.touch()
        db.create_video_clip(sid, str(clip_path), 5.0)
    return chapter_id, script_id, clip_dir


# ── Fake video composer that skips actual MoviePy rendering ──

class FakeVideoComposerAgent(VideoComposerAgent):
    """Overrides _compose to skip actual MoviePy rendering in tests."""

    def _compose(self, clip_paths, shots, output_path, chapter_id, db):
        """Simulate composition — create an empty file as placeholder."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("")
        return output_path


# ── Tests ──

def test_validate_input_valid():
    agent = VideoComposerAgent()
    assert agent.validate_input({"chapter_id": 1, "script_id": 1}) is True


def test_validate_input_missing_script_id():
    agent = VideoComposerAgent()
    assert agent.validate_input({"chapter_id": 1}) is False


def test_validate_input_missing_chapter_id():
    agent = VideoComposerAgent()
    assert agent.validate_input({"script_id": 1}) is False


def test_execute_success():
    db, db_path = _make_db()
    clip_dir = None
    try:
        chapter_id, script_id, clip_dir = _setup_data(db)

        agent = FakeVideoComposerAgent()
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["clip_count"] == 2
        assert result.data["final_video_path"] != ""

        # Verify final_video row created
        fv_row = db.conn.execute(
            "SELECT * FROM final_video WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        assert fv_row is not None
        assert fv_row["file_path"] == result.data["final_video_path"]

        # Verify agent status
        assert db.get_agent_status("video-composer", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()
        if clip_dir:
            shutil.rmtree(clip_dir, ignore_errors=True)


def test_execute_reruns_when_called_again():
    """v0.17: video-composer always re-runs - no idempotency skip."""
    db, db_path = _make_db()
    clip_dir = None
    try:
        chapter_id, script_id, clip_dir = _setup_data(db)

        agent = FakeVideoComposerAgent()

        result1 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )
        assert result1.success is True
        assert result1.data.get("clip_count") == 2

        # Second call should also succeed and produce real data
        result2 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )
        assert result2.success is True
        assert result2.data.get("clip_count") == 2
    finally:
        db.close()
        db_path.unlink()
        if clip_dir:
            shutil.rmtree(clip_dir, ignore_errors=True)


def test_execute_no_clips_raises():
    """When no video_clips exist, should fail gracefully."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")
        script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})
        db.save_storyboard_shots(script_id, [
            {"shot_num": 1, "narration": "", "dialogue": "",
             "camera_movement": "MS", "duration_sec": 3.0,
             "char_ids": [], "scene_id": None},
        ])
        # No video_clips created — should fail

        agent = VideoComposerAgent()
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is False
        assert result.error is not None
        assert "No video clips" in result.error or "video clips" in result.error.lower()
    finally:
        db.close()
        db_path.unlink()
