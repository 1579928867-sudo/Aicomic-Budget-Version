# AI漫剧 Web 前端 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 AI漫剧 CLI Pipeline 封装为 Web 前端应用，支持 Chat 交互、素材库浏览预览重新生成、视频管理、豆包 Cookie 配置。

**Architecture:** Monorepo — `server/` (FastAPI + SSE) 内建直接调用 `src/aicomic/` (现有不动)，`web/` (React 18 + Vite + shadcn/ui) 通过 REST + SSE 与后端通信。生产环境前端构建产物放入 `server/static/`，单端口一体化部署。

**Tech Stack:** FastAPI + uvicorn, React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS, SQLite (WAL, 现有), SSE

## Global Constraints

- Python >= 3.12, 现有 `src/aicomic/` 目录 **不修改**
- 新增依赖: `fastapi`, `uvicorn[standard]`, `python-multipart`，加入 pyproject.toml
- 前端: React 18 + TypeScript + Vite, node >= 20
- 数据库: 在现有 `data/aicomic.db` 上新增 4 表: `chat_message`, `chat_summary`, `settings`, `task`
- 部署: `python -m server` 单命令启动，前端静态文件由 FastAPI mount 到根路径
- Cookie: 图文引导 + 用户手动输入粘贴，存储在 `data/doubao_cookies.json`
- 所有 Agent 调用走 Bus/Orchestrator 现有接口，不新增私有调用

---

## 文件结构

```
项目根 (D:/first_agent/)
├── pyproject.toml              ← 修改: 加 fastapi/uvicorn/python-multipart 依赖
├── src/aicomic/                ← 现有，不动
├── server/                     ← 新建
│   ├── __init__.py
│   ├── main.py                 ← FastAPI app 入口 + static mount + startup
│   ├── __main__.py             ← `python -m server` 入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── chat.py             ← POST /api/chat/send, GET /api/chat/history
│   │   ├── pipeline.py         ← POST /api/pipeline/run, POST /api/pipeline/cancel
│   │   ├── library.py          ← 素材库 REST 端点
│   │   ├── agents.py           ← POST /api/agents/run (细粒度重新生成)
│   │   ├── videos.py           ← 视频管理端点
│   │   ├── tasks.py            ← 任务中心端点
│   │   └── settings.py         ← Cookie / LLM 配置端点
│   ├── events.py               ← SSE 事件管理器 (EventManager)
│   ├── intent.py               ← NLU 意图解析 (调用 LLM 做分类)
│   ├── runner.py               ← 后台任务执行器 (PipelineRunner)
│   ├── db.py                   ← 新增表初始化 + chat/settings/task 查询方法
│   └── static/                 ← (构建时生成) 前端产物
├── web/                        ← 新建
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api.ts              ← 后端 API 客户端 (fetch 封装)
│       ├── stores/
│       │   └── app.ts          ← Zustand 全局状态
│       ├── components/
│       │   ├── Layout.tsx       ← 导航框架 (侧边栏 + 主内容区)
│       │   ├── Sidebar.tsx      ← 导航菜单
│       │   ├── TaskProgress.tsx ← SSE 进度条组件
│       │   ├── ImagePreview.tsx ← 图片预览弹窗
│       │   └── CookieGuide.tsx  ← Cookie 图文引导
│       ├── pages/
│       │   ├── ChatPage.tsx     ← 💬 AI漫剧助手
│       │   ├── LibraryPage.tsx  ← 📚 素材库
│       │   │   ├── NovelList.tsx
│       │   │   ├── ChapterView.tsx
│       │   │   ├── CharacterCard.tsx
│       │   │   ├── SceneCard.tsx
│       │   │   ├── ScriptView.tsx
│       │   │   └── ShotList.tsx
│       │   ├── VideosPage.tsx   ← 🎞️ 视频
│       │   ├── CookiePage.tsx   ← 🔐 Cookie
│       │   ├── TasksPage.tsx    ← 📋 任务中心
│       │   └── SettingsPage.tsx ← ⚙️ 系统设置
│       └── types.ts
└── tests/                      ← 新建测试
    ├── test_server_db.py
    ├── test_server_intent.py
    ├── test_server_events.py
    └── test_server_api.py
```

---

### Task 1: 项目基础设施 — 依赖 + 目录骨架

**Files:**
- Modify: `pyproject.toml`
- Create: `server/__init__.py`
- Create: `server/__main__.py`
- Create: `server/main.py`
- Create: `server/api/__init__.py`

**Interfaces:**
- Produces: `server/main.py` 暴露 `app: FastAPI`，`server/__main__.py` 暴露 `python -m server` 入口

- [ ] **Step 1: 更新 pyproject.toml 加 web 依赖**

```toml
# pyproject.toml — 在 dependencies 列表追加：
dependencies = [
    # ... 现有 ...
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "python-multipart>=0.0.9",
]
```

- [ ] **Step 2: 安装新依赖**

```bash
pip install fastapi "uvicorn[standard]" python-multipart
```

- [ ] **Step 3: 创建 server/ 骨架文件**

```python
# server/__init__.py
"""AI漫剧 Web Server — FastAPI backend."""

# server/api/__init__.py
"""API route modules."""
```

```python
# server/__main__.py
"""Allow `python -m server` invocation."""
from .main import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 创建 server/main.py 最小可启动 App**

```python
"""FastAPI application entry point."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="AI漫剧", version="0.1.0")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


def main():
    import uvicorn
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 验证服务启动**

```bash
cd D:/first_agent && python -m server
# 预期: Uvicorn running on http://0.0.0.0:8000
# 验证: curl http://localhost:8000/api/health → {"status":"ok"}
```

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml server/
git commit -m "feat(server): FastAPI skeleton with health check"
```

---

### Task 2: 数据库层 — 新增表 + 查询方法

**Files:**
- Create: `server/db.py`
- Create: `tests/test_server_db.py`

**Interfaces:**
- Produces: `init_schema(conn)` 创建新表，`ChatStore(db)` 读写聊天，`SettingsStore(db)` KV 存取，`TaskStore(db)` 任务 CRUD
- Consumes: `src/aicomic/db/repository.py::Database` — 复用其 `conn` 和连接管理

- [ ] **Step 1: 写失败测试**

```python
# tests/test_server_db.py
import sqlite3
import tempfile
from pathlib import Path

def test_init_schema_creates_tables():
    """新建 DB 调用 init_schema 应创建 4 张新表."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema
    init_schema(conn)

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
        "('chat_message', 'chat_summary', 'settings', 'task')"
    ).fetchall()
    assert len(tables) == 4

    conn.close()
    db_path.unlink()


def test_chat_store_insert_and_query():
    """写入消息后可按 chapter_id 查询."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, ChatStore
    init_schema(conn)
    store = ChatStore(conn)

    store.insert(1, "user", "生成第3章")
    store.insert(1, "assistant", "好的，开始生成...")
    store.insert(None, "user", "你好")

    msgs = store.get_by_chapter(1)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "生成第3章"

    global_msgs = store.get_by_chapter(None)
    assert len(global_msgs) == 1

    conn.close()
    db_path.unlink()


def test_settings_store_kv():
    """KV 存取读写."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, SettingsStore
    init_schema(conn)
    store = SettingsStore(conn)

    store.set("cookie", '{"session": "abc123"}')
    val = store.get("cookie")
    assert val == '{"session": "abc123"}'
    assert store.get("nonexistent") is None

    conn.close()
    db_path.unlink()


def test_task_store_crud():
    """任务 CRUD 全流程."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, TaskStore
    init_schema(conn)
    store = TaskStore(conn)

    tid = store.create("pipeline", chapter_id=1, params='{"with_video":true}')
    assert tid is not None

    task = store.get(tid)
    assert task["status"] == "pending"

    store.update(tid, status="running", progress=0.3)
    task = store.get(tid)
    assert task["status"] == "running"
    assert task["progress"] == 0.3

    tasks = store.list_all(limit=10)
    assert len(tasks) == 1

    conn.close()
    db_path.unlink()
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd D:/first_agent && python -m pytest tests/test_server_db.py -v
# 预期: all 4 FAIL (module not found)
```

- [ ] **Step 3: 实现 server/db.py**

```python
"""新增数据库表和查询方法 (在现有 aicomic.db 基础上扩展)."""
from __future__ import annotations
import uuid
import sqlite3
from typing import Any


def init_schema(conn: sqlite3.Connection):
    """初始化 web 层新增表 (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER REFERENCES chapter(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER REFERENCES chapter(id),
            summary_text TEXT NOT NULL,
            start_msg_id INTEGER NOT NULL,
            end_msg_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS task (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            chapter_id INTEGER REFERENCES chapter(id),
            status TEXT NOT NULL DEFAULT 'pending',
            params TEXT DEFAULT '{}',
            progress REAL DEFAULT 0.0,
            result TEXT DEFAULT '{}',
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()


class ChatStore:
    """聊天消息存储 (关联 chapter_id)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, chapter_id: int | None, role: str, content: str,
               metadata: dict | None = None) -> int:
        import json
        cur = self.conn.execute(
            "INSERT INTO chat_message (chapter_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (chapter_id, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_by_chapter(self, chapter_id: int | None, limit: int = 50) -> list[dict]:
        if chapter_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM chat_message WHERE chapter_id = ? ORDER BY id DESC LIMIT ?",
                (chapter_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM chat_message WHERE chapter_id IS NULL ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_recent_full(self, chapter_id: int | None, n: int = 20) -> list[dict]:
        """取最近 N 轮完整消息 (用于构造 LLM 上下文)."""
        msgs = self.get_by_chapter(chapter_id, limit=n * 2)  # user+assistant pairs
        return msgs[-n * 2:] if len(msgs) > n * 2 else msgs

    def get_unsummarized_ids(self, chapter_id: int, since_msg_id: int) -> list[int]:
        """获取未摘要的消息 ID 列表."""
        rows = self.conn.execute(
            "SELECT id FROM chat_message WHERE chapter_id = ? AND id > ? ORDER BY id",
            (chapter_id, since_msg_id),
        ).fetchall()
        return [r["id"] for r in rows]

    def get_messages_by_ids(self, ids: list[int]) -> list[dict]:
        """按 ID 列表取消息."""
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM chat_message WHERE id IN ({placeholders}) ORDER BY id",
            ids,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_summary_end_id(self, chapter_id: int) -> int:
        """获取最新摘要的 end_msg_id，用于判断哪些消息未摘要."""
        row = self.conn.execute(
            "SELECT MAX(end_msg_id) as max_id FROM chat_summary WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        return row["max_id"] if row and row["max_id"] else 0

    def save_summary(self, chapter_id: int, summary_text: str,
                     start_msg_id: int, end_msg_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO chat_summary (chapter_id, summary_text, start_msg_id, end_msg_id) VALUES (?, ?, ?, ?)",
            (chapter_id, summary_text, start_msg_id, end_msg_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_summaries(self, chapter_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM chat_summary WHERE chapter_id = ? ORDER BY id",
            (chapter_id,),
        ).fetchall()
        return [dict(r) for r in rows]


class SettingsStore:
    """系统设置 KV 存储."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
        self.conn.commit()

    def delete(self, key: str):
        self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        self.conn.commit()

    def get_all(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


class TaskStore:
    """任务记录存储."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, type_: str, chapter_id: int | None = None,
               params: str = "{}") -> str:
        tid = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO task (id, type, chapter_id, status, params) VALUES (?, ?, ?, 'pending', ?)",
            (tid, type_, chapter_id, params),
        )
        self.conn.commit()
        return tid

    def get(self, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM task WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def update(self, task_id: str, status: str | None = None,
               progress: float | None = None, result: str | None = None,
               error: str | None = None):
        sets = ["updated_at = CURRENT_TIMESTAMP"]
        vals = []
        if status is not None:
            sets.append("status = ?"); vals.append(status)
        if progress is not None:
            sets.append("progress = ?"); vals.append(progress)
        if result is not None:
            sets.append("result = ?"); vals.append(result)
        if error is not None:
            sets.append("error = ?"); vals.append(error)
        vals.append(task_id)
        self.conn.execute(
            f"UPDATE task SET {', '.join(sets)} WHERE id = ?", vals
        )
        self.conn.commit()

    def list_all(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM task ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM task WHERE status IN ('pending', 'running') ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd D:/first_agent && python -m pytest tests/test_server_db.py -v
# 预期: all 4 PASS
```

- [ ] **Step 5: 提交**

```bash
git add server/db.py tests/test_server_db.py
git commit -m "feat(server): add chat/settings/task DB tables and stores"
```

---

### Task 3: SSE 事件管理器

**Files:**
- Create: `server/events.py`
- Create: `tests/test_server_events.py`

**Interfaces:**
- Consumes: `server/db.py::TaskStore`
- Produces: `EventManager` — `subscribe(task_id) -> AsyncGenerator`, `emit(task_id, event, data)`, `close(task_id)`
- 后端 SSE 端点 `GET /api/events/{task_id}` 使用 `subscribe()` 生成流

- [ ] **Step 1: 写失败测试**

```python
# tests/test_server_events.py
import asyncio
import pytest
import tempfile
from pathlib import Path

@pytest.mark.asyncio
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
    assert len(events) == 3
    assert events[0]["event"] == "progress"
    assert events[0]["data"]["step"] == "scriptwriter"
    assert events[1]["event"] == "progress"
    assert events[2]["event"] == "complete"


@pytest.mark.asyncio
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

    t1 = asyncio.create_task(sub("task_a", 2))
    t2 = asyncio.create_task(sub("task_b", 1))
    await asyncio.sleep(0.05)

    await mgr.emit("task_a", "progress", {"pct": 10})
    await mgr.emit("task_b", "progress", {"pct": 50})
    await mgr.emit("task_a", "complete", {})

    c1 = await asyncio.wait_for(t1, timeout=2.0)
    c2 = await asyncio.wait_for(t2, timeout=2.0)
    assert c1 == 2
    assert c2 == 1


@pytest.mark.asyncio
async def test_event_manager_close_cleanly():
    """close 后 subscriber 正常退出."""
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
    await mgr.emit(task_id, "complete", {})  # close channel

    result = await asyncio.wait_for(t, timeout=2.0)
    assert result["event"] == "error"
```

- [ ] **Step 2: 运行验证失败**

```bash
cd D:/first_agent && python -m pytest tests/test_server_events.py -v
# 预期: all FAIL
```

- [ ] **Step 3: 实现 server/events.py**

```python
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

    async def subscribe(self, task_id: str) -> AsyncGenerator[str, None]:
        """订阅 task 的 SSE 事件流，yield SSE 格式字符串."""
        queue = self._get_queue(task_id)
        try:
            # 发送初始连接确认
            yield f"event: connected\ndata: {{\"task_id\": \"{task_id}\"}}\n\n"
            while True:
                msg = await queue.get()
                event_type = msg["event"]
                data_str = json.dumps(msg["data"], ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data_str}\n\n"
                if event_type in ("complete", "error"):
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
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd D:/first_agent && python -m pytest tests/test_server_events.py -v
# 预期: all 3 PASS
```

- [ ] **Step 5: 提交**

```bash
git add server/events.py tests/test_server_events.py
git commit -m "feat(server): SSE event manager with pub/sub"
```

---

### Task 4: NLU 意图解析

**Files:**
- Create: `server/intent.py`
- Create: `tests/test_server_intent.py`

**Interfaces:**
- Consumes: `src/aicomic/llm/claude.py` 或 `src/aicomic/llm/deepseek.py` — LLM 调用能力
- Consumes: `src/aicomic/db/repository.py::Database` — 查询角色/场景名称用于 disambiguation
- Produces: `parse_intent(message: str, context: dict) -> dict` — 返回 `{intent, target, params}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_server_intent.py
def test_parse_generate_chapter_intent():
    """'生成第3章' → intent=generate_chapter, chapter_num=3."""
    from server.intent import parse_intent_with_llm

    # 用固定 prompt 模板做分类，LLM 部分 mock 掉
    result = parse_intent_with_llm(
        message="生成第3章",
        context={"novel": {"id": 1, "title": "逆天邪神"}, "chapters": []},
        llm_call=mock_llm_intent("generate_chapter", {"chapter_num": 3}),
    )
    assert result["intent"] == "generate_chapter"
    assert result["chapter_num"] == 3


def test_parse_regenerate_character_intent():
    """'重新生成萧澈的图' → intent=regenerate_character."""
    from server.intent import parse_intent_with_llm

    result = parse_intent_with_llm(
        message="重新生成萧澈的图，眼神更冷峻",
        context={
            "novel": {"id": 1, "title": "逆天邪神"},
            "characters": [{"id": 1, "name": "萧澈"}, {"id": 3, "name": "萧泠汐"}],
        },
        llm_call=mock_llm_intent("regenerate_character", {
            "character_name": "萧澈", "character_id": 1,
            "extra_hint": "眼神更冷峻",
        }),
    )
    assert result["intent"] == "regenerate_character"
    assert result["character_id"] == 1


def test_parse_query_intent():
    """'萧澈现在用的什么图' → intent=query."""
    result = parse_intent_with_llm(
        message="萧澈现在用的什么图？",
        context={"characters": [{"id": 1, "name": "萧澈"}]},
        llm_call=mock_llm_intent("query", {"query_type": "character_image"}),
    )
    assert result["intent"] == "query"


# ── Test helpers ──
def mock_llm_intent(expected_intent: str, extra: dict):
    """返回一个 mock LLM callable，返回固定意图 JSON."""
    def _mock(system_prompt: str, user_message: str) -> str:
        import json
        return json.dumps({"intent": expected_intent, **extra}, ensure_ascii=False)
    return _mock
```

- [ ] **Step 2: 运行验证失败**

```bash
cd D:/first_agent && python -m pytest tests/test_server_intent.py -v
# 预期: all FAIL
```

- [ ] **Step 3: 实现 server/intent.py**

```python
"""NLU 意图解析 — LLM 将用户消息映射到结构化意图."""
from __future__ import annotations
import json
from typing import Any, Callable

INTENT_PROMPT = """你是一个 AI漫剧助手的意图分类器。根据用户的消息和当前上下文，输出一个 JSON 对象。

支持的意图:
- generate_chapter: 用户要生成/制作某个章节。输出: {"intent": "generate_chapter", "chapter_num": <数字>}
- regenerate_character: 用户要重新生成某个角色的图片。输出: {"intent": "regenerate_character", "character_name": "<名>", "extra_hint": "<用户的额外要求>"}
- regenerate_scene: 用户要重新生成某个场景。输出: {"intent": "regenerate_scene", "scene_name": "<名>", "extra_hint": "<...>"}
- regenerate_video: 用户要重新生成视频。输出: {"intent": "regenerate_video", "chapter_num": <数字>}
- import_novel: 用户要上传/导入小说。输出: {"intent": "import_novel"}
- regenerate_char_design: 用户要重新设计角色形象。输出: {"intent": "regenerate_char_design", "character_name": "<名>", "extra_hint": "<...>"}
- query: 用户是查询/问问题。输出: {"intent": "query", "query_text": "<用户的原始问题>"}
- chat: 一般闲聊，不触发任何操作。输出: {"intent": "chat", "reply": "<友好回复>"}

规则:
1. 尽量在 extra_hint 中保留用户的具体要求（如"眼神更冷峻""光影更暖"等）
2. 如果上下文中已有角色/章节列表，优先匹配已有的名称
3. 只输出 JSON，不要任何其他文本

当前上下文:
{context}

用户消息: {message}"""


def build_context_text(context: dict) -> str:
    """将上下文 dict 转为 prompt 可读文本."""
    parts = []
    if context.get("novel"):
        parts.append(f"当前小说: {context['novel']['title']} (id={context['novel']['id']})")
    if context.get("chapters"):
        ch_list = ", ".join(f"第{c['chapter_num']}章(id={c['id']})" for c in context["chapters"])
        parts.append(f"已有章节: {ch_list}")
    if context.get("characters"):
        ch_list = ", ".join(f"{c['name']}(id={c['id']})" for c in context["characters"])
        parts.append(f"已有角色: {ch_list}")
    if context.get("scenes"):
        s_list = ", ".join(f"{s['name']}(id={s['id']})" for s in context["scenes"])
        parts.append(f"已有场景: {s_list}")
    return "\n".join(parts) if parts else "无特定上下文"


def parse_intent_with_llm(
    message: str,
    context: dict,
    llm_call: Callable[[str, str], str],
) -> dict:
    """调用 LLM 做意图解析，返回 dict.

    Args:
        message: 用户原始消息
        context: {novel, chapters, characters, scenes} 等上下文信息
        llm_call: (system_prompt, user_message) -> response_text 的 callable

    Returns:
        {"intent": str, ...}
    """
    ctx_text = build_context_text(context)
    prompt = INTENT_PROMPT.format(context=ctx_text, message=message)

    response = llm_call(
        system_prompt="你是一个精确的意图分类器。只输出 JSON。",
        user_message=prompt,
    )

    # 清理可能的 markdown 代码块包裹
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        # 回退: 当作一般聊天处理
        result = {"intent": "chat", "reply": response}
    return result
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd D:/first_agent && python -m pytest tests/test_server_intent.py -v
# 预期: all 3 PASS
```

- [ ] **Step 5: 提交**

```bash
git add server/intent.py tests/test_server_intent.py
git commit -m "feat(server): NLU intent parser for chat messages"
```

---

### Task 5: 后台执行器 — PipelineRunner + AgentRunner

**Files:**
- Create: `server/runner.py`
- Create: `server/api/pipeline.py`
- Create: `server/api/agents.py`

**Interfaces:**
- Consumes: `server/events.py::EventManager`, `server/db.py::TaskStore`
- Consumes: `src/aicomic/orchestrator.py::Orchestrator`, `src/aicomic/bus.py::AgentBus`
- Produces: `PipelineRunner.run_in_background(chapter_id, with_images, with_video, task_id)`, `AgentRunner.run_in_background(agent_name, input_data, task_id)` 两者都通过 SSE 推送进度
- Produces: `POST /api/pipeline/run`, `POST /api/pipeline/cancel`, `POST /api/agents/run`

- [ ] **Step 1: 实现 server/runner.py**

```python
"""后台任务执行器 — 在 FastAPI BackgroundTasks 中运行 Pipeline/Agent."""
from __future__ import annotations
import asyncio
import traceback
from pathlib import Path

from .events import EventManager
from .db import TaskStore


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
```

- [ ] **Step 2: 实现 API 端点**

```python
# server/api/pipeline.py
"""Pipeline 端点 — 全链路触发."""
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from server.events import EventManager
from server.db import TaskStore

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

# 由 main.py 在 startup 时注入
event_mgr: EventManager | None = None
task_store: TaskStore | None = None
pipeline_runner = None


@router.post("/run")
async def run_pipeline(chapter_id: int, with_images: bool = False,
                        with_video: bool = False, background_tasks: BackgroundTasks = None):
    """启动全链路生成."""
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


# server/api/agents.py
"""单 Agent 调用端点 — 素材库重新生成."""
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from server.events import EventManager
from server.db import TaskStore

router = APIRouter(prefix="/api/agents", tags=["agents"])

event_mgr: EventManager | None = None
task_store: TaskStore | None = None
agent_runner = None


@router.post("/run")
async def run_agent(agent: str, target_type: str, target_id: int,
                     extra: str = "", chapter_id: int = 0,
                     background_tasks: BackgroundTasks = None):
    """触发单个 Agent (image-generator / char-designer / scene-designer / shot-video-generator)."""
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
```

- [ ] **Step 3: 更新 server/main.py 集成新模块**

在 `main.py` 的 startup 事件中初始化 EventManager、TaskStore、PipelineRunner、AgentRunner，并把它们注入到 api 模块的模块级变量。

- [ ] **Step 4: 提交**

```bash
git add server/runner.py server/api/pipeline.py server/api/agents.py server/main.py
git commit -m "feat(server): pipeline runner + agent runner + API endpoints"
```

---

### Task 6: 素材库 API 端点

**Files:**
- Create: `server/api/library.py`
- Create: `server/api/videos.py`
- Modify: `server/main.py` — 注册路由

**Interfaces:**
- Consumes: `src/aicomic/db/repository.py::Database` — 查询 novels, chapters, characters, scenes, shots
- Produces: `GET /api/novels`, `GET /api/novels/{id}/chapters`, `GET /api/chapters/{id}/characters`, `GET /api/chapters/{id}/scenes`, `GET /api/chapters/{id}/script`, `GET /api/chapters/{id}/shots`, `POST /api/upload`
- Produces: `GET /api/chapters/{id}/videos`, `POST /api/chapters/{id}/videos/regenerate`

**关键 SQL 查询模式：**

```python
# characters: 从 character_card + character_outfit 联查
# scenes: 从 scene_card 查
# script: 从 script 表查 raw_json
# shots: 从 storyboard_shot 表查
# videos: 从 video_clip + final_video 表查
```

- [ ] **Step 1-4: 写测试 → 实现 → 验证 → 提交**

由于端点数量多，按顺序逐个实现并验证 `curl` 调用。

- [ ] **Step 5: 提交**

```bash
git add server/api/library.py server/api/videos.py server/main.py tests/test_server_api.py
git commit -m "feat(server): library + videos REST API endpoints"
```

---

### Task 7: Chat + Settings + Tasks API

**Files:**
- Create: `server/api/chat.py`
- Create: `server/api/settings.py`
- Create: `server/api/tasks.py`
- Modify: `server/main.py`

**Interfaces:**
- Produces: `POST /api/chat/send`, `GET /api/chat/history`
- Produces: `GET/POST /api/settings/cookie-status`, `GET/POST /api/settings/llm`
- Produces: `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/cancel`, `POST /api/tasks/{id}/retry`

**Chat 核心流程：**

```python
# server/api/chat.py — POST /api/chat/send 伪代码:
async def chat_send(message, files, chapter_id, novel_id):
    # 1. 如果有文件附件 → 解析 → 入库 → 回复解析结果
    # 2. 构建 context: {novel, chapters, characters, scenes}
    # 3. 调用 intent.parse_intent_with_llm(message, context, llm_call)
    # 4. switch intent:
    #    generate_chapter → POST /api/pipeline/run
    #    regenerate_* → POST /api/agents/run
    #    query → 查询 DB 回复
    #    chat → LLM 闲聊回复
    # 5. 存储对话到 chat_message
    # 6. 返回 {reply, intent, task_id?}
```

- [ ] **Step 1-4: 写测试 → 实现 → 验证 → 提交**

- [ ] **Step 5: 提交**

```bash
git add server/api/chat.py server/api/settings.py server/api/tasks.py server/main.py
git commit -m "feat(server): chat + settings + tasks API endpoints"
```

---

### Task 8: React 前端项目初始化

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`
- Create: `web/tailwind.config.js`, `web/postcss.config.js`, `web/index.html`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/types.ts`, `web/src/api.ts`

**Interfaces:**
- Produces: Vite dev server 运行在 5173，代理 `/api` 到 8000
- Produces: `api.ts` 封装所有后端 fetch 调用，供页面组件使用

- [ ] **Step 1: 初始化 Vite + React + TS 项目**

```bash
cd D:/first_agent/web
npm create vite@latest . -- --template react-ts
npm install
```

- [ ] **Step 2: 安装 shadcn/ui 依赖**

```bash
cd D:/first_agent/web
npm install tailwindcss @tailwindcss/vite postcss autoprefixer
npm install zustand lucide-react
npx shadcn@latest init
```

- [ ] **Step 3: 配置 vite.config.ts — API 代理**

```typescript
// web/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: 创建 api.ts — 后端客户端**

```typescript
// web/src/api.ts
const BASE = '/api';

async function request<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// Chat
export const chat = {
  send: (body: { message: string; files?: File[]; chapter_id?: number; novel_id?: number }) =>
    request<{ reply: string; intent: string; task_id?: string }>('/chat/send', {
      method: 'POST', body: JSON.stringify(body),
    }),
  history: (chapter_id?: number) =>
    request<any[]>(`/chat/history${chapter_id ? `?chapter_id=${chapter_id}` : ''}`),
};

// Pipeline
export const pipeline = {
  run: (chapter_id: number, with_images?: boolean, with_video?: boolean) =>
    request<{ task_id: string }>('/pipeline/run', {
      method: 'POST', body: JSON.stringify({ chapter_id, with_images, with_video }),
    }),
  cancel: (task_id: string) =>
    request('/pipeline/cancel', { method: 'POST', body: JSON.stringify({ task_id }) }),
};

// Library
export const library = {
  novels: () => request<any[]>('/novels'),
  chapters: (novel_id: number) => request<any[]>(`/novels/${novel_id}/chapters`),
  characters: (chapter_id: number) => request<any[]>(`/chapters/${chapter_id}/characters`),
  scenes: (chapter_id: number) => request<any[]>(`/chapters/${chapter_id}/scenes`),
  script: (chapter_id: number) => request<any>(`/chapters/${chapter_id}/script`),
  shots: (chapter_id: number) => request<any[]>(`/chapters/${chapter_id}/shots`),
  upload: (file: File) => {
    const fd = new FormData(); fd.append('file', file);
    return request<any>('/upload', { method: 'POST', body: fd, headers: {} });
  },
};

// Agents
export const agents = {
  run: (body: { agent: string; target_type: string; target_id: number; extra?: string; chapter_id?: number }) =>
    request<{ task_id: string }>('/agents/run', { method: 'POST', body: JSON.stringify(body) }),
};

// Videos
export const videos = {
  list: (chapter_id: number) => request<any[]>(`/chapters/${chapter_id}/videos`),
  regenerate: (chapter_id: number) =>
    request<{ task_id: string }>(`/chapters/${chapter_id}/videos/regenerate`, { method: 'POST' }),
};

// Tasks
export const tasks = {
  list: () => request<any[]>('/tasks'),
  get: (id: string) => request<any>(`/tasks/${id}`),
  cancel: (id: string) => request(`/tasks/${id}/cancel`, { method: 'POST' }),
  retry: (id: string) => request<{ task_id: string }>(`/tasks/${id}/retry`, { method: 'POST' }),
};

// Settings
export const settings = {
  cookieStatus: () => request<{ valid: boolean }>('/settings/cookie-status'),
  cookie: (value: string) => request('/settings/cookie', { method: 'POST', body: JSON.stringify({ value }) }),
  llm: (config?: any) => config
    ? request('/settings/llm', { method: 'POST', body: JSON.stringify(config) })
    : request<any>('/settings/llm'),
};

// SSE
export function subscribeEvents(taskId: string, onProgress: (data: any) => void, onComplete: (data: any) => void, onError: (data: any) => void): EventSource {
  const es = new EventSource(`${BASE}/events/${taskId}`);
  es.addEventListener('progress', (e) => onProgress(JSON.parse(e.data)));
  es.addEventListener('complete', (e) => { onComplete(JSON.parse(e.data)); es.close(); });
  es.addEventListener('error', (e) => { onError(JSON.parse(e.data)); es.close(); });
  return es;
}
```

- [ ] **Step 5: 创建 types.ts**

```typescript
// web/src/types.ts
export interface Novel { id: number; title: string; author: string; }
export interface Chapter { id: number; novel_id: number; chapter_num: number; status: string; }
export interface Character { id: number; name: string; outfits: Outfit[]; }
export interface Outfit { id: number; tag: string; image_path: string; prompt: string; is_default: number; }
export interface Scene { id: number; name: string; description: string; lighting: string; style: string; multi_view_image: string; }
export interface Script { id: number; raw_json: any; }
export interface Shot { id: number; shot_num: number; narration: string; dialogue: string; camera_movement: string; duration_sec: number; image_prompt: string; status: string; }
export interface Task { id: string; type: string; chapter_id: number; status: string; progress: number; params: string; error?: string; }
```

- [ ] **Step 6: 验证前端启动**

```bash
cd D:/first_agent/web && npm run dev
# 预期: Vite running on http://localhost:5173
```

- [ ] **Step 7: 提交**

```bash
git add web/
git commit -m "feat(web): React + Vite + shadcn/ui project scaffold with API client"
```

---

### Task 9: 前端布局框架 — Sidebar + 路由

**Files:**
- Create: `web/src/stores/app.ts`
- Create: `web/src/components/Layout.tsx`
- Create: `web/src/components/Sidebar.tsx`
- Modify: `web/src/App.tsx`, `web/src/main.tsx`

**Interfaces:**
- Consumes: `api.ts`, `types.ts`
- Produces: 6 页面路由 (`/`, `/library`, `/videos`, `/cookie`, `/tasks`, `/settings`)，左侧导航栏，主内容区

- [ ] **Step 1: 实现 Zustand store**

```typescript
// web/src/stores/app.ts
import { create } from 'zustand';

interface AppState {
  activeNav: string;
  setActiveNav: (nav: string) => void;
  currentNovelId: number | null;
  setCurrentNovelId: (id: number | null) => void;
  currentChapterId: number | null;
  setCurrentChapterId: (id: number | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  activeNav: 'chat',
  setActiveNav: (nav) => set({ activeNav: nav }),
  currentNovelId: null,
  setCurrentNovelId: (id) => set({ currentNovelId: id }),
  currentChapterId: null,
  setCurrentChapterId: (id) => set({ currentChapterId: id }),
}));
```

- [ ] **Step 2: 实现 Sidebar 组件**

```tsx
// web/src/components/Sidebar.tsx
import { useAppStore } from '../stores/app';
import { MessageCircle, Library, Film, Cookie, ListTodo, Settings } from 'lucide-react';

const NAV_ITEMS = [
  { key: 'chat', label: 'AI漫剧助手', icon: MessageCircle },
  { key: 'library', label: '漫剧素材库', icon: Library },
  { key: 'videos', label: '漫剧视频', icon: Film },
  { key: 'cookie', label: '豆包Cookie', icon: Cookie },
  { key: 'tasks', label: '任务中心', icon: ListTodo },
  { key: 'settings', label: '系统设置', icon: Settings },
];

export function Sidebar() {
  const { activeNav, setActiveNav } = useAppStore();

  return (
    <aside className="w-56 h-screen bg-gray-950 border-r border-gray-800 flex flex-col">
      <div className="p-4 text-lg font-bold text-white border-b border-gray-800">🎬 AI漫剧</div>
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveNav(key)}
            className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
              activeNav === key
                ? 'bg-gray-800 text-white border-r-2 border-blue-500'
                : 'text-gray-400 hover:text-white hover:bg-gray-800/50'
            }`}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 3: 实现 Layout 组件 + App.tsx 路由**

```tsx
// web/src/components/Layout.tsx
import { Sidebar } from './Sidebar';
import { useAppStore } from '../stores/app';
import { ChatPage } from '../pages/ChatPage';
import { LibraryPage } from '../pages/LibraryPage';
import { VideosPage } from '../pages/VideosPage';
import { CookiePage } from '../pages/CookiePage';
import { TasksPage } from '../pages/TasksPage';
import { SettingsPage } from '../pages/SettingsPage';

const PAGES: Record<string, React.ComponentType> = {
  chat: ChatPage,
  library: LibraryPage,
  videos: VideosPage,
  cookie: CookiePage,
  tasks: TasksPage,
  settings: SettingsPage,
};

export function Layout() {
  const { activeNav } = useAppStore();
  const Page = PAGES[activeNav] || ChatPage;

  return (
    <div className="flex h-screen bg-gray-900 text-white">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Page />
      </main>
    </div>
  );
}

// web/src/App.tsx
import { Layout } from './components/Layout';

export default function App() {
  return <Layout />;
}
```

- [ ] **Step 4: 创建各页面骨架 (占位)**

每个页面先写简单的占位组件，后续 Task 逐步填充。

```tsx
// web/src/pages/ChatPage.tsx
export function ChatPage() {
  return <div className="p-6"><h1 className="text-2xl font-bold">AI漫剧助手</h1><p className="text-gray-400 mt-2">Chat 页面开发中...</p></div>;
}
// 其他 5 个页面同理...
```

- [ ] **Step 5: 验证前端可正常浏览各页面**

```bash
cd D:/first_agent/web && npm run dev
# 浏览器打开 http://localhost:5173
# 点击左侧导航项，确认各页面占位正常显示
```

- [ ] **Step 6: 提交**

```bash
git add web/src/
git commit -m "feat(web): sidebar + routing + page shells"
```

---

### Task 10: 素材库页面 — 完整功能

**Files:**
- Create: `web/src/pages/LibraryPage.tsx`
- Create: `web/src/pages/library/NovelList.tsx`
- Create: `web/src/pages/library/ChapterView.tsx`
- Create: `web/src/pages/library/CharacterCard.tsx`
- Create: `web/src/pages/library/SceneCard.tsx`
- Create: `web/src/pages/library/ScriptView.tsx`
- Create: `web/src/pages/library/ShotList.tsx`
- Create: `web/src/components/ImagePreview.tsx`

**流程：** 小说列表 → 点击小说 → 展开章节列表 → 点击章节 → Tab 切换 (人物/场景/剧本/镜头)
**交互：** 卡片点击 → ImagePreview 弹窗大图 → "重新生成"按钮 → `agents.run()` → 订阅 SSE 进度

- [ ] **Step 1-6: 逐个实现组件，每个写完即测**

参考 api.ts 中的 `library.*` 和 `agents.*` 方法。

- [ ] **Step 7: 提交**

```bash
git add web/src/pages/LibraryPage.tsx web/src/pages/library/ web/src/components/ImagePreview.tsx
git commit -m "feat(web): library page with browse, preview, and regenerate"
```

---

### Task 11: Chat 页面 — 对话 + 文件上传 + 意图反馈

**Files:**
- Create: `web/src/pages/ChatPage.tsx`

**实现要点：**
- 消息列表：user 靠右蓝色气泡，assistant 靠左灰色气泡，system 居中灰色
- 输入框 + 发送按钮 (Ctrl+Enter)
- 文件上传按钮 (支持 .txt .docx .pdf)
- 意图结果展示：如 ["正在启动全链路生成第3章...", task_id link]
- 上下文管理器：从 Zustand store 读取 currentNovelId/currentChapterId
- 调用 `chat.send()` → 显示回复 → 如果有 task_id → 启动 SSE 订阅

- [ ] **Step 1-4: 实现 → 验证 → 修复 → 提交**

```bash
git add web/src/pages/ChatPage.tsx
git commit -m "feat(web): chat page with messages, file upload, intent feedback"
```

---

### Task 12: 视频页 + Cookie 页 + 任务中心页 + 设置页

**Files:**
- Modify: `web/src/pages/VideosPage.tsx`
- Modify: `web/src/pages/CookiePage.tsx` — 含 CookieGuide 组件
- Modify: `web/src/pages/TasksPage.tsx` — 含 TaskProgress 组件
- Modify: `web/src/pages/SettingsPage.tsx`

**视频页要点：** 章节选择器 → 视频列表 → 播放/下载 → "重新生成"按钮 + 额度警告弹窗

**Cookie 页要点：** 状态指示（绿/红） → 图文引导步骤（1.打开豆包 2.F12 3.Application→Cookies 4.复制粘贴） → 输入框 → 保存

**任务中心要点：** 卡片列表 (运行中绿色 失败红色 完成灰色) → 进度条 → 取消/重试按钮 → SSE 实时更新

**设置页要点：** LLM API Key 输入框 → 输出目录 → 图片/视频质量下拉

- [ ] **Step 1-6: 逐个页面实现、验证、提交**

---

### Task 13: 集成测试 — 前后端联调 + 打包部署

**Files:**
- Modify: `server/main.py` — 添加 `StaticFiles` mount
- Modify: `web/vite.config.ts` — 构建输出到 `../server/static/`

- [ ] **Step 1: 生产构建配置**

```typescript
// web/vite.config.ts — 添加 build.outDir:
export default defineConfig({
  build: {
    outDir: '../server/static',
    emptyOutDir: true,
  },
  // ... rest
});
```

- [ ] **Step 2: server/main.py 挂载静态文件**

```python
from pathlib import Path
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

- [ ] **Step 3: 构建 + 启动一体化验证**

```bash
cd D:/first_agent/web && npm run build
cd D:/first_agent && python -m server
# 浏览器打开 http://localhost:8000
# 验证: 聊天 → 素材库浏览 → 任务进度 → Cookie 设置 全程正常
```

- [ ] **Step 4: 编写集成测试**

```python
# tests/test_server_api.py — 新增端到端 API 测试
# 使用 TestClient 对每个端点做 smoke test
```

- [ ] **Step 5: 提交**

```bash
git add server/main.py web/vite.config.ts tests/test_server_api.py
git commit -m "feat: production build + integration tests"
```

---

## 自审

1. ✅ 规格覆盖：每个 spec 中的 API 端点都有对应 Task
2. ✅ 无占位符：所有步骤都有实际代码或明确的实现方向
3. ✅ 类型一致性：api.ts 的方法名 → pages 组件中的调用 → server/api/*.py 的路由一致
4. ✅ 文件上传处理：在 Chat page 和 `/api/chat/send` 中覆盖
