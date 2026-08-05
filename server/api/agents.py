"""单 Agent 调用端点 — 素材库重新生成."""
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter(prefix="/api/agents", tags=["agents"])

event_mgr = None
task_store = None
agent_runner = None


@router.post("/run")
async def run_agent(agent: str, target_type: str, target_id: int,
                    extra: str = "", chapter_id: int = 0,
                    background_tasks: BackgroundTasks = None):
    """触发单个 Agent (image-generator / char-designer / scene-designer / shot-video-generator)."""
    if agent_runner is None:
        raise HTTPException(503, "Agent runner not initialized — check API key and config")

    VALID_AGENTS = {"image-generator", "char-designer", "scene-designer", "shot-video-generator"}
    if agent not in VALID_AGENTS:
        raise HTTPException(400, f"Invalid agent: {agent}. Must be one of {VALID_AGENTS}")

    input_data = {
        "chapter_id": chapter_id,
        "target_type": target_type,
        "target_id": target_id,
        "extra": extra,
    }
    tid = task_store.create("agent", chapter_id=chapter_id,
        params=json.dumps({"agent": agent, **input_data}))

    if background_tasks:
        background_tasks.add_task(agent_runner.run_in_background, agent, input_data, tid)

    return {"task_id": tid, "events_url": f"/api/events/{tid}"}
