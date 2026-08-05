"""Pipeline 端点 — 全链路触发."""
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# 由 main.py 在 startup 时注入
event_mgr = None
task_store = None
pipeline_runner = None


@router.post("/run")
async def run_pipeline(chapter_id: int, with_images: bool = False,
                       with_video: bool = False, background_tasks: BackgroundTasks = None):
    """启动全链路生成."""
    if pipeline_runner is None:
        raise HTTPException(503, "Pipeline runner not initialized — check API key and config")

    tid = task_store.create("pipeline", chapter_id=chapter_id,
        params=json.dumps({"with_images": with_images, "with_video": with_video}))

    if background_tasks:
        background_tasks.add_task(
            pipeline_runner.run_in_background,
            chapter_id, "", with_images, with_video, tid,
        )

    return {"task_id": tid, "events_url": f"/api/events/{tid}"}


@router.post("/cancel")
async def cancel_pipeline(task_id: str):
    """取消运行中的 pipeline."""
    pipeline_runner.cancel(task_id)
    return {"status": "cancelled"}
