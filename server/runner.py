"""后台任务执行器 — 在 FastAPI BackgroundTasks 中运行 Pipeline/Agent."""
from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from typing import Any

from .events import EventManager
from .db import TaskStore


class InterruptedError(Exception):
    """任务被用户取消."""


class PipelineRunner:
    """在后台运行 Orchestrator.run_chapter(), emit SSE 进度事件."""

    def __init__(self, orchestrator, event_mgr: EventManager, task_store: TaskStore,
                 db_path: Path = Path("data/aicomic.db")):
        self.orchestrator = orchestrator
        self.event_mgr = event_mgr
        self.task_store = task_store
        self.db_path = db_path
        self._cancel_flags: dict[str, bool] = {}

    async def run_in_background(
        self, chapter_id: int, raw_text: str = "",
        with_images: bool = False, with_video: bool = False,
        task_id: str = "",
    ):
        """在后台线程中运行 pipeline，通过 SSE 推送每个 Agent 的进度."""
        self._cancel_flags[task_id] = False
        self.task_store.update(task_id, status="running")

        # 定义每个 step 的进度权重
        STEPS = [
            ("scriptwriter", 10), ("char-designer", 15), ("scene-designer", 15),
            ("outfit-manager", 5), ("storyboard-agent", 10), ("image-generator", 15),
            ("shot-visualizer", 10), ("shot-video-generator", 15), ("video-composer", 5),
        ]

        # ── 通过 monkey-patch db.log 拦截进度 ──
        original_log = self.orchestrator.db.log

        def progress_log(agent_name, ch_id, event, detail=None, level="INFO"):
            original_log(agent_name, ch_id, event, detail, level)
            # ── 取消检查 ──
            if self._cancel_flags.get(task_id, False):
                raise InterruptedError(f"Task {task_id} cancelled by user")

        self.orchestrator.db.log = progress_log

        try:
            total_pct = 0
            for step_name, step_weight in STEPS:
                if self._cancel_flags.get(task_id, False):
                    raise InterruptedError(f"Task {task_id} cancelled")

                await self.event_mgr.emit(task_id, "progress", {
                    "step": step_name, "status": "running",
                    "pct": total_pct, "message": f"正在运行 {step_name}...",
                })
                total_pct += step_weight

            # ── 在 executor 中同步运行 orchestrator ──
            from concurrent.futures import ThreadPoolExecutor
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = await loop.run_in_executor(
                    pool,
                    lambda: self.orchestrator.run_chapter(
                        chapter_id, raw_text,
                        with_video=with_video, with_images=with_images,
                    )
                )

            # ── 恢复原始 log ──
            self.orchestrator.db.log = original_log

            if result.success:
                self.task_store.update(task_id, status="done", progress=1.0,
                    result=f'{{"final_video": "{result.data.get("final_video_path", "")}"}}')
                await self.event_mgr.emit(task_id, "complete", {
                    "status": "done",
                    "data": result.data,
                })
            else:
                self.task_store.update(task_id, status="failed", error=result.error or "unknown")
                await self.event_mgr.emit(task_id, "error", {
                    "status": "failed", "error": result.error or "unknown",
                })
        except InterruptedError:
            self.task_store.update(task_id, status="cancelled")
            await self.event_mgr.emit(task_id, "error", {
                "status": "cancelled", "error": "用户取消",
            })
        except Exception as e:
            self.task_store.update(task_id, status="failed", error=str(e))
            await self.event_mgr.emit(task_id, "error", {
                "status": "failed", "error": str(e),
            })
        finally:
            self.orchestrator.db.log = original_log
            self._cancel_flags.pop(task_id, None)

    def cancel(self, task_id: str):
        """设置取消标志，后台任务检测到后会抛出 InterruptedError."""
        self._cancel_flags[task_id] = True


class AgentRunner:
    """在后台运行单个 Agent (用于素材库的"重新生成"按钮)."""

    def __init__(self, bus, event_mgr: EventManager, task_store: TaskStore):
        self.bus = bus
        self.event_mgr = event_mgr
        self.task_store = task_store

    async def run_in_background(self, agent_name: str, input_data: dict, task_id: str):
        """在后台线程中运行单个 Agent."""
        self.task_store.update(task_id, status="running")

        await self.event_mgr.emit(task_id, "progress", {
            "step": agent_name, "status": "running", "pct": 0,
            "message": f"正在运行 {agent_name}...",
        })

        try:
            from concurrent.futures import ThreadPoolExecutor
            from src.aicomic.db.repository import Database as AICDB

            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = await loop.run_in_executor(
                    pool,
                    lambda: self.bus.run(agent_name, input_data, AICDB(Path("data/aicomic.db"))),
                )

            if result.success:
                self.task_store.update(task_id, status="done", progress=1.0)
                await self.event_mgr.emit(task_id, "complete", {
                    "status": "done", "data": result.data,
                })
            else:
                self.task_store.update(task_id, status="failed", error=result.error or "unknown")
                await self.event_mgr.emit(task_id, "error", {
                    "status": "failed", "error": result.error or "unknown",
                })
        except Exception as e:
            self.task_store.update(task_id, status="failed", error=str(e))
            await self.event_mgr.emit(task_id, "error", {
                "status": "failed", "error": str(e),
            })
