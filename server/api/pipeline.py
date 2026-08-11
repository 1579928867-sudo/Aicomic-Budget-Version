"""Pipeline 端点 — 全链路触发."""
import json
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# 由 main.py 在 startup 时注入
event_mgr = None
task_store = None
pipeline_runner = None


class PipelineRunBody(BaseModel):
    chapter_id: int
    with_images: bool = True
    with_video: bool = True
    mode: str = "interactive"  # "interactive" | "auto"


class PipelineContinueBody(BaseModel):
    task_id: str


class PipelineCancelBody(BaseModel):
    task_id: str


@router.post("/run")
async def run_pipeline(body: PipelineRunBody, background_tasks: BackgroundTasks = None):
    """启动全链路生成.

    mode='interactive': 分 3 阶段，每阶段完成后暂停等待用户确认
    mode='auto': 一口气跑完，每阶段仅汇报不暂停
    """
    if pipeline_runner is None:
        raise HTTPException(503, "Pipeline runner not initialized — check API key and config")

    mode = body.mode if body.mode in ("interactive", "auto") else "interactive"
    tid = task_store.create("pipeline", chapter_id=body.chapter_id,
        params=json.dumps({"with_images": body.with_images, "with_video": body.with_video, "mode": mode}))

    if background_tasks:
        background_tasks.add_task(
            pipeline_runner.run_in_background,
            body.chapter_id, "", body.with_images, body.with_video, tid, mode,
        )

    return {"task_id": tid, "events_url": f"/api/events/{tid}", "mode": mode}


@router.post("/continue")
async def continue_pipeline(body: PipelineContinueBody, background_tasks: BackgroundTasks = None):
    """继续下一阶段 (interactive 模式专用)."""
    if pipeline_runner is None:
        raise HTTPException(503, "Pipeline runner not initialized")

    task = task_store.get(body.task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] != "awaiting_continue":
        raise HTTPException(400, f"Task is {task['status']}, not awaiting continue")

    if background_tasks:
        background_tasks.add_task(pipeline_runner.continue_phase, body.task_id)

    return {"status": "continuing", "task_id": body.task_id}


@router.post("/cancel")
async def cancel_pipeline(body: PipelineCancelBody):
    """取消运行中的 pipeline."""
    pipeline_runner.cancel(body.task_id)
    return {"status": "cancelled"}
