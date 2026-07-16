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


def test_migrate_schema_adds_image_prompt_column(db):
    """v0.3 migration: ALTER TABLE storyboard_shot ADD COLUMN image_prompt."""
    db.migrate_schema()

    # Verify the column exists
    cols = db.conn.execute("PRAGMA table_info(storyboard_shot)").fetchall()
    col_names = [c["name"] for c in cols]
    assert "image_prompt" in col_names

    # Verify idempotent: can call again without error
    db.migrate_schema()


def test_update_appearance_variant_views(db):
    """新增方法: 回填 appearance_variant 的 front/side/back_view 列."""
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")
    char_id, _ = db.get_or_create_character("叶凡")
    variant_id = db.create_appearance_variant(
        character_id=char_id,
        variant_name="default",
        variant_type="default",
        appearance_json='{"full_prompt": "test"}',
    )

    db.update_appearance_variant_views(
        variant_id=variant_id,
        front="正面视图prompt",
        side="侧面视图prompt",
        back="背面视图prompt",
    )

    # Verify columns populated
    row = db.conn.execute(
        "SELECT front_view, side_view, back_view FROM appearance_variant WHERE id = ?",
        (variant_id,),
    ).fetchone()
    assert row["front_view"] == "正面视图prompt"
    assert row["side_view"] == "侧面视图prompt"
    assert row["back_view"] == "背面视图prompt"


def test_update_scene_card_with_views(db):
    """update_scene_card 现在接受 6 个字段，包括 wide/mid/close_view."""
    scene_id = db.get_or_create_scene("山门")
    db.update_scene_card(
        scene_id=scene_id,
        description="巍峨山门",
        lighting="晨光金色",
        style="中式仙侠",
        wide_view="全景广角视图prompt",
        mid_view="中景核心区域prompt",
        close_view="特写细节prompt",
    )

    row = db.conn.execute(
        "SELECT * FROM scene_card WHERE id = ?", (scene_id,)
    ).fetchone()
    assert row["description"] == "巍峨山门"
    assert row["lighting"] == "晨光金色"
    assert row["style"] == "中式仙侠"
    assert row["wide_view"] == "全景广角视图prompt"
    assert row["mid_view"] == "中景核心区域prompt"
    assert row["close_view"] == "特写细节prompt"
    assert row["status"] == "done"


def test_update_shot_image_prompt(db):
    """Update image_prompt field on a storyboard shot."""
    db.migrate_schema()

    # Set up: create a novel, chapter, script, and a shot
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")
    script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})
    shot_ids = db.save_storyboard_shots(script_id, [{
        "shot_num": 1, "narration": "", "dialogue": "",
        "camera_movement": "MS", "duration_sec": 5.0,
        "char_ids": [], "scene_id": None,
    }])

    # Update the image prompt
    prompt = "古代仙侠风格，16:9横版构图，测试画面提示词..."
    db.update_shot_image_prompt(shot_ids[0], prompt)

    # Verify it was saved
    shots = db.get_storyboard_shots(script_id)
    assert shots[0]["image_prompt"] == prompt


def test_create_final_video(db):
    """创建 final_video 行并返回 id."""
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")

    fv_id = db.create_final_video(chapter_id, "data/videos/final_1.mp4")
    assert fv_id == 1

    row = db.conn.execute(
        "SELECT * FROM final_video WHERE id = ?", (fv_id,)
    ).fetchone()
    assert row is not None
    assert row["chapter_id"] == chapter_id
    assert row["file_path"] == "data/videos/final_1.mp4"


def test_migrate_schema_adds_image_columns(db):
    """v0.6 migration: add front/side/back_image to appearance_variant; wide/mid/close_image to scene_card."""
    db.migrate_schema()

    # Verify appearance_variant columns
    av_cols = db.conn.execute("PRAGMA table_info(appearance_variant)").fetchall()
    av_names = [c["name"] for c in av_cols]
    for col in ["front_image", "side_image", "back_image"]:
        assert col in av_names, f"{col} missing from appearance_variant"

    # Verify scene_card columns
    sc_cols = db.conn.execute("PRAGMA table_info(scene_card)").fetchall()
    sc_names = [c["name"] for c in sc_cols]
    for col in ["wide_image", "mid_image", "close_image"]:
        assert col in sc_names, f"{col} missing from scene_card"

    # Verify idempotent
    db.migrate_schema()


def test_update_appearance_variant_image(db):
    """回填 appearance_variant 的 {view}_image 列."""
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")
    char_id, _ = db.get_or_create_character("叶凡")
    variant_id = db.create_appearance_variant(
        character_id=char_id,
        variant_name="default",
        variant_type="default",
        appearance_json='{"full_prompt": "test"}',
    )
    db.migrate_schema()

    db.update_appearance_variant_image(variant_id, "front", "data/images/front_1.png")
    db.update_appearance_variant_image(variant_id, "side", "data/images/side_1.png")
    db.update_appearance_variant_image(variant_id, "back", "data/images/back_1.png")

    row = db.conn.execute(
        "SELECT front_image, side_image, back_image FROM appearance_variant WHERE id = ?",
        (variant_id,),
    ).fetchone()
    assert row["front_image"] == "data/images/front_1.png"
    assert row["side_image"] == "data/images/side_1.png"
    assert row["back_image"] == "data/images/back_1.png"


def test_update_scene_card_image(db):
    """回填 scene_card 的 {view}_image 列."""
    scene_id = db.get_or_create_scene("山门")
    db.migrate_schema()

    db.update_scene_card_image(scene_id, "wide", "data/images/wide_1.png")
    db.update_scene_card_image(scene_id, "mid", "data/images/mid_1.png")
    db.update_scene_card_image(scene_id, "close", "data/images/close_1.png")

    row = db.conn.execute(
        "SELECT wide_image, mid_image, close_image FROM scene_card WHERE id = ?",
        (scene_id,),
    ).fetchone()
    assert row["wide_image"] == "data/images/wide_1.png"
    assert row["mid_image"] == "data/images/mid_1.png"
    assert row["close_image"] == "data/images/close_1.png"
