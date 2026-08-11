"""Tests for Orchestrator pipeline coordination (v0.10: 2-step script→storyboard)."""

import tempfile
from pathlib import Path

from aicomic.interface import AgentInterface, AgentResult
from aicomic.bus import AgentBus
from aicomic.orchestrator import Orchestrator
from aicomic.db.repository import Database


class _FakeScriptwriter(AgentInterface):
    """Fake for ScriptwriterAgent (v0.10 step 1)."""

    agent_name = "scriptwriter"

    def __init__(self):
        self.executed = False
        self.will_fail = False

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "raw_text" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        if self.will_fail:
            return AgentResult(success=False, error="LLM API error")
        self.executed = True
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={
                "script_id": 1,
                "characters": ["张三"],
                "scenes_list": ["大殿"],
                "beat_count": 6,
            },
        )


class _FakeStoryboardAgent(AgentInterface):
    """Fake for StoryboardAgent (v0.10 step 5, was old Screenwriter)."""

    agent_name = "storyboard-agent"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"shots_created": 6},
        )


class _FakeCharDesigner(AgentInterface):
    agent_name = "char-designer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "characters" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"outfits_created": 2, "character_names": input_data.get("characters", [])},
        )


class _FakeSceneDesigner(AgentInterface):
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


class _FakeOutfitManager(AgentInterface):
    agent_name = "outfit-manager"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"outfits_generated": 0, "shots_tagged": 0},
        )


class _FakeShotVisualizer(AgentInterface):
    agent_name = "shot-visualizer"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"shots_processed": 6, "total_shots": 6},
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
            data={"clips_created": 6, "total_shots": 6, "already_done": 0},
        )


class _FakeShotVideoGenerator(AgentInterface):
    agent_name = "shot-video-generator"

    def validate_input(self, input_data: dict) -> bool:
        return "chapter_id" in input_data and "script_id" in input_data

    def execute(self, input_data: dict, db) -> AgentResult:
        chapter_id = input_data["chapter_id"]
        db.set_agent_status(self.agent_name, chapter_id, "done")
        return AgentResult(
            success=True,
            data={"clips_created": 6, "total_shots": 6, "already_done": 0, "failed_count": 0},
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
            data={"final_video_path": "data/videos/final_1.mp4", "clip_count": 6},
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
            data={"images_generated": 6, "outfits_processed": 2, "scenes_processed": 1},
        )


def _register_all_agents(bus, with_composer=False, with_images=False):
    """Register all fake agents for v0.10 pipeline."""
    bus.register(_FakeScriptwriter())
    bus.register(_FakeStoryboardAgent())
    bus.register(_FakeCharDesigner())
    bus.register(_FakeSceneDesigner())
    bus.register(_FakeOutfitManager())
    if with_images:
        bus.register(_FakeImageGenerator())
    bus.register(_FakeShotVisualizer())
    bus.register(_FakeShotVideoGenerator())
    bus.register(_FakeVideoGenerator())
    if with_composer:
        bus.register(_FakeVideoComposer())


# ── Tests ──

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
        assert result.data["beat_count"] == 6
        assert result.data["outfits_created"] == 2
        assert result.data["scenes_updated"] == 2
        assert result.data["shots_created"] == 6
        assert result.data["shots_visualized"] == 6
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_scriptwriter_fails():
    """v0.10: pipeline should abort if scriptwriter step fails."""
    bus = AgentBus()
    sw = _FakeScriptwriter()
    sw.will_fail = True
    bus.register(sw)
    bus.register(_FakeCharDesigner())
    bus.register(_FakeSceneDesigner())

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
        assert "LLM API error" in result.error
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
        result1 = orchestrator.run_chapter(chapter_id, "内容")
        assert result1.success is True
        result2 = orchestrator.run_chapter(chapter_id, "内容")
        assert result2.success is True
    finally:
        db.close()
        db_path.unlink()


# ── Full integration tests ──

class FakeLLMForScriptwriter:
    """Returns a valid SCRIPT JSON (ScriptwriterAgent output format)."""

    def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return {
            "era_background": "中国古代·仙侠",
            "scenes": [
                {
                    "scene_name": "山门",
                    "scene_index": 1,
                    "atmosphere": "晨光肃穆",
                    "scene_sound_cues": ["风声", "鸟鸣"],
                    "beats": [
                        {
                            "beat_num": 1,
                            "characters": ["叶凡"],
                            "action": "叶凡站在山门前，仰望牌匾",
                            "dialogue": [],
                            "expressions": {"叶凡": "神情坚定"},
                            "sound_cue": "风声呼啸",
                        },
                        {
                            "beat_num": 2,
                            "characters": ["叶凡"],
                            "action": "叶凡深吸一口气",
                            "dialogue": [
                                {"speaker": "叶凡", "line": "这就是青云宗...", "emotion": "感慨"}
                            ],
                            "expressions": {"叶凡": "目光灼灼"},
                            "sound_cue": "深呼吸声",
                        },
                    ],
                },
                {
                    "scene_name": "大殿",
                    "scene_index": 2,
                    "atmosphere": "庄严华贵",
                    "scene_sound_cues": ["烛火噼啪"],
                    "beats": [
                        {
                            "beat_num": 3,
                            "characters": ["叶凡", "长老"],
                            "action": "殿内，白发长老端坐蒲团",
                            "dialogue": [
                                {"speaker": "长老", "line": "你终于来了。", "emotion": "平静"}
                            ],
                            "expressions": {"叶凡": "恭敬低头", "长老": "嘴角微扬"},
                            "sound_cue": "袍服摩擦声",
                        },
                    ],
                },
            ],
            "characters": ["叶凡", "长老"],
            "scenes_list": ["山门", "大殿"],
        }


class FakeLLMForStoryboard:
    """Returns a valid STORYBOARD JSON (v0.13 industry format with segments)."""

    def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return {
            "scenes": [
                {
                    "scene_name": "山门",
                    "scene_index": 1,
                    "shots": [
                        {
                            "shot_num": 1, "shot_type": "both", "duration_sec": 10.0,
                            "characters": [{"name": "叶凡", "variant": "default"}],
                            "scene_name": "山门",
                            "segments": [
                                {"time_range": "0-3秒", "camera": "全景",
                                 "action": "叶凡站在山门前，仰望牌匾。", "dialogue": None,
                                 "sound": "风声", "transition": None},
                                {"time_range": "3-7秒", "camera": "中景",
                                 "action": "叶凡深吸一口气，迈步向前。", "dialogue":
                                 "叶凡（感慨，音色：清朗少年）: 这就是青云宗...",
                                 "sound": "脚步声", "transition": "延续中景，叶凡迈入山门"},
                                {"time_range": "7-10秒", "camera": "全景",
                                 "action": "叶凡背影消失在云雾缭绕的山门中。", "dialogue": None,
                                 "sound": "风声渐远",
                                 "transition": "衔接镜头2的0-3秒"},
                            ],
                            "scene_summary": "场景：仙侠山门，云雾缭绕。（视频不要添加字幕）",
                        },
                    ],
                },
                {
                    "scene_name": "大殿",
                    "scene_index": 2,
                    "shots": [
                        {
                            "shot_num": 2, "shot_type": "both", "duration_sec": 8.0,
                            "characters": [
                                {"name": "叶凡", "variant": "default"},
                                {"name": "长老", "variant": "default"},
                            ],
                            "scene_name": "大殿",
                            "segments": [
                                {"time_range": "0-3秒", "camera": "全景",
                                 "action": "叶凡进入大殿，立于殿中。", "dialogue": None,
                                 "sound": "脚步声", "transition": None},
                                {"time_range": "3-7秒", "camera": "中景",
                                 "action": "白发长老端坐蒲团之上。", "dialogue":
                                 "长老（平静，音色：威严老者）: 你终于来了。",
                                 "sound": "静谧", "transition": "延续中景"},
                                {"time_range": "7-10秒", "camera": "近景",
                                 "action": "叶凡立于殿中，神色恭敬。", "dialogue": None,
                                 "sound": "钟声回荡", "transition": None},
                            ],
                            "scene_summary": "场景：仙侠大殿，宏伟庄严。（视频不要添加字幕）",
                        },
                    ],
                },
            ],
            "characters": ["叶凡", "长老"],
            "scenes_list": ["山门", "大殿"],
        }


class FakeLLMForCharDesigner:
    def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return {
            "era_background": "中国古代·仙侠",
            "characters": [
                {
                    "name": "叶凡", "aliases": [], "gender": "男", "age": 18,
                    "is_human": True,
                    "design_prompt": "【中国古代·仙侠】叶凡，男 18岁，8k 类 3D 游戏 cg 电影风格...",
                },
                {
                    "name": "长老", "aliases": [], "gender": "男", "age": 60,
                    "is_human": True,
                    "design_prompt": "【中国古代·仙侠】长老，男 60岁，8k 类 3D 游戏 cg 电影风格...",
                },
            ],
        }


class FakeLLMForSceneDesigner:
    def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return {
            "era_background": "中国古代·仙侠",
            "scenes": [
                {
                    "name": "山门", "description": "巍峨山门", "lighting": "晨光",
                    "style": "中式仙侠", "environment_type": "室外", "time_of_day": "清晨",
                    "atmosphere": "肃穆", "visual_features": "青石牌坊",
                    "full_prompt": "full_prompt_1",
                    "wide_view_prompt": "wide_1", "mid_view_prompt": "mid_1",
                    "close_view_prompt": "close_1", "multi_view_prompt": "multi_1",
                },
                {
                    "name": "大殿", "description": "华美大殿", "lighting": "烛光",
                    "style": "中式古典", "environment_type": "室内", "time_of_day": "早晨",
                    "atmosphere": "威严", "visual_features": "雕龙石柱",
                    "full_prompt": "full_prompt_2",
                    "wide_view_prompt": "wide_2", "mid_view_prompt": "mid_2",
                    "close_view_prompt": "close_2", "multi_view_prompt": "multi_2",
                },
            ],
        }


class FakeLLMForShotVisualizer:
    def generate_json(self, system_prompt, user_prompt, max_tokens=4096):
        return {
            "shots": [
                {"shot_num": 1, "image_prompt": "镜头1画面", "composition": "中景", "mood": "晨光"},
                {"shot_num": 2, "image_prompt": "镜头2画面", "composition": "全景", "mood": "庄严"},
            ],
        }


def test_full_pipeline_integration():
    """v0.10: Scriptwriter→CharDesigner→SceneDesigner→Outfit→Storyboard→ShotVisualizer"""
    from aicomic.agents.scriptwriter import ScriptwriterAgent
    from aicomic.agents.screenwriter import ScreenwriterAgent
    from aicomic.agents.char_designer import CharacterDesignerAgent
    from aicomic.agents.scene_designer import SceneDesignerAgent
    from aicomic.agents.shot_visualizer import ShotVisualizerAgent
    from aicomic.agents.outfit_manager import OutfitManagerAgent

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    db = Database(db_path)
    db.connect()
    db.init_schema()
    db.migrate_schema()

    try:
        novel_id = db.create_novel("测试修仙", "作者")
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前...")

        scriptwriter = ScriptwriterAgent(llm_client=FakeLLMForScriptwriter())
        storyboard_agent = ScreenwriterAgent(llm_client=FakeLLMForStoryboard())
        char_designer = CharacterDesignerAgent(llm_client=FakeLLMForCharDesigner())
        scene_designer = SceneDesignerAgent(llm_client=FakeLLMForSceneDesigner())
        shot_visualizer = ShotVisualizerAgent(llm_client=FakeLLMForShotVisualizer())
        outfit_manager = OutfitManagerAgent(llm_client=FakeLLMForScriptwriter())

        bus = AgentBus()
        bus.register(scriptwriter)
        bus.register(storyboard_agent)
        bus.register(char_designer)
        bus.register(scene_designer)
        bus.register(shot_visualizer)
        bus.register(outfit_manager)

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(chapter_id, "叶凡走到山门前...")

        assert result.success is True
        assert result.data is not None
        assert result.data["script_id"] == 1
        assert set(result.data["characters"]) == {"叶凡", "长老"}
        assert result.data["scenes_list"] == ["山门", "大殿"]
        assert result.data["beat_count"] == 3
        assert result.data["outfits_created"] == 2
        assert result.data["scenes_updated"] == 2
        assert result.data["shots_created"] == 2
        assert result.data["shots_visualized"] == 2

        # Verify DB: storyboard shots
        shots = db.get_storyboard_shots(1)
        assert len(shots) == 2
        # v0.13+: verify segments_json is stored
        import json
        segs = json.loads(shots[0].get("segments_json", "[]"))
        assert len(segs) == 3

        # Verify characters & scenes
        chars = db.conn.execute("SELECT name FROM character_card ORDER BY id").fetchall()
        assert {c["name"] for c in chars} == {"叶凡", "长老"}
        scenes = db.conn.execute("SELECT name FROM scene_card ORDER BY id").fetchall()
        assert {s["name"] for s in scenes} == {"山门", "大殿"}

        # Verify agent statuses
        assert db.get_agent_status("scriptwriter", chapter_id) == "done"
        assert db.get_agent_status("storyboard-agent", chapter_id) == "done"
        assert db.get_agent_status("char-designer", chapter_id) == "done"
        assert db.get_agent_status("scene-designer", chapter_id) == "done"
        assert db.get_agent_status("shot-visualizer", chapter_id) == "done"
        assert db.get_agent_status("video-generator", chapter_id) is None
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_with_video_and_composer():
    """v0.10: with_video=True should run VideoGenerator + VideoComposer."""
    bus = AgentBus()
    _register_all_agents(bus, with_composer=True)

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
        assert result.data["clips_created"] == 6
        assert result.data.get("final_video_path") is not None
        assert db.get_agent_status("video-composer", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()


def test_orchestrator_run_chapter_with_images():
    """v0.10: with_images=True should run ImageGenerator."""
    bus = AgentBus()
    _register_all_agents(bus, with_images=True)

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
    """v0.10: full pipeline with video generation."""
    from aicomic.agents.scriptwriter import ScriptwriterAgent
    from aicomic.agents.screenwriter import ScreenwriterAgent
    from aicomic.agents.char_designer import CharacterDesignerAgent
    from aicomic.agents.scene_designer import SceneDesignerAgent
    from aicomic.agents.shot_visualizer import ShotVisualizerAgent
    from aicomic.agents.outfit_manager import OutfitManagerAgent
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
        chapter_id = db.create_chapter(novel_id, 1, "叶凡走到山门前...")

        scriptwriter = ScriptwriterAgent(llm_client=FakeLLMForScriptwriter())
        storyboard_agent = ScreenwriterAgent(llm_client=FakeLLMForStoryboard())
        char_designer = CharacterDesignerAgent(llm_client=FakeLLMForCharDesigner())
        scene_designer = SceneDesignerAgent(llm_client=FakeLLMForSceneDesigner())
        shot_visualizer = ShotVisualizerAgent(llm_client=FakeLLMForShotVisualizer())
        outfit_manager = OutfitManagerAgent(llm_client=FakeLLMForScriptwriter())
        video_agent = VideoGeneratorAgent(
            llm_client=FakeLLMForShotVisualizer(),
            video_generator=MockVideoGenerator(output_dir=Path("/tmp")),
        )

        bus = AgentBus()
        bus.register(scriptwriter)
        bus.register(storyboard_agent)
        bus.register(char_designer)
        bus.register(scene_designer)
        bus.register(shot_visualizer)
        bus.register(outfit_manager)
        bus.register(_FakeShotVideoGenerator())
        bus.register(video_agent)

        orchestrator = Orchestrator(bus, db)
        result = orchestrator.run_chapter(
            chapter_id, "叶凡走到山门前...", with_video=True,
        )

        assert result.success is True
        assert result.data is not None
        assert result.data["clips_created"] == 6  # _FakeShotVideoGenerator hardcoded

        # Note: _FakeShotVideoGenerator doesn't write to DB, so skip clip count check
        assert result.data["script_id"] is not None

        assert db.get_agent_status("shot-video-generator", chapter_id) == "done"
    finally:
        db.close()
        db_path.unlink()
