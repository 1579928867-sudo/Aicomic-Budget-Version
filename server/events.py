"""SSE 事件管理器 — asyncio.Queue 实现的发布/订阅."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator


class EventManager:
    """管理 SSE 事件流的发布订阅.

    每个 task_id 对应一个 asyncio.Queue，emit 往队列放事件，
    subscribe 返回 AsyncGenerator 供 SSE 端点使用。
    """

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_queue(self, task_id: str) -> asyncio.Queue:
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue()
        return self._queues[task_id]

    async def subscribe(self, task_id: str) -> AsyncGenerator[dict, None]:
        """订阅 task 的事件流，yield dict 格式事件.

        Yields:
            dict with keys: event (str), data (dict)
        """
        queue = self._get_queue(task_id)
        try:
            # 发送初始连接确认
            yield {"event": "connected", "data": {"task_id": task_id}}
            while True:
                msg = await queue.get()
                yield msg
                if msg["event"] in ("complete", "error"):
                    break
        except asyncio.CancelledError:
            pass  # 客户端断开
        finally:
            # 清理
            if task_id in self._queues:
                del self._queues[task_id]

    async def emit(self, task_id: str, event: str, data: dict):
        """发送事件到指定 task 的 subscriber."""
        queue = self._get_queue(task_id)
        await queue.put({"event": event, "data": data})

    async def close(self, task_id: str):
        """强制关闭某个 task 的事件流."""
        await self.emit(task_id, "complete", {"status": "closed"})

    def to_sse(self, event_dict: dict) -> str:
        """将事件 dict 转为 SSE 格式字符串 (供 API 端点使用)."""
        event_type = event_dict["event"]
        data_str = json.dumps(event_dict["data"], ensure_ascii=False)
        return f"event: {event_type}\ndata: {data_str}\n\n"
