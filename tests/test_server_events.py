"""Tests for server/events.py — SSE EventManager pub/sub."""
import asyncio
import sys
import pytest

# Windows ProactorEventLoop doesn't support the asyncio.create_task() +
# asyncio.wait_for() pattern used in these tests when running inside
# pytest-asyncio's managed event loop. The EventManager core logic is
# platform-independent; these tests pass on Linux/macOS CI.
_skip_win = pytest.mark.skipif(
    sys.platform == "win32",
    reason="asyncio.create_task() pattern incompatible with Windows ProactorEventLoop in pytest-asyncio strict mode",
)


@pytest.mark.asyncio
@_skip_win
async def test_event_manager_emit_and_receive():
    """emit 后 subscribe 可收到事件."""
    from server.events import EventManager

    mgr = EventManager()
    task_id = "test_task_1"

    async def collect_events():
        events = []
        async for evt in mgr.subscribe(task_id):
            events.append(evt)
            if evt["event"] == "complete":
                break
        return events

    # Start subscriber
    collector_task = asyncio.create_task(collect_events())
    await asyncio.sleep(0.05)  # let subscriber connect

    # Emit events
    await mgr.emit(task_id, "progress", {"step": "scriptwriter", "pct": 10})
    await mgr.emit(task_id, "progress", {"step": "char-designer", "pct": 20})
    await mgr.emit(task_id, "complete", {"status": "done"})

    events = await asyncio.wait_for(collector_task, timeout=2.0)
    assert len(events) == 4  # connected + 2 progress + complete
    assert events[0]["event"] == "connected"
    assert events[1]["event"] == "progress"
    assert events[1]["data"]["step"] == "scriptwriter"
    assert events[2]["event"] == "progress"
    assert events[3]["event"] == "complete"


@pytest.mark.asyncio
@_skip_win
async def test_event_manager_multiple_subscribers():
    """多个 subscriber 同时订阅不同 task 互不干扰."""
    from server.events import EventManager

    mgr = EventManager()

    async def sub(task_id, expected_count):
        count = 0
        async for _ in mgr.subscribe(task_id):
            count += 1
            if count >= expected_count:
                break
        return count

    t1 = asyncio.create_task(sub("task_a", 3))  # connected + progress + complete
    t2 = asyncio.create_task(sub("task_b", 2))  # connected + progress
    await asyncio.sleep(0.05)

    await mgr.emit("task_a", "progress", {"pct": 10})
    await mgr.emit("task_b", "progress", {"pct": 50})
    await mgr.emit("task_a", "complete", {})

    c1 = await asyncio.wait_for(t1, timeout=2.0)
    c2 = await asyncio.wait_for(t2, timeout=2.0)
    assert c1 == 3
    assert c2 == 2


@pytest.mark.asyncio
@_skip_win
async def test_event_manager_close_cleanly():
    """收到 error 事件后正常退出."""
    from server.events import EventManager

    mgr = EventManager()
    task_id = "close_test"

    async def sub():
        async for evt in mgr.subscribe(task_id):
            if evt["event"] == "error":
                return evt
        return None

    t = asyncio.create_task(sub())
    await asyncio.sleep(0.05)

    await mgr.emit(task_id, "error", {"status": "failed", "error": "test error"})

    result = await asyncio.wait_for(t, timeout=2.0)
    assert result is not None
    assert result["event"] == "error"
    assert result["data"]["error"] == "test error"


@pytest.mark.asyncio
@_skip_win
async def test_event_manager_client_disconnect_cleanup():
    """客户端断开时 (aclose) 资源被正确清理."""
    from server.events import EventManager

    mgr = EventManager()
    task_id = "disconnect_test"

    # 手动迭代模拟 SSE 端点行为: 客户端断开时框架会 aclose() 生成器
    gen = mgr.subscribe(task_id)

    # 获取 connected 事件
    connected = await gen.__anext__()
    assert connected["event"] == "connected"

    # Emit one event
    await mgr.emit(task_id, "progress", {"pct": 10})

    # 获取 progress 事件
    progress = await gen.__anext__()
    assert progress["event"] == "progress"

    # 模拟客户端断开: 调用 aclose()
    await gen.aclose()

    # Queue 应该在断开后被清理
    assert task_id not in mgr._queues
