"""任务中心端点 — 查看、取消、重试任务."""
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("")
def list_tasks(limit: int = 50):
    """所有任务列表."""
    from server.db import TaskStore
    conn = _get_conn()
    try:
        store = TaskStore(conn)
        tasks = store.list_all(limit=limit)
        return [dict(t) for t in tasks]
    finally:
        conn.close()


@router.get("/{task_id}")
def get_task(task_id: str):
    """单个任务详情."""
    from server.db import TaskStore
    conn = _get_conn()
    try:
        store = TaskStore(conn)
        task = store.get(task_id)
        if not task:
            raise HTTPException(404, f"Task '{task_id}' not found")
        return dict(task)
    finally:
        conn.close()


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    """取消运行中的任务."""
    from server.db import TaskStore
    conn = _get_conn()
    try:
        store = TaskStore(conn)
        task = store.get(task_id)
        if not task:
            raise HTTPException(404, f"Task '{task_id}' not found")

        if task["status"] not in ("pending", "running"):
            raise HTTPException(400, f"Task '{task_id}' is {task['status']}, cannot cancel")

        # 通知 PipelineRunner 取消
        try:
            from server.main import app
            runner = getattr(app.state, "pipeline_runner", None)
            if runner:
                runner.cancel(task_id)
        except Exception:
            pass

        store.update(task_id, status="cancelled")
        return {"status": "cancelled", "task_id": task_id}
    finally:
        conn.close()


@router.post("/{task_id}/retry")
def retry_task(task_id: str):
    """重试失败的任务."""
    from server.db import TaskStore
    conn = _get_conn()
    try:
        store = TaskStore(conn)
        task = store.get(task_id)
        if not task:
            raise HTTPException(404, f"Task '{task_id}' not found")

        if task["status"] not in ("failed", "cancelled"):
            raise HTTPException(400, f"Task '{task_id}' is {task['status']}, can only retry failed/cancelled")

        # 创建新任务 (保留原参数)
        params = task.get("params", "{}")
        new_tid = store.create(
            type_=task["type"],
            chapter_id=task["chapter_id"],
            params=params,
        )

        return {
            "status": "retrying",
            "original_task_id": task_id,
            "new_task_id": new_tid,
            "events_url": f"/api/events/{new_tid}",
        }
    finally:
        conn.close()
