"""Tests for Orchestrator pipeline coordination (v0.2: 3-agent pipeline)."""

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


class _FakeCharDesigner(AgentInterface):
    """Minimal fake for the Character Designer agent."""

    agent_name = "char-designer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "characters" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"variants_created": 2, "character_names": input_data.get("characters", [])},
        )


class _FakeSceneDesigner(AgentInterface):
    """Minimal fake for the Scene Designer agent."""

    agent_name = "scene-designer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "scenes_list" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"scenes_updated": 2, "scene_names": input_data.get("scenes_list", [])},
        )


class _FakeShotVisualizer(AgentInterface):
    """Minimal fake for the Shot Visualizer agent."""

    agent_name = "shot-visualizer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"shots_processed": 14, "total_shots": 14},
        )


class _FakeVideoGenerator(AgentInterface):
    agent_name = "video-generator"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"clips_created": 14, "total_shots": 14, "already_done": 0},
        )


class _FakeVideoComposer(AgentInterface):
    agent_name = "video-composer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={
                "final_video_path": "data/videos/final_1.mp4",
                "clip_count": 14,
                "total_duration": 70.0,
            },
        )


class _FakeImageGenerator(AgentInterface):
    agent_name = "image-generator"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={
                "images_generated": 6,
                "variants_processed": 1,
                "scenes_processed": 1,
            },
        )


def _register_all_agents(
    bus: AgentBus,
    with_video_composer: bool = False,
    with_image_generator: bool = False,
):
    """Register all fake agents."""
    bus.register(_FakeScreenwriter())
    bus.register(_FakeCharDesigner())
    bus.register(_FakeSceneDesigner())
    if with_image_generator:
        bus.register(_FakeImageGenerator())
    bus.register(_FakeShotVisualizer())
    bus.register(_FakeVideoGenerator())
    if with_video_composer:
        bus.register(_FakeVideoComposer())


def test_orchestrator_run_chapter_success():
    bus = AgentBus()
    _register_all_agents(bus)

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
        assert result.data is not None
        assert result.data["script_id"] == 1
        assert result.data["characters"] == ["张三"]
        assert result.data["scenes_list"] == ["大殿"]
        assert result.data["char_variants_created"] == 2
        assert result.data["scenes_updated"] == 2
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_screenwriter_fails():
    bus = AgentBus()
    screenwriter = _FakeScreenwriter()
    screenwriter.will_fail = True
    bus.register(screenwriter)
    bus.register(_FakeCharDesigner())
    bus.register(_FakeSceneDesigner())
    bus.register(_FakeShotVisualizer())

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
    _register_all_agents(bus)

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

        # Second run — screenwriter may skip, others may not
        # The real ScreenwriterAgent checks for "done" in execute().
        # Fake agents don't check — but the pipeline still runs
        result2 = orchestrator.run_chapter(chapter_id, "内容")
        assert result2.success is True
    finally:
        db.close()
        db_path.unlink()


# ── Integration: full v0.2 pipeline with fake LLMs ──

class FakeClaudeForIntegration:
    """Returns a valid script JSON covering multiple shots and characters."""

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        return {
            "era_background": "中国古代·仙侠",
            "scenes": [
                {
                    "scene_name": "山门",
                    "scene_index": 1,
                    "shots": [
                        {
                            "shot_num": 1,
                            "shot_type": "action",
                            "duration_sec": 4.0,
                            "characters": [{"name": "叶凡", "variant": "default"}],
                            "scene_name": "山门",
                            "narration": "叶凡站在山门前，仰望巍峨的牌匾。",
                            "dialogue": "",
                            "camera_movement": "LS",
                        },
                        {
                            "shot_num": 2,
                            "shot_type": "both",
                            "duration_sec": 3.0,
                            "characters": [{"name": "叶凡", "variant": "default"}],
                            "scene_name": "山门",
                            "narration": "叶凡深吸一口气。",
                            "dialogue": "叶凡: 这就是青云宗...",
                            "camera_movement": "MS",
                        },
                    ],
                },
                {
                    "scene_name": "大殿",
                    "scene_index": 2,
                    "shots": [
                        {
                            "shot_num": 3,
                            "shot_type": "both",
                            "duration_sec": 6.0,
                            "characters": [
                                {"name": "叶凡", "variant": "default"},
                                {"name": "长老", "variant": "default"},
                            ],
                            "scene_name": "大殿",
                            "narration": "殿内，一位白发长老端坐于蒲团之上。",
                            "dialogue": "长老: 你终于来了。",
                            "camera_movement": "Pan",
                        },
                    ],
                },
            ],
            "characters": ["叶凡", "长老"],
            "scenes_list": ["山门", "大殿"],
        }


class FakeLLMForCharDesigner:
    """Returns a canned character design JSON."""

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        return {
            "era_background": "中国古代·仙侠",
            "characters": [
                {
                    "name": "叶凡",
                    "aliases": [],
                    "gender": "男",
                    "age": 18,
                    "height_cm": 178,
                    "is_human": True,
                    "variants": [
                        {
                            "variant_name": "default",
                            "hair": "黑色长发束髻",
                            "head_accessories": "白玉发冠",
                            "makeup": "剑眉星目",
                            "face": "清秀俊朗，肤色白净",
                            "aura": "气质坚毅",
                            "upper_body": "白色交领长袍，云纹刺绣",
                            "lower_body": "同色系长衫，墨玉腰带",
                            "footwear": "黑色云纹布靴",
                            "accessories": "左手天毒珠印记",
                            "full_prompt": "古代仙侠风格，【中国古代·仙侠】叶凡，男 18岁，身高178cm，九头身比例，写实电影感风格，正面，站立的全身图片，图片人物背景为纯白色。黑色长发束髻，白玉发冠束发；剑眉星目，清秀俊朗面容，肤色白净，气质坚毅；上身白色交领长袍，云纹刺绣；下身同色系长衫，墨玉腰带；脚上黑色云纹布靴；配饰左手天毒珠印记；双手自然下垂，手里无任何物品。",
                            "front_view_prompt": "古代仙侠风格，写实电影感风格，正面特写全身站立图片，纯白背景。叶凡。",
                            "side_view_prompt": "古代仙侠风格，写实电影感风格，侧面全身站立图片，纯白背景。叶凡。",
                            "back_view_prompt": "古代仙侠风格，写实电影感风格，背面全身站立图片，纯白背景。叶凡。",
                        }
                    ],
                },
                {
                    "name": "长老",
                    "aliases": [],
                    "gender": "男",
                    "age": 60,
                    "height_cm": 170,
                    "is_human": True,
                    "variants": [
                        {
                            "variant_name": "default",
                            "hair": "白色长发束髻",
                            "head_accessories": "木质道冠",
                            "makeup": "白眉长须，仙风道骨",
                            "face": "面容清瘦，皱纹深刻",
                            "aura": "气质威严深邃",
                            "upper_body": "灰色宽袖道袍",
                            "lower_body": "同色系长裤",
                            "footwear": "黑色布鞋",
                            "accessories": "手持拂尘",
                            "full_prompt": "古代仙侠风格，【中国古代·仙侠】长老，男 60岁，身高170cm，九头身比例，写实电影感风格，正面，站立的全身图片，图片人物背景为纯白色。白色长发束髻，木质道冠束发；白眉长须，仙风道骨，面容清瘦，皱纹深刻，气质威严深邃；上身灰色宽袖道袍；下身同色系长裤；脚上黑色布鞋；配饰手持拂尘；双手自然下垂，手里无任何物品。",
                            "front_view_prompt": "古代仙侠风格，写实电影感风格，正面特写全身站立图片，纯白背景。长老。",
                            "side_view_prompt": "古代仙侠风格，写实电影感风格，侧面全身站立图片，纯白背景。长老。",
                            "back_view_prompt": "古代仙侠风格，写实电影感风格，背面全身站立图片，纯白背景。长老。",
                        }
                    ],
                },
            ],
        }


class FakeLLMForSceneDesigner:
    """Returns a canned scene design JSON."""

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        return {
            "era_background": "中国古代·仙侠",
            "scenes": [
                {
                    "name": "山门",
                    "description": "巍峨山门，青石台阶，云雾缭绕",
                    "lighting": "晨光金色光束洒落",
                    "style": "中式仙侠宗门建筑",
                    "environment_type": "室外山门",
                    "time_of_day": "清晨",
                    "atmosphere": "肃穆庄严",
                    "visual_features": "青石牌坊，古松挺立",
                    "full_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景展示场景全貌。山门｜巍峨山门，青石台阶，晨光金色光束，古松挺立。",
                    "wide_view_prompt": "古代仙侠风格，写实电影感风格，全景广角展示场景全貌，横向16:9。山门全景。",
                    "mid_view_prompt": "古代仙侠风格，写实电影感风格，中景展示场景核心区域，横向16:9。山门中景。",
                    "close_view_prompt": "古代仙侠风格，写实电影感风格，特写展示场景关键细节，横向16:9。山门细节。",
                },
                {
                    "name": "大殿",
                    "description": "宽敞华美大殿，金色宝座居中",
                    "lighting": "烛光温暖幽暗",
                    "style": "中式古典宫殿",
                    "environment_type": "室内大殿",
                    "time_of_day": "早晨",
                    "atmosphere": "威严华贵",
                    "visual_features": "雕龙石柱，红毯铺地",
                    "full_prompt": "不能出现其他人，无人纯场景，no humans,empty,landscape only，古代仙侠风格，【中国古代·仙侠】写实电影感风格，全景展示场景全貌。大殿｜宽敞华美，金色宝座居中，雕龙石柱，烛光温暖幽暗。",
                    "wide_view_prompt": "古代仙侠风格，写实电影感风格，全景广角展示场景全貌，横向16:9。大殿全景。",
                    "mid_view_prompt": "古代仙侠风格，写实电影感风格，中景展示场景核心区域，横向16:9。大殿中景。",
                    "close_view_prompt": "古代仙侠风格，写实电影感风格，特写展示场景关键细节，横向16:9。大殿细节。",
                },
            ],
        }


class FakeLLMForShotVisualizer:
    """Returns canned shot visualizer JSON."""

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> dict:
        return {
            "shots": [
                {"shot_num": 1, "image_prompt": "镜头1画面提示词", "composition": "中景居中", "mood": "晨光柔和"},
                {"shot_num": 2, "image_prompt": "镜头2画面提示词", "composition": "近景表情", "mood": "紧张压抑"},
                {"shot_num": 3, "image_prompt": "镜头3画面提示词", "composition": "全景摇镜", "mood": "庄严肃穆"},
            ],
        }


def test_full_pipeline_integration():
    """End-to-end: novel text → Screenwriter → CharDesigner → SceneDesigner → ShotVisualizer → DB entries."""
    import tempfile

    from aicomic.bus import AgentBus
    from aicomic.orchestrator import Orchestrator
    from aicomic.db.repository import Database
    from aicomic.agents.screenwriter import ScreenwriterAgent
    from aicomic.agents.char_designer import CharacterDesignerAgent
    from aicomic.agents.scene_designer import SceneDesignerAgent
    from aicomic.agents.shot_visualizer import ShotVisualizerAgent

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()

    try:
        # Setup
        novel_id = db.create_novel("测试修仙", "作者")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前，仰望牌匾...")

        screenwriter = ScreenwriterAgent(llm_client=FakeClaudeForIntegration())
        char_designer = CharacterDesignerAgent(llm_client=FakeLLMForCharDesigner())
        scene_designer = SceneDesignerAgent(llm_client=FakeLLMForSceneDesigner())
        shot_visualizer = ShotVisualizerAgent(llm_client=FakeLLMForShotVisualizer())

        bus = AgentBus()
        bus.register(screenwriter)
        bus.register(char_designer)
        bus.register(scene_designer)
        bus.register(shot_visualizer)

        orchestrator = Orchestrator(bus, db)

        # Run
        result = orchestrator.run_chapter(chapter_id, "叶凡走到山门前，仰望牌匾...")

        # Verify orchestrator result
        assert result.success is True
        assert result.data is not None
        assert result.data["script_id"] == 1
        assert set(result.data["characters"]) == {"叶凡", "长老"}
        assert result.data["scenes_list"] == ["山门", "大殿"]
        assert result.data["char_variants_created"] == 2
        assert result.data["scenes_updated"] == 2
        assert result.data["shots_visualized"] == 3

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
        assert shots[2]["camera_movement"] == "Pan"

        # Verify DB: shot image prompts populated
        for s in shots:
            sd = dict(s)
            assert sd.get("image_prompt", "") != "", f"Shot {sd['shot_num']} has empty image_prompt"

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

        # Verify DB: appearance variants created
        variants = db.conn.execute(
            "SELECT * FROM appearance_variant ORDER BY id"
        ).fetchall()
        assert len(variants) == 2, f"Expected 2 variants, got {len(variants)}"
        for v in variants:
            vd = dict(v)
            # v0.5: view columns populated
            assert vd["front_view"] != "", f"Variant {vd['id']} front_view empty"
            assert vd["side_view"] != "", f"Variant {vd['id']} side_view empty"
            assert vd["back_view"] != "", f"Variant {vd['id']} back_view empty"

        # Verify DB: character default_look_id set
        char_rows = db.conn.execute(
            "SELECT * FROM character_card ORDER BY id"
        ).fetchall()
        for c in char_rows:
            cd = dict(c)
            assert cd["default_look_id"] is not None, f"{cd['name']} has NULL default_look_id"

        # Verify DB: scene descriptions filled
        scene_rows = db.conn.execute(
            "SELECT * FROM scene_card ORDER BY id"
        ).fetchall()
        for s in scene_rows:
            sd = dict(s)
            assert sd["description"] != "", f"Scene '{sd['name']}' description empty"
            # v0.5: view prompts populated
            assert sd["wide_view"] != "", f"Scene '{sd['name']}' wide_view empty"
            assert sd["mid_view"] != "", f"Scene '{sd['name']}' mid_view empty"
            assert sd["close_view"] != "", f"Scene '{sd['name']}' close_view empty"
            assert sd["status"] == "done"

        # Verify DB: agent status
        assert db.get_agent_status("screenwriter", chapter_id) == "done"
        assert db.get_agent_status("char-designer", chapter_id) == "done"
        assert db.get_agent_status("scene-designer", chapter_id) == "done"
        assert db.get_agent_status("shot-visualizer", chapter_id) == "done"
        # Video generator should NOT have run (with_video=False by default)
        assert db.get_agent_status("video-generator", chapter_id) is None

        # Verify DB: task log entries exist
        logs = db.conn.execute(
            "SELECT * FROM task_log WHERE chapter_id = ? ORDER BY id",
            (chapter_id,),
        ).fetchall()
        log_events = [l["event"] for l in logs]
        assert "pipeline_started" in log_events
        assert "pipeline_completed" in log_events
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_with_video_and_composer():
    """v0.5: with_video=True should also run Video Composer."""
    bus = AgentBus()
    _register_all_agents(bus, with_video_composer=True)

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
        result = orchestrator.run_chapter(chapter_id, "内容", with_video=True)

        assert result.success is True
        assert result.data["clips_created"] == 14
        # v0.5: composer data
        assert result.data.get("final_video_path") is not None
        assert result.data.get("clip_count") == 14
        assert db.get_agent_status("video-composer", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_with_images():
    """v0.6: with_images=True should run ImageGenerator at Step 3.5."""
    bus = AgentBus()
    _register_all_agents(bus, with_image_generator=True)

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()

    try:
        novel_id = db.create_novel("测试", "")
        chapter_id = db.create_chapter(novel_id, 1, "内容")

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, "内容", with_images=True)

        assert result.success is True
        assert result.data.get("images_generated") == 6
        assert db.get_agent_status("image-generator", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_full_pipeline_integration_with_video():
    """End-to-end with video generation step enabled."""
    import tempfile

    from aicomic.bus import AgentBus
    from aicomic.orchestrator import Orchestrator
    from aicomic.db.repository import Database
    from aicomic.agents.screenwriter import ScreenwriterAgent
    from aicomic.agents.char_designer import CharacterDesignerAgent
    from aicomic.agents.scene_designer import SceneDesignerAgent
    from aicomic.agents.shot_visualizer import ShotVisualizerAgent
    from aicomic.agents.video_generator import VideoGeneratorAgent
    from aicomic.doubao.client import MockVideoGenerator

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()

    try:
        novel_id = db.create_novel("测试修仙", "作者")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前，仰望牌匾...")

        screenwriter = ScreenwriterAgent(llm_client=FakeClaudeForIntegration())
        char_designer = CharacterDesignerAgent(llm_client=FakeLLMForCharDesigner())
        scene_designer = SceneDesignerAgent(llm_client=FakeLLMForSceneDesigner())
        shot_visualizer = ShotVisualizerAgent(llm_client=FakeLLMForShotVisualizer())
        video_agent = VideoGeneratorAgent(
            llm_client=FakeLLMForShotVisualizer(),
            video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
        )

        bus = AgentBus()
        bus.register(screenwriter)
        bus.register(char_designer)
        bus.register(scene_designer)
        bus.register(shot_visualizer)
        bus.register(video_agent)

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, "叶凡走到山门前，仰望牌匾...", with_video=True)

        assert result.success is True
        assert result.data is not None
        assert result.data["clips_created"] == 3

        # Verify video_clip rows
        clips = db.get_video_clips(result.data["script_id"])
        assert len(clips) == 3
        for c in clips:
            assert c["status"] == "done"
            assert c["file_path"] != ""

        assert db.get_agent_status("video-generator", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()
