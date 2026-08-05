"""素材库 REST 端点 — novels, chapters, characters, scenes, scripts, shots, upload."""
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File

DB_PATH = Path("data/aicomic.db")

router = APIRouter(prefix="/api", tags=["library"])


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接 (每次请求新建，线程安全)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Novels ──

@router.get("/novels")
def list_novels():
    """所有小说列表."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, title, author, created_at FROM novel ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/novels/{novel_id}/chapters")
def list_chapters(novel_id: int):
    """某小说的所有章节."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, novel_id, chapter_num, status, created_at FROM chapter "
            "WHERE novel_id = ? ORDER BY chapter_num",
            (novel_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/novels/merge")
def merge_novels(source_id: int, target_id: int):
    """将 source novel 的所有章节合并到 target novel，然后删除 source。

    用于修复历史上因文件名不同导致的重复小说问题。
    """
    conn = _get_conn()
    try:
        src = conn.execute("SELECT id, title FROM novel WHERE id = ?", (source_id,)).fetchone()
        dst = conn.execute("SELECT id, title FROM novel WHERE id = ?", (target_id,)).fetchone()
        if not src or not dst:
            raise HTTPException(404, "Novel not found")

        # 移动章节
        moved = conn.execute(
            "UPDATE chapter SET novel_id = ? WHERE novel_id = ?",
            (target_id, source_id),
        ).rowcount

        # 删除被合并的 novel
        conn.execute("DELETE FROM novel WHERE id = ?", (source_id,))
        conn.commit()

        return {
            "status": "ok",
            "merged_from": {"id": src["id"], "title": src["title"]},
            "merged_into": {"id": dst["id"], "title": dst["title"]},
            "chapters_moved": moved,
        }
    finally:
        conn.close()


# ── Characters ──

@router.get("/chapters/{chapter_id}/characters")
def list_characters(chapter_id: int):
    """某章节关联的所有角色及其 outfit."""
    conn = _get_conn()
    try:
        # 通过 shot_character_outfit 找到章节中出现的角色
        rows = conn.execute("""
            SELECT DISTINCT cc.id, cc.name, cc.status
            FROM character_card cc
            INNER JOIN shot_character_outfit sco ON sco.character_id = cc.id
            INNER JOIN storyboard_shot ss ON ss.id = sco.shot_id
            INNER JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
            ORDER BY cc.name
        """, (chapter_id,)).fetchall()

        characters = []
        for row in rows:
            char = dict(row)
            # 查询 outfits
            outfits = conn.execute("""
                SELECT id, tag, prompt, image_path, is_default
                FROM character_outfit
                WHERE character_id = ?
                ORDER BY is_default DESC, tag
            """, (char["id"],)).fetchall()
            char["outfits"] = [dict(o) for o in outfits]
            characters.append(char)

        return characters
    finally:
        conn.close()


# ── Scenes ──

@router.get("/chapters/{chapter_id}/scenes")
def list_scenes(chapter_id: int):
    """某章节关联的所有场景."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT DISTINCT sc.id, sc.name, sc.description, sc.lighting, sc.style,
                   sc.wide_view, sc.mid_view, sc.close_view, sc.status
            FROM scene_card sc
            INNER JOIN storyboard_shot ss ON ss.scene_id = sc.id
            INNER JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
            ORDER BY sc.name
        """, (chapter_id,)).fetchall()

        scenes = []
        for row in rows:
            scene = dict(row)
            # 合并 multi-view 为单个字段 (取第一个非空的 view)
            scene["multi_view_image"] = (
                scene.get("wide_view") or scene.get("mid_view") or scene.get("close_view") or ""
            )
            scenes.append(scene)

        return scenes
    finally:
        conn.close()


# ── Script ──

@router.get("/chapters/{chapter_id}/script")
def get_script(chapter_id: int):
    """某章节的剧本 JSON."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, raw_json, status FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Script not found for this chapter")
        result = dict(row)
        result["raw_json"] = json.loads(result["raw_json"])
        return result
    finally:
        conn.close()


# ── Shots ──

@router.get("/chapters/{chapter_id}/shots")
def list_shots(chapter_id: int):
    """某章节的所有分镜."""
    conn = _get_conn()
    try:
        # 获取最新 script
        script_row = conn.execute(
            "SELECT id FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
            (chapter_id,),
        ).fetchone()
        if not script_row:
            return []

        rows = conn.execute("""
            SELECT id, shot_num, narration, dialogue, camera_movement,
                   duration_sec, image_prompt, status
            FROM storyboard_shot
            WHERE script_id = ?
            ORDER BY shot_num
        """, (script_row["id"],)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Upload ──

def _extract_novel_title(filename: str) -> str:
    """从文件名中提取纯书名，剥离章节号。

    "逆天邪神第2章 情不自己.txt"  →  "逆天邪神"
    "逆天邪神 第1章.txt"          →  "逆天邪神"
    "星辰变_第3章.docx"            →  "星辰变"
    "simple-novel.txt"             →  "simple-novel"
    """
    name = Path(filename).stem.strip()

    # 去除常见章节后缀: "第X章...", "Chapter X...", "_第X章", " 第X章"
    patterns = [
        r'[\s_]*第\s*\d+\s*章.*$',      # "第1章", "第1章 云澈"
        r'[\s_]*Chapter\s+\d+.*$',        # "Chapter 1 ..."
        r'[\s_]*(?:上|中|下|终)$',         # "星辰变 上"
    ]
    for pat in patterns:
        name = re.sub(pat, '', name, flags=re.IGNORECASE)

    # 如果只剩几个字，保留原名
    if len(name) < 1:
        name = Path(filename).stem.strip()

    return name.strip()


def _detect_chapter_num(filename: str) -> int | None:
    """从文件名中自动检测章节号。

    "逆天邪神第2章.txt"  →  2
    "Chapter 5.docx"      →  5
    "第03章.pdf"          →  3
    "novel.txt"           →  None (no chapter hint)
    """
    # 中文: 第N章
    m = re.search(r'第\s*(\d+)\s*章', filename)
    if m: return int(m.group(1))
    # 英文: Chapter N
    m = re.search(r'Chapter\s+(\d+)', filename, re.IGNORECASE)
    if m: return int(m.group(1))
    # 纯数字后缀
    m = re.search(r'[^\d](\d{1,3})$', Path(filename).stem)
    if m: return int(m.group(1))
    return None


def _find_novel(conn, novel_title: str) -> int | None:
    """按书名查找已存在的小说。先精确匹配，再模糊匹配（LIKE）。"""
    # 1. 精确匹配
    row = conn.execute("SELECT id FROM novel WHERE title = ?", (novel_title,)).fetchone()
    if row: return row["id"]

    # 2. 模糊: 去掉标点后对比
    clean = re.sub(r'\s+', '', novel_title)
    rows = conn.execute("SELECT id, title FROM novel").fetchall()
    for r in rows:
        existing_clean = re.sub(r'\s+', '', r["title"])
        if existing_clean == clean or existing_clean.startswith(clean[:4]) or clean.startswith(existing_clean[:4]):
            return r["id"]

    return None


def _create_chapter(conn, novel_id: int, chapter_num: int, raw_text: str) -> tuple[int, str]:
    """创建或更新章节，返回 (chapter_id, action)."""
    existing = conn.execute(
        "SELECT id FROM chapter WHERE novel_id = ? AND chapter_num = ?",
        (novel_id, chapter_num),
    ).fetchone()

    if existing:
        conn.execute("UPDATE chapter SET raw_text = ?, status = 'idle' WHERE id = ?", (raw_text, existing["id"]))
        conn.commit()
        return existing["id"], "updated"
    else:
        cur = conn.execute(
            "INSERT INTO chapter (novel_id, chapter_num, raw_text, status) VALUES (?, ?, ?, 'idle')",
            (novel_id, chapter_num, raw_text),
        )
        conn.commit()
        return cur.lastrowid, "created"


def _next_chapter_num(conn, novel_id: int) -> int:
    """返回该小说下一个可用章节号（最大已有序号 + 1）。"""
    row = conn.execute("SELECT MAX(chapter_num) as mx FROM chapter WHERE novel_id = ?", (novel_id,)).fetchone()
    return (row["mx"] or 0) + 1


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传小说文件 (.txt / .docx / .pdf)，解析后入库。

    智能识别书名和章节号：
    - "逆天邪神第2章.txt" → 加到已有「逆天邪神」novel 的第2章
    - "星辰变_第3章.docx"  → 加到已有「星辰变」novel 的第3章
    - "simple.txt"          → 新建 novel，章节号为下一个可用序号
    """
    allowed_suffixes = {".txt", ".docx", ".pdf"}
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(400, f"Unsupported file type: {suffix}. Allowed: {', '.join(allowed_suffixes)}")

    content = await file.read()
    tmp_path = Path(tempfile.mktemp(suffix=suffix))
    tmp_path.write_bytes(content)

    try:
        from src.aicomic.parsers import parse_file
        raw_text = parse_file(tmp_path)

        # 智能提取书名和章节号
        clean_title = _extract_novel_title(filename)
        detected_ch = _detect_chapter_num(filename)

        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        try:
            novel_id = _find_novel(conn, clean_title)

            if novel_id:
                # 已有小说 — 复用
                chapter_num = detected_ch or _next_chapter_num(conn, novel_id)
                novel_title = conn.execute("SELECT title FROM novel WHERE id = ?", (novel_id,)).fetchone()["title"]
            else:
                # 新建小说
                cur = conn.execute("INSERT INTO novel (title, author) VALUES (?, '')", (clean_title,))
                conn.commit()
                novel_id = cur.lastrowid
                novel_title = clean_title
                chapter_num = detected_ch or 1

            chapter_id, action = _create_chapter(conn, novel_id, chapter_num, raw_text)
        finally:
            conn.close()

        return {
            "status": "ok",
            "action": action,
            "novel_id": novel_id,
            "chapter_id": chapter_id,
            "chapter_num": chapter_num,
            "title": novel_title,
            "filename": filename,
            "char_count": len(raw_text),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to parse file: {e}")
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
