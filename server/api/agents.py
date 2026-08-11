"""单 Agent 调用端点 — 素材库重新生成."""
import json
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException
from server.db import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"])

event_mgr = None
task_store = None
agent_runner = None


class AgentRunBody(BaseModel):
    agent: str
    target_type: str
    target_id: int
    extra: str = ""
    chapter_id: int = 0
    shot_num: int = 0  # only for shot-video-generator


@router.post("/run")
async def run_agent(body: AgentRunBody, background_tasks: BackgroundTasks = None):
    """触发单个 Agent (image-generator / char-designer / scene-designer / shot-video-generator)."""
    if agent_runner is None:
        raise HTTPException(503, "Agent runner not initialized — check API key and config")

    VALID_AGENTS = {"image-generator", "char-designer", "scene-designer", "shot-video-generator", "video-composer"}
    if body.agent not in VALID_AGENTS:
        raise HTTPException(400, f"Invalid agent: {body.agent}. Must be one of {VALID_AGENTS}")

    input_data = {
        "chapter_id": body.chapter_id,
        "target_type": body.target_type,
        "target_id": body.target_id,
        "extra": body.extra,
    }
    # video-composer / shot-video-generator need script_id resolved from chapter_id
    if body.agent in ("video-composer", "shot-video-generator") and body.chapter_id:
        conn = get_db()
        row = conn.execute(
            "SELECT id FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
            (body.chapter_id,),
        ).fetchone()
        conn.close()
        if row:
            input_data["script_id"] = row["id"]
    # shot-video-generator: single shot retry — pass shot_num, no clip limit
    if body.agent == "shot-video-generator":
        if body.shot_num:
            input_data["shot_num"] = body.shot_num
        input_data["max_clips_per_run"] = 0
    # char-designer needs raw_text + characters list — resolve from chapter
    if body.agent == "char-designer" and body.chapter_id:
        conn = get_db()
        ch = conn.execute("SELECT raw_text FROM chapter WHERE id=?", (body.chapter_id,)).fetchone()
        if not ch or not (ch["raw_text"] or "").strip():
            conn.close()
            raise HTTPException(400, "Chapter has no text — upload the chapter file first")
        raw_text = ch["raw_text"]
        # Resolve character name from target_id
        char_row = conn.execute("SELECT name FROM character_card WHERE id=?", (body.target_id,)).fetchone()
        conn.close()
        if char_row:
            input_data = {
                "chapter_id": body.chapter_id,
                "raw_text": raw_text,
                "characters": [char_row["name"]],
                "force": True,  # bypass idempotency — always re-run for single-char regen
            }
        else:
            input_data = {
                "chapter_id": body.chapter_id,
                "raw_text": raw_text,
                "characters": [],
                "force": True,
            }
    tid = task_store.create("agent", chapter_id=body.chapter_id,
        params=json.dumps({"agent": body.agent, **input_data}))

    if background_tasks:
        background_tasks.add_task(agent_runner.run_in_background, body.agent, input_data, tid)

    return {"task_id": tid, "events_url": f"/api/events/{tid}"}
