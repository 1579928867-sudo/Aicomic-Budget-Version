"""素材库 REST 端点 — novels, chapters, characters, scenes, scripts, shots, upload."""
import json
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

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传小说文件 (.txt / .docx / .pdf)，解析后入库."""
    # 验证文件类型
    allowed_suffixes = {".txt", ".docx", ".pdf"}
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(400, f"Unsupported file type: {suffix}. Allowed: {', '.join(allowed_suffixes)}")

    # 保存临时文件
    content = await file.read()
    tmp_path = Path(tempfile.mktemp(suffix=suffix))
    tmp_path.write_bytes(content)

    try:
        # 使用现有 parser 解析
        from src.aicomic.parsers import parse_file
        raw_text = parse_file(tmp_path)

        # 入库: find-or-create novel + chapter
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(DB_PATH))
        conn.row_factory = _sqlite3.Row
        try:
            novel_title = Path(filename).stem
            existing_novel = conn.execute(
                "SELECT id FROM novel WHERE title = ?", (novel_title,)
            ).fetchone()

            if existing_novel:
                novel_id = existing_novel["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO novel (title, author) VALUES (?, '')", (novel_title,)
                )
                conn.commit()
                novel_id = cur.lastrowid

            # 创建第一章 (上传时默认为第1章)
            chapter_num = 1
            existing_ch = conn.execute(
                "SELECT id FROM chapter WHERE novel_id = ? AND chapter_num = ?",
                (novel_id, chapter_num),
            ).fetchone()

            if existing_ch:
                chapter_id = existing_ch["id"]
                conn.execute(
                    "UPDATE chapter SET raw_text = ? WHERE id = ?",
                    (raw_text, chapter_id),
                )
                conn.commit()
                action = "updated"
            else:
                cur = conn.execute(
                    "INSERT INTO chapter (novel_id, chapter_num, raw_text, status) VALUES (?, ?, ?, 'idle')",
                    (novel_id, chapter_num, raw_text),
                )
                conn.commit()
                chapter_id = cur.lastrowid
                action = "created"
        finally:
            conn.close()

        return {
            "status": "ok",
            "action": action,
            "novel_id": novel_id,
            "chapter_id": chapter_id,
            "chapter_num": chapter_num,
            "title": novel_title,
            "char_count": len(raw_text),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to parse file: {e}")
    finally:
        # 清理临时文件
        try:
            tmp_path.unlink()
        except Exception:
            pass
