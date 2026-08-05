"""视频管理端点 — 章节视频列表、重新生成."""
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")

router = APIRouter(prefix="/api", tags=["videos"])


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/chapters/{chapter_id}/videos")
def list_videos(chapter_id: int):
    """某章节的所有视频 (shot clips + final video)."""
    conn = _get_conn()
    try:
        # Shot video clips
        clips = conn.execute("""
            SELECT vc.id, vc.file_path, vc.duration_sec, vc.status,
                   ss.shot_num, vc.created_at
            FROM video_clip vc
            INNER JOIN storyboard_shot ss ON ss.id = vc.shot_id
            INNER JOIN script s ON s.id = ss.script_id
            WHERE s.chapter_id = ?
            ORDER BY ss.shot_num
        """, (chapter_id,)).fetchall()

        # Final videos
        finals = conn.execute("""
            SELECT id, file_path, created_at
            FROM final_video
            WHERE chapter_id = ?
            ORDER BY created_at DESC
        """, (chapter_id,)).fetchall()

        return {
            "clips": [dict(c) for c in clips],
            "finals": [dict(f) for f in finals],
        }
    finally:
        conn.close()


@router.post("/chapters/{chapter_id}/videos/regenerate")
def regenerate_videos(chapter_id: int):
    """触发视频重新生成 (返回 task 创建指引，实际操作通过 agents/run 触发)."""
    # 此端点提供信息，实际重生成通过 POST /api/agents/run 触发
    return {
        "message": "视频重新生成请使用 POST /api/agents/run",
        "example": {
            "agent": "shot-video-generator",
            "target_type": "chapter",
            "target_id": chapter_id,
            "chapter_id": chapter_id,
        },
    }
