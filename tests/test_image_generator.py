"""Tests for Image Generator Agent."""

import tempfile
from pathlib import Path

from aicomic.agents.image_generator import ImageGeneratorAgent
from aicomic.doubao.browser import ImageResult
from aicomic.db.repository import Database


class FakeBrowserClient:
    """Stubs out DoubaoBrowserClient for testing — returns fake ImageResults."""

    def __init__(self):
        self.call_count = 0
        self.prompts: list[str] = []
        self.will_fail = False

    def generate_image(self, prompt: str, aspect_ratio: str = "16:9") -> ImageResult:
        self.call_count += 1
        self.prompts.append(prompt)
        if self.will_fail:
            return ImageResult(success=False, file_path="", file_paths=[], error="Fake error")
        path = f"/tmp/fake_image_{self.call_count}.png"
        return ImageResult(
            success=True,
            file_path=path,
            file_paths=[path],
            url=f"https://example.com/img_{self.call_count}.png",
            metadata={"generator": "fake"},
        )


def _make_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()
    return db, db_path


def _setup_full_data(db: Database) -> tuple[int, int]:
    """Create novel, chapter, script, char variants and scene cards with composite prompts."""
    novel_id = db.create_novel("测试", "")
    chapter_id = db.create_chapter(novel_id, 1, "内容")
    script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})

    # Create a character with variant + three_view_prompt (composite prompt)
    char_id, _ = db.get_or_create_character("叶凡")
    variant_id = db.create_appearance_variant(
        character_id=char_id,
        variant_name="default",
        variant_type="default",
        appearance_json='{"full_prompt": "test"}',
    )
    db.update_appearance_variant_three_view_prompt(
        variant_id=variant_id,
        prompt="正面侧面背面三视图组合prompt",
    )
    db.set_character_default_look(char_id, variant_id)

    # Create a scene with multi_view_prompt (composite prompt)
    scene_id = db.get_or_create_scene("山门")
    db.update_scene_card(
        scene_id=scene_id,
        description="巍峨山门",
        lighting="晨光金色",
        style="中式仙侠",
    )
    db.update_scene_card_multi_view_prompt(
        scene_id=scene_id,
        prompt="全景中景特写组合prompt",
    )

    return chapter_id, script_id


# ── Tests ──

def test_validate_input_valid():
    agent = ImageGeneratorAgent(browser_client=FakeBrowserClient())
    assert agent.validate_input({"chapter_id": 1, "script_id": 1}) is True


def test_validate_input_missing_script_id():
    agent = ImageGeneratorAgent(browser_client=FakeBrowserClient())
    assert agent.validate_input({"chapter_id": 1}) is False


def test_validate_input_missing_chapter_id():
    agent = ImageGeneratorAgent(browser_client=FakeBrowserClient())
    assert agent.validate_input({"script_id": 1}) is False


def test_execute_success():
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_full_data(db)

        fake_browser = FakeBrowserClient()
        agent = ImageGeneratorAgent(browser_client=fake_browser)
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        assert result.data is not None
        # 1 variant x 1 composite prompt + 1 scene x 1 composite prompt = 2 images
        assert result.data["images_generated"] == 2
        assert result.data["variants_processed"] == 1
        assert result.data["scenes_processed"] == 1
        assert fake_browser.call_count == 2

        # Verify DB: variant three_view_image populated (composite column)
        variants = db.conn.execute(
            "SELECT * FROM appearance_variant ORDER BY id"
        ).fetchall()
        for v in variants:
            vd = dict(v)
            assert vd["three_view_image"] != "", "three_view_image should be populated"

        # Verify DB: scene multi_view_image populated (composite column)
        scenes = db.conn.execute(
            "SELECT * FROM scene_card ORDER BY id"
        ).fetchall()
        for s in scenes:
            sd = dict(s)
            assert sd["multi_view_image"] != "", "multi_view_image should be populated"

        # Verify agent status marked done
        assert db.get_agent_status("image-generator", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_execute_skips_when_already_done():
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_full_data(db)

        fake_browser = FakeBrowserClient()
        agent = ImageGeneratorAgent(browser_client=fake_browser)

        # First run
        result1 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id}, db
        )
        assert result1.success is True
        first_count = fake_browser.call_count

        # Second run — should skip
        result2 = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id}, db
        )
        assert result2.success is True
        assert result2.data.get("status") == "skipped"
        # No additional browser calls
        assert fake_browser.call_count == first_count
    finally:
        db.close()
        db_path.unlink()


def test_execute_all_browser_calls_fail():
    """When all generate_image calls fail, agent should still not crash."""
    db, db_path = _make_db()
    try:
        chapter_id, script_id = _setup_full_data(db)

        fake_browser = FakeBrowserClient()
        fake_browser.will_fail = True
        agent = ImageGeneratorAgent(browser_client=fake_browser)
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        # Agent should report non-success since ALL images failed
        assert result.success is False
        assert "No images" in result.error or "images generated" in str(result.data.get("images_generated", ""))
        assert result.data["images_generated"] == 0
    finally:
        db.close()
        db_path.unlink()


def test_execute_no_variants_no_scenes():
    """Chapter with no variants and no scene cards should complete gracefully."""
    db, db_path = _make_db()
    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")
        script_id = db.save_script(chapter_id, {"scenes": [], "characters": [], "scenes_list": []})
        # No variants, no scene cards created

        fake_browser = FakeBrowserClient()
        agent = ImageGeneratorAgent(browser_client=fake_browser)
        result = agent.execute(
            {"chapter_id": chapter_id, "script_id": script_id},
            db,
        )

        assert result.success is True
        assert result.data["images_generated"] == 0
        assert fake_browser.call_count == 0
    finally:
        db.close()
        db_path.unlink()
