"""Tests for Database layer."""

import tempfile
from pathlib import Path

import pytest

from aicomic.db.repository import Database


@pytest.fixture
def db():
    """Create a temporary database for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    database = Database(db_path)
    database.connect()
    database.init_schema()
    yield database
    database.close()
    db_path.unlink()


def test_database_connect_and_init(db):
    """Verify database connects and creates all tables."""
    tables = db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = [t["name"] for t in tables]
    expected = [
        "appearance_variant",
        "chapter",
        "character_card",
        "final_video",
        "novel",
        "scene_card",
        "script",
        "storyboard_shot",
        "task_log",
        "video_clip",
    ]
    for t in expected:
        assert t in table_names, f"Table '{t}' missing from schema"


def test_create_and_get_novel(db):
    novel_id = db.create_novel("测试小说", "测试作者")
    assert novel_id == 1

    novel = db.conn.execute("SELECT * FROM novel WHERE id = ?", (novel_id,)).fetchone()
    assert novel["title"] == "测试小说"
    assert novel["author"] == "测试作者"


def test_create_and_get_chapter(db):
    novel_id = db.create_novel("测试小说", "")
    chapter_id = db.create_chapter(novel_id, 1, "第一章内容...")
    assert chapter_id == 1

    chapter = db.get_chapter(chapter_id)
    assert chapter is not None
    assert chapter["chapter_num"] == 1
    assert chapter["raw_text"] == "第一章内容..."
    assert chapter["status"] == "idle"


def test_get_chapter_not_found(db):
    assert db.get_chapter(999) is None


def test_save_script_and_storyboard_shots(db):
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")

    script_json = {"scenes": [{"scene_name": "大殿", "shots": []}]}
    script_id = db.save_script(chapter_id, script_json)
    assert script_id == 1

    shots = [
        {
            "shot_num": 1,
            "narration": "",
            "dialogue": "张三: 到了。",
            "camera_movement": "static",
            "duration_sec": 5.0,
            "char_ids": [1],
            "scene_id": 1,
        },
        {
            "shot_num": 2,
            "narration": "风吹过山谷",
            "dialogue": "",
            "camera_movement": "slow_pan",
            "duration_sec": 8.0,
            "char_ids": [1, 2],
            "scene_id": 1,
        },
    ]
    shot_ids = db.save_storyboard_shots(script_id, shots)
    assert len(shot_ids) == 2

    saved_shots = db.get_storyboard_shots(script_id)
    assert len(saved_shots) == 2
    assert saved_shots[0]["shot_num"] == 1
    assert saved_shots[0]["dialogue"] == "张三: 到了。"


def test_get_or_create_character(db):
    char_id, is_new = db.get_or_create_character("张三")
    assert char_id == 1
    assert is_new is True

    char_id2, is_new2 = db.get_or_create_character("张三")
    assert char_id2 == 1
    assert is_new2 is False


def test_get_or_create_scene(db):
    scene_id = db.get_or_create_scene("大殿")
    assert scene_id == 1

    scene_id2 = db.get_or_create_scene("大殿")
    assert scene_id2 == 1


def test_agent_status_lifecycle(db):
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")

    # Initially no status
    assert db.get_agent_status("screenwriter", chapter_id) is None

    # Set to running
    db.set_agent_status("screenwriter", chapter_id, "running")
    assert db.get_agent_status("screenwriter", chapter_id) == "running"

    # Set to done
    db.set_agent_status("screenwriter", chapter_id, "done")
    assert db.get_agent_status("screenwriter", chapter_id) == "done"


def test_task_log(db):
    db.log("screenwriter", 1, "script_generated", {"script_id": 5})

    row = db.conn.execute(
        "SELECT * FROM task_log WHERE agent_name = 'screenwriter'"
    ).fetchone()
    assert row is not None
    assert row["event"] == "script_generated"
    assert row["level"] == "INFO"
