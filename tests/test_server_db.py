"""Tests for server/db.py — chat, settings, and task storage."""
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


def test_chat_store_summary_flow():
    """摘要写入后可查询并判断未摘要消息."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, ChatStore
    init_schema(conn)
    store = ChatStore(conn)

    # 写入多条消息
    store.insert(1, "user", "msg1")
    store.insert(1, "assistant", "msg2")
    store.insert(1, "user", "msg3")
    store.insert(1, "assistant", "msg4")

    # 前2条做摘要
    store.save_summary(1, "前两条摘要", 1, 2)

    # 获取未摘要的消息 ID
    unsummarized = store.get_unsummarized_ids(1, 2)
    assert len(unsummarized) == 2  # msg3, msg4

    # 按 ID 取消息
    msgs = store.get_messages_by_ids(unsummarized)
    assert len(msgs) == 2
    assert msgs[0]["content"] == "msg3"

    # 验证摘要列表
    summaries = store.get_summaries(1)
    assert len(summaries) == 1
    assert summaries[0]["summary_text"] == "前两条摘要"

    conn.close()
    db_path.unlink()


def test_settings_store_get_all_and_delete():
    """SettingsStore get_all 和 delete 操作."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, SettingsStore
    init_schema(conn)
    store = SettingsStore(conn)

    store.set("key1", "val1")
    store.set("key2", "val2")

    all_kv = store.get_all()
    assert all_kv == {"key1": "val1", "key2": "val2"}

    store.delete("key1")
    assert store.get("key1") is None
    assert store.get("key2") == "val2"

    conn.close()
    db_path.unlink()


def test_task_store_get_active():
    """get_active 只返回 pending 和 running 的任务."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    from server.db import init_schema, TaskStore
    init_schema(conn)
    store = TaskStore(conn)

    t1 = store.create("pipeline", chapter_id=1)
    t2 = store.create("agent", chapter_id=2)
    t3 = store.create("pipeline", chapter_id=3)

    store.update(t2, status="running")
    store.update(t3, status="done")

    active = store.get_active()
    assert len(active) == 2  # t1 pending + t2 running
    active_ids = {t["id"] for t in active}
    assert t1 in active_ids
    assert t2 in active_ids
    assert t3 not in active_ids

    conn.close()
    db_path.unlink()


def test_deduplicate_novels_merges_duplicates():
    """同名 novel 自动合并章节: '逆天邪神' + '逆天邪神第1章 云澈' → 1条 novel."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS novel (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, author TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS chapter (id INTEGER PRIMARY KEY AUTOINCREMENT, novel_id INTEGER REFERENCES novel(id), chapter_num INTEGER NOT NULL, raw_text TEXT NOT NULL DEFAULT '', status TEXT DEFAULT 'idle');
    """)
    conn.commit()

    conn.execute("INSERT INTO novel (id, title) VALUES (1, '逆天邪神')")
    conn.execute("INSERT INTO novel (id, title) VALUES (2, '逆天邪神第1章 云澈')")
    conn.execute("INSERT INTO chapter (id, novel_id, chapter_num, raw_text) VALUES (1, 1, 1, 'ch1')")
    conn.execute("INSERT INTO chapter (id, novel_id, chapter_num, raw_text) VALUES (2, 2, 2, 'ch2')")
    conn.commit()

    from server.db import deduplicate_novels
    merged = deduplicate_novels(conn)
    assert merged == 1

    novels = conn.execute("SELECT id, title FROM novel").fetchall()
    assert len(novels) == 1
    assert novels[0]["id"] == 1

    chapters = conn.execute("SELECT id, novel_id FROM chapter ORDER BY id").fetchall()
    assert [c["novel_id"] for c in chapters] == [1, 1]

    conn.close()
    db_path.unlink()
