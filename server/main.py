"""FastAPI application entry point."""
import logging
import os
import sqlite3
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logger = logging.getLogger("aicomic-server")

app = FastAPI(title="AI漫剧", version="0.1.0")

# CORS — 允许前端 dev server (Vite :5173) 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 数据库路径 ──
DB_PATH = Path("data/aicomic.db")
CONFIG_PATH = Path("config/settings.yaml")


def _load_config() -> dict:
    """加载 YAML 配置."""
    config = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    # Env var overrides
    for key, env_var in [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ]:
        env_val = os.environ.get(env_var) or os.environ.get(f"AICOMIC_{env_var}")
        if env_val:
            config.setdefault(key, {})["api_key"] = env_val

    return config


def _build_llm_client(config: dict):
    """构建 LLM 客户端."""
    backend = config.get("backend", "deepseek")
    api_key = config.get(backend, {}).get("api_key", "")
    if not api_key:
        raise RuntimeError(
            f"No API key for backend '{backend}'. "
            f"Set {backend.upper()}_API_KEY env var or config/settings.yaml"
        )

    backend_config = config.get(backend, {})
    if backend == "deepseek":
        from src.aicomic.llm.deepseek import DeepSeekClient
        return DeepSeekClient(
            api_key=api_key,
            model=backend_config.get("model", "deepseek-chat"),
            base_url=backend_config.get("base_url", "https://api.deepseek.com"),
        )
    elif backend == "claude":
        from src.aicomic.llm.claude import ClaudeClient
        return ClaudeClient(
            api_key=api_key,
            model=backend_config.get("model", "claude-sonnet-5-20251001"),
        )
    else:
        raise RuntimeError(f"Unknown backend: {backend}")


@app.get("/api/health")
async def health():
    orchestrator_ready = getattr(app.state, "pipeline_runner", None) is not None
    return {
        "status": "ok",
        "version": "0.1.0",
        "orchestrator_ready": orchestrator_ready,
    }


# ── SSE 事件流端点 ──
@app.get("/api/events/{task_id}")
async def event_stream(task_id: str, request: Request):
    """SSE 端点 — 客户端 EventSource 连接到此获取实时进度."""
    from server.events import EventManager
    event_mgr: EventManager = app.state.event_mgr

    async def generate():
        async for evt in event_mgr.subscribe(task_id):
            if await request.is_disconnected():
                break
            yield event_mgr.to_sse(evt)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 注册 API 路由 ──
from server.api import pipeline as pipeline_api
from server.api import agents as agents_api
from server.api import library as library_api
from server.api import videos as videos_api

app.include_router(pipeline_api.router)
app.include_router(agents_api.router)
app.include_router(library_api.router)
app.include_router(videos_api.router)


# ── Startup: 初始化所有依赖并注入到 api 模块 ──
@app.on_event("startup")
def on_startup():
    from server.events import EventManager
    from server.db import TaskStore, init_schema
    from server.runner import PipelineRunner, AgentRunner

    # 1. 初始化数据库新表
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    # 2. 初始化基础组件
    event_mgr = EventManager()
    task_store = TaskStore(conn)
    app.state.conn = conn
    app.state.event_mgr = event_mgr
    app.state.task_store = task_store

    # 3. 注入到 api 模块 (基础组件)
    pipeline_api.event_mgr = event_mgr
    pipeline_api.task_store = task_store
    agents_api.event_mgr = event_mgr
    agents_api.task_store = task_store

    # 4. 尝试初始化 Orchestrator + Runners
    try:
        config = _load_config()

        from src.aicomic.db.repository import Database as AICDB
        from src.aicomic.bus import AgentBus
        from src.aicomic.agents.scriptwriter import ScriptwriterAgent
        from src.aicomic.agents.screenwriter import ScreenwriterAgent
        from src.aicomic.agents.char_designer import CharacterDesignerAgent
        from src.aicomic.agents.scene_designer import SceneDesignerAgent
        from src.aicomic.agents.shot_visualizer import ShotVisualizerAgent
        from src.aicomic.agents.image_generator import ImageGeneratorAgent
        from src.aicomic.agents.shot_video_generator import ShotVideoGeneratorAgent
        from src.aicomic.agents.outfit_manager import OutfitManagerAgent
        from src.aicomic.agents.video_generator import VideoGeneratorAgent
        from src.aicomic.agents.video_composer import VideoComposerAgent
        from src.aicomic.doubao.client import MockVideoGenerator, DoubaoVideoGenerator
        from src.aicomic.doubao.browser import DoubaoBrowserClient
        from src.aicomic.orchestrator import Orchestrator

        # 构建 LLM 客户端
        llm = _build_llm_client(config)

        # 注册所有 Agent
        bus = AgentBus()
        bus.register(ScriptwriterAgent(llm_client=llm))
        bus.register(ScreenwriterAgent(llm_client=llm))
        bus.register(CharacterDesignerAgent(llm_client=llm))
        bus.register(SceneDesignerAgent(llm_client=llm))
        bus.register(ShotVisualizerAgent(llm_client=llm))
        bus.register(OutfitManagerAgent(llm_client=llm))

        # Image Generator (with browser)
        doubao_cfg = config.get("doubao", {})
        browser_client = DoubaoBrowserClient(
            state_file=Path(doubao_cfg.get("state_file", "data/doubao_state.json")),
            cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
            headless=doubao_cfg.get("headless", True),
            output_dir=doubao_cfg.get("output_dir", "data/"),
            timeout_sec=doubao_cfg.get("timeout_sec", 300),
            poll_interval_sec=doubao_cfg.get("poll_interval_sec", 3),
            rate_limit_sec=doubao_cfg.get("rate_limit_sec", 10),
            selectors=doubao_cfg.get("selectors", {}),
        )
        pages_cfg = doubao_cfg.get("pages", {})
        if pages_cfg:
            browser_client.page_urls.update(pages_cfg)

        bus.register(ImageGeneratorAgent(browser_client=browser_client))

        # Video Generator (根据 backend 选择)
        video_cfg = config.get("video", {})
        video_output_dir = video_cfg.get("output_dir", "data/videos")
        video_backend = video_cfg.get("generator", "mock")
        if video_backend == "doubao":
            # ShotVideoGenerator 在 doubao 图片页上贴参考图 + 视频提示词
            shot_duration = float(video_cfg.get("shot_video_duration_sec", 5))
            bus.register(ShotVideoGeneratorAgent(
                browser_client=browser_client,
                duration_sec=shot_duration,
            ))
        else:
            video_gen = MockVideoGenerator(output_dir=Path(video_output_dir))
            bus.register(VideoGeneratorAgent(llm_client=llm, video_generator=video_gen))
            bus.register(ShotVideoGeneratorAgent(browser_client=browser_client))

        # Video Composer
        composer_output_dir = video_cfg.get("composer_output_dir", "data/videos")
        bus.register(VideoComposerAgent(output_dir=composer_output_dir))

        # 连接数据库
        db = AICDB(DB_PATH)
        db.connect()

        orchestrator = Orchestrator(bus, db)

        pipeline_runner = PipelineRunner(orchestrator, event_mgr, task_store, DB_PATH)
        agent_runner = AgentRunner(bus, event_mgr, task_store)

        app.state.pipeline_runner = pipeline_runner
        app.state.agent_runner = agent_runner
        app.state.orchestrator_db = db
        app.state.agent_bus = bus

        pipeline_api.pipeline_runner = pipeline_runner
        agents_api.agent_runner = agent_runner

        logger.info("Orchestrator + Runners initialized successfully")
    except Exception as e:
        logger.warning("Orchestrator/Runners NOT initialized: %s", e)
        app.state.pipeline_runner = None
        app.state.agent_runner = None
        pipeline_api.pipeline_runner = None
        agents_api.agent_runner = None


@app.on_event("shutdown")
def on_shutdown():
    conn = getattr(app.state, "conn", None)
    if conn:
        conn.close()
    orch_db = getattr(app.state, "orchestrator_db", None)
    if orch_db:
        orch_db.close()


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
