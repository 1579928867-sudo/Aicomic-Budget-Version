"""新增数据库表和查询方法 (在现有 aicomic.db 基础上扩展)."""
from __future__ import annotations

import uuid
import sqlite3
from pathlib import Path
from typing import Any


def get_db(path: str | Path = "data/aicomic.db") -> sqlite3.Connection:
    """统一的数据库连接工厂 — 所有 API 和 runner 共用。

    自动设置 WAL 模式、5 秒 busy_timeout、Row factory。
    每个调用者负责 close()。
    """
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


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
        if not ids:
            return []
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
               error: str | None = None, params: str | None = None):
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
        if params is not None:
            sets.append("params = ?"); vals.append(params)
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

    def delete(self, task_id: str) -> bool:
        """Delete a single task. Returns True if deleted, False if not found."""
        cur = self.conn.execute("DELETE FROM task WHERE id = ?", (task_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def delete_completed(self) -> int:
        """Delete all completed/failed/cancelled tasks. Returns count deleted."""
        cur = self.conn.execute(
            "DELETE FROM task WHERE status IN ('done', 'failed', 'cancelled')"
        )
        self.conn.commit()
        return cur.rowcount


def deduplicate_novels(conn: sqlite3.Connection) -> int:
    """清理书名重复的 novel，把章节归并到最老的那条，删除重复 novel。

    同名 novel（空格/标点忽略后匹配）→ 保留 ID 最小的，其余的被合并删除。

    Returns: 被合并/删除的 novel 数量。
    """
    import re
    rows = conn.execute("SELECT id, title FROM novel ORDER BY id").fetchall()
    if not rows:
        return 0

    merged = 0
    kept = {rows[0]["id"]}  # 第一条默认保留

    for i in range(len(rows)):
        if rows[i]["id"] in kept:
            continue
        title_a = re.sub(r'\s+', '', rows[i]["title"])
        for j in range(i):
            title_b = re.sub(r'\s+', '', rows[j]["title"])
            # 模糊匹配: 去掉空格后完全相同, 或一个包含另一个
            if (title_a == title_b
                    or (len(title_a) > 2 and title_a in title_b)
                    or (len(title_b) > 2 and title_b in title_a)):
                src_id = rows[i]["id"]
                dst_id = rows[j]["id"]  # 合并到较早的那条
                # 移动所有章节
                conn.execute("UPDATE chapter SET novel_id = ? WHERE novel_id = ?", (dst_id, src_id))
                # 删除被合并的 novel
                conn.execute("DELETE FROM novel WHERE id = ?", (src_id,))
                merged += 1
                break
        else:
            kept.add(rows[i]["id"])

    if merged:
        conn.commit()
    return merged
