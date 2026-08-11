"""素材库 REST 端点 — novels, chapters, characters, scenes, scripts, shots, upload, delete."""
import json
import re
import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from server.db import get_db

DB_PATH = Path("data/aicomic.db")

router = APIRouter(prefix="/api", tags=["library"])


# ── Novels ──

@router.get("/novels")
def list_novels():
    """所有小说列表."""
    conn = get_db()
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
    conn = get_db()
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
    conn = get_db()
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
        _cleanup_orphans(conn)
        conn.commit()

        return {
            "status": "ok",
            "merged_from": {"id": src["id"], "title": src["title"]},
            "merged_into": {"id": dst["id"], "title": dst["title"]},
            "chapters_moved": moved,
        }
    finally:
        conn.close()


def _cleanup_orphans(conn) -> dict:
    """清理不再被任何章节引用的 character_card/outfit 和 scene_card。

    只在所有关联 shot 关系被删除后调用。安全：只删除零引用的对象。
    返回: {"characters": int, "scenes": int}
    """
    import os as _os
    count_c = 0
    count_s = 0

    # ── 孤角色 outfit（该 character 不再出现在任何 shot_character_outfit 中）──
    orphan_outfits = conn.execute("""
        SELECT co.id, co.character_id, co.image_path
        FROM character_outfit co
        WHERE co.character_id NOT IN (
            SELECT DISTINCT sco.character_id FROM shot_character_outfit sco
        )
    """).fetchall()
    for oo in orphan_outfits:
        # 删除图片文件
        if oo["image_path"] and _os.path.exists(oo["image_path"]):
            _os.remove(oo["image_path"])
        conn.execute("DELETE FROM character_outfit WHERE id = ?", (oo["id"],))
        count_c += 1

    # ── 孤 character_card ──
    conn.execute("""
        DELETE FROM character_card
        WHERE id NOT IN (
            SELECT DISTINCT sco.character_id FROM shot_character_outfit sco
        )
        AND id NOT IN (
            SELECT DISTINCT character_id FROM character_outfit
        )
    """)

    # ── 孤场景图片 ──
    orphan_scenes = conn.execute("""
        SELECT sc.id, sc.multi_view_image, sc.wide_image, sc.mid_image, sc.close_image
        FROM scene_card sc
        WHERE sc.id NOT IN (
            SELECT DISTINCT ss.scene_id FROM storyboard_shot ss WHERE ss.scene_id IS NOT NULL
        )
    """).fetchall()
    for os_ in orphan_scenes:
        for col in ["multi_view_image", "wide_image", "mid_image", "close_image"]:
            p = os_[col]
            if p and _os.path.exists(p):
                _os.remove(p)
        conn.execute("DELETE FROM scene_card WHERE id = ?", (os_["id"],))
        count_s += 1

    return {"characters": count_c, "scenes": count_s}


@router.delete("/novels/{novel_id}")
def delete_novel(novel_id: int):
    """删除小说及其所有章节、分镜、视频等关联数据。"""
    import os as _os
    conn = get_db()
    try:
        novel = conn.execute("SELECT id, title FROM novel WHERE id = ?", (novel_id,)).fetchone()
        if not novel:
            raise HTTPException(404, "Novel not found")

        # 收集关联数据路径
        deleted_files = 0
        chapters = conn.execute("SELECT id FROM chapter WHERE novel_id = ?", (novel_id,)).fetchall()
        for ch in chapters:
            cid = ch["id"]
            # 收集视频文件路径
            clips = conn.execute("""
                SELECT vc.file_path FROM video_clip vc
                JOIN storyboard_shot ss ON ss.id = vc.shot_id
                JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?
            """, (cid,)).fetchall()
            for cl in clips:
                if cl["file_path"] and _os.path.exists(cl["file_path"]):
                    _os.remove(cl["file_path"]); deleted_files += 1

            finals = conn.execute(
                "SELECT file_path FROM final_video WHERE chapter_id = ?", (cid,)
            ).fetchall()
            for fv in finals:
                if fv["file_path"] and _os.path.exists(fv["file_path"]):
                    _os.remove(fv["file_path"]); deleted_files += 1

            # 收集图片文件
            img_rows = conn.execute("""
                SELECT co.image_path FROM character_outfit co
                JOIN shot_character_outfit sco ON sco.character_id = co.character_id
                JOIN storyboard_shot ss ON ss.id = sco.shot_id
                JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ? AND co.image_path != ''
            """, (cid,)).fetchall()
            for ir in img_rows:
                if ir["image_path"] and _os.path.exists(ir["image_path"]):
                    _os.remove(ir["image_path"]); deleted_files += 1

            # 删除关联数据 (按依赖顺序)
            conn.execute("DELETE FROM video_clip WHERE shot_id IN (SELECT ss.id FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?)", (cid,))
            conn.execute("DELETE FROM shot_character_outfit WHERE shot_id IN (SELECT ss.id FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?)", (cid,))
            conn.execute("DELETE FROM storyboard_shot WHERE script_id IN (SELECT id FROM script WHERE chapter_id=?)", (cid,))
            conn.execute("DELETE FROM final_video WHERE chapter_id = ?", (cid,))
            conn.execute("DELETE FROM script WHERE chapter_id = ?", (cid,))
            conn.execute("DELETE FROM task_log WHERE chapter_id = ?", (cid,))
            conn.execute("DELETE FROM chat_message WHERE chapter_id = ?", (cid,))
            conn.execute("DELETE FROM task WHERE chapter_id = ?", (cid,))
            conn.execute("DELETE FROM chapter WHERE id = ?", (cid,))

        conn.execute("DELETE FROM novel WHERE id = ?", (novel_id,))

        # ── 清理全局无引用孤对象 ──
        deleted_orphans = _cleanup_orphans(conn)

        conn.commit()

        return {
            "status": "ok",
            "deleted_novel": {"id": novel["id"], "title": novel["title"]},
            "deleted_chapters": len(chapters),
            "deleted_files": deleted_files,
            "cleaned_orphans": deleted_orphans,
        }
    finally:
        conn.close()


@router.delete("/chapters/{chapter_id}")
def delete_chapter(chapter_id: int):
    """删除单个章节及其分镜、视频等关联数据。"""
    import os as _os
    conn = get_db()
    try:
        ch = conn.execute("SELECT id, novel_id, chapter_num FROM chapter WHERE id = ?", (chapter_id,)).fetchone()
        if not ch:
            raise HTTPException(404, "Chapter not found")

        deleted_files = 0

        # 收集并删除视频文件
        clips = conn.execute("""
            SELECT vc.file_path FROM video_clip vc
            JOIN storyboard_shot ss ON ss.id = vc.shot_id
            JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
        """, (chapter_id,)).fetchall()
        for cl in clips:
            if cl["file_path"] and _os.path.exists(cl["file_path"]):
                _os.remove(cl["file_path"]); deleted_files += 1

        finals = conn.execute(
            "SELECT file_path FROM final_video WHERE chapter_id = ?", (chapter_id,)
        ).fetchall()
        for fv in finals:
            if fv["file_path"] and _os.path.exists(fv["file_path"]):
                _os.remove(fv["file_path"]); deleted_files += 1

        # 收集并删除图片
        img_rows = conn.execute("""
            SELECT co.image_path FROM character_outfit co
            JOIN shot_character_outfit sco ON sco.character_id = co.character_id
            JOIN storyboard_shot ss ON ss.id = sco.shot_id
            JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ? AND co.image_path != ''
        """, (chapter_id,)).fetchall()
        for ir in img_rows:
            if ir["image_path"] and _os.path.exists(ir["image_path"]):
                _os.remove(ir["image_path"]); deleted_files += 1

        # 删除关联数据
        conn.execute("DELETE FROM video_clip WHERE shot_id IN (SELECT ss.id FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?)", (chapter_id,))
        conn.execute("DELETE FROM shot_character_outfit WHERE shot_id IN (SELECT ss.id FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?)", (chapter_id,))
        conn.execute("DELETE FROM storyboard_shot WHERE script_id IN (SELECT id FROM script WHERE chapter_id=?)", (chapter_id,))
        conn.execute("DELETE FROM final_video WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM script WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM task_log WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM chat_message WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM task WHERE chapter_id = ?", (chapter_id,))
        conn.execute("DELETE FROM chapter WHERE id = ?", (chapter_id,))

        # ── 清理全局无引用孤对象 ──
        deleted_orphans = _cleanup_orphans(conn)

        conn.commit()

        return {
            "status": "ok",
            "deleted_chapter": {"id": ch["id"], "chapter_num": ch["chapter_num"]},
            "deleted_files": deleted_files,
            "cleaned_orphans": deleted_orphans,
        }
    finally:
        conn.close()


# ── Characters ──

@router.get("/chapters/{chapter_id}/characters")
def list_characters(chapter_id: int):
    """某章节关联的所有角色及其 outfit.

    两条路径:
    1. 主路径: 通过 shot_character_outfit 联结表 (v0.12+, 支持多装扮)
    2. 降级路径: 直接从 storyboard_shot.char_ids 解析角色ID
       — 适用于旧管线跑的章节（联结表无数据但 shot 里有 char_ids）
    """
    conn = get_db()
    try:
        # 步骤1: 尝试 shot_character_outfit 联结表
        rows = conn.execute("""
            SELECT DISTINCT cc.id, cc.name, cc.status
            FROM character_card cc
            INNER JOIN shot_character_outfit sco ON sco.character_id = cc.id
            INNER JOIN storyboard_shot ss ON ss.id = sco.shot_id
            INNER JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
            ORDER BY cc.name
        """, (chapter_id,)).fetchall()

        # 步骤2: 降级 — 从 shot.char_ids 直接解析
        if not rows:
            # 获取该章节最新 script 的所有 shot 的 char_ids
            shot_rows = conn.execute("""
                SELECT ss.char_ids FROM storyboard_shot ss
                INNER JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?
            """, (chapter_id,)).fetchall()

            # 汇总所有出现过的角色 ID
            seen_ids = set()
            for sr in shot_rows:
                try:
                    ids = json.loads(sr["char_ids"] or "[]")
                    for cid in ids:
                        if isinstance(cid, int):
                            seen_ids.add(cid)
                except (json.JSONDecodeError, TypeError):
                    pass

            if seen_ids:
                placeholders = ",".join("?" * len(seen_ids))
                rows = conn.execute(
                    f"""SELECT id, name, status FROM character_card
                        WHERE id IN ({placeholders}) ORDER BY name""",
                    tuple(seen_ids),
                ).fetchall()

        characters = []
        for row in rows:
            char = dict(row)
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
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT DISTINCT sc.id, sc.name, sc.description, sc.lighting, sc.style,
                   sc.wide_view, sc.mid_view, sc.close_view, sc.status,
                   sc.multi_view_image, sc.wide_image, sc.mid_image, sc.close_image
            FROM scene_card sc
            INNER JOIN storyboard_shot ss ON ss.scene_id = sc.id
            INNER JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
            ORDER BY sc.name
        """, (chapter_id,)).fetchall()

        scenes = []
        for row in rows:
            scene = dict(row)
            # 合并多图路径为单个字段: multi_view_image > wide_image > mid_image > close_image
            scene["multi_view_image"] = (
                scene.get("multi_view_image") or scene.get("wide_image")
                or scene.get("mid_image") or scene.get("close_image") or ""
            )
            scenes.append(scene)

        return scenes
    finally:
        conn.close()


# ── Script ──

@router.get("/chapters/{chapter_id}/script")
def get_script(chapter_id: int):
    """某章节的剧本 JSON."""
    conn = get_db()
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
    conn = get_db()
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

        conn = get_db()
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
