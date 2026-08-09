"""FastAPI application entry point."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from server.config import load_config, build_llm_client

logger = logging.getLogger("aicomic-server")

app = FastAPI(title="AI漫剧", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

DB_PATH = Path("data/aicomic.db")


@app.get("/api/health")
async def health():
    orchestrator_ready = getattr(app.state, "pipeline_runner", None) is not None
    return {"status": "ok", "version": "0.2.0", "orchestrator_ready": orchestrator_ready}


@app.get("/api/events/{task_id}")
async def event_stream(task_id: str, request: Request):
    from server.events import EventManager
    event_mgr: EventManager = app.state.event_mgr

    async def generate():
        async for evt in event_mgr.subscribe(task_id):
            if await request.is_disconnected(): break
            yield event_mgr.to_sse(evt)

    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


# ── 路由 ──
from server.api import pipeline as pipeline_api, agents as agents_api
from server.api import library as library_api, videos as videos_api
from server.api import chat as chat_api, settings as settings_api, tasks as tasks_api

app.include_router(pipeline_api.router)
app.include_router(agents_api.router)
app.include_router(library_api.router)
app.include_router(videos_api.router)
app.include_router(chat_api.router)
app.include_router(settings_api.router)
app.include_router(tasks_api.router)


def init_orchestrator():
    """初始化/重新初始化 orchestrator + runners。返回 (ok, error_msg)。"""
    from server.events import EventManager
    from server.db import TaskStore, get_db
    from server.runner import PipelineRunner, AgentRunner

    # 关闭旧的 db 连接（如果有）
    old_db = getattr(app.state, "orchestrator_db", None)
    if old_db:
        try: old_db.close()
        except Exception: pass

    event_mgr: EventManager = app.state.event_mgr
    task_store: TaskStore = app.state.task_store

    try:
        config = load_config()

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

        llm = build_llm_client(config)
        bus = AgentBus()
        bus.register(ScriptwriterAgent(llm_client=llm))
        bus.register(ScreenwriterAgent(llm_client=llm))
        bus.register(CharacterDesignerAgent(llm_client=llm))
        bus.register(SceneDesignerAgent(llm_client=llm))
        bus.register(ShotVisualizerAgent(llm_client=llm))
        bus.register(OutfitManagerAgent(llm_client=llm))

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
        if pages_cfg: browser_client.page_urls.update(pages_cfg)
        bus.register(ImageGeneratorAgent(browser_client=browser_client))

        video_cfg = config.get("video", {})
        video_output_dir = video_cfg.get("output_dir", "data/videos")
        video_backend = video_cfg.get("generator", "mock")
        if video_backend == "doubao":
            shot_duration = float(video_cfg.get("shot_video_duration_sec", 5))
            bus.register(ShotVideoGeneratorAgent(browser_client=browser_client, duration_sec=shot_duration))
        else:
            video_gen = MockVideoGenerator(output_dir=Path(video_output_dir))
            bus.register(VideoGeneratorAgent(llm_client=llm, video_generator=video_gen))
            bus.register(ShotVideoGeneratorAgent(browser_client=browser_client))
        composer_output_dir = video_cfg.get("composer_output_dir", "data/videos")
        bus.register(VideoComposerAgent(output_dir=composer_output_dir))

        db = AICDB(DB_PATH)
        db.connect()
        db.init_schema()
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
        return True, None
    except Exception as e:
        logger.warning("Orchestrator/Runners NOT initialized: %s", e)
        app.state.pipeline_runner = None
        app.state.agent_runner = None
        pipeline_api.pipeline_runner = None
        agents_api.agent_runner = None
        return False, str(e)


@app.on_event("startup")
def on_startup():
    # Windows GBK 编码修复 — 必须在任何 print() 之前
    import sys as _sys
    if _sys.platform == "win32":
        try:
            _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    from server.events import EventManager
    from server.db import TaskStore, init_schema, deduplicate_novels, get_db

    conn = get_db(DB_PATH)
    init_schema(conn)

    # 确保核心表存在（空库首次启动时 init_schema 只建 web 层表）
    from src.aicomic.db.repository import Database as _AICDB
    _core_db = _AICDB(DB_PATH)
    _core_db.connect()
    _core_db.init_schema()
    _core_db.close()

    # 修复脏数据: 合并重名 novel
    merged = deduplicate_novels(conn)
    if merged:
        logger.info("Cleaned up %d duplicate novel(s)", merged)

    event_mgr = EventManager()
    task_store = TaskStore(conn)
    app.state.conn = conn
    app.state.event_mgr = event_mgr
    app.state.task_store = task_store

    pipeline_api.event_mgr = event_mgr
    pipeline_api.task_store = task_store
    agents_api.event_mgr = event_mgr
    agents_api.task_store = task_store

    init_orchestrator()


@app.on_event("shutdown")
def on_shutdown():
    conn = getattr(app.state, "conn", None)
    if conn: conn.close()
    orch_db = getattr(app.state, "orchestrator_db", None)
    if orch_db: orch_db.close()


# ── 素材图片静态服务（必须在 / 之前注册）──
data_dir = Path("data")
if data_dir.exists():
    app.mount("/data", StaticFiles(directory=str(data_dir)), name="data")

# ── 前端静态文件 + SPA fallback ──
# 不挂载 "/" StaticFiles，因为会拦截 API 路由。改用自定义 catch-all。
static_dir = Path(__file__).parent / "static"
_static_ready = static_dir.exists() and any(static_dir.iterdir())

if _static_ready:
    from fastapi.responses import FileResponse, HTMLResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        # 尝试匹配静态文件
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback — 每次请求重新读 index.html（避免 rebuild 后缓存过期）
        index_path = static_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>Frontend not built — run: cd web && npm run build</h1>")
else:
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend_no_build(full_path: str):
        return {"error": "frontend not built — run: cd web && npm run build"}



def main():
    import os as _os
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    _reload = _os.environ.get("AICOMIC_RELOAD", "").lower() not in ("0", "false", "no")
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=_reload)


if __name__ == "__main__":
    main()
