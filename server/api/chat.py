"""Chat 端点 — 消息发送、历史查询、意图路由."""
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatSendBody(BaseModel):
    message: str
    chapter_id: int | None = None
    novel_id: int | None = None


def _conn():
    c = sqlite3.connect(str(DB_PATH)); c.row_factory = sqlite3.Row; return c


@router.post("/send")
async def chat_send(body: ChatSendBody):
    message = body.message; chapter_id = body.chapter_id; novel_id = body.novel_id
    from server.db import ChatStore
    from server.intent import parse_intent_with_llm
    from server.config import load_config, build_llm_client

    conn = _conn()
    try:
        store = ChatStore(conn)
        store.insert(chapter_id, "user", message)

        context = {}
        if novel_id:
            novel = conn.execute("SELECT id, title FROM novel WHERE id = ?", (novel_id,)).fetchone()
            if novel:
                context["novel"] = dict(novel)
                chapters = conn.execute("SELECT id, chapter_num FROM chapter WHERE novel_id = ? ORDER BY chapter_num", (novel_id,)).fetchall()
                context["chapters"] = [dict(c) for c in chapters]

        if chapter_id:
            chars = conn.execute("""SELECT DISTINCT cc.id, cc.name FROM character_card cc
                INNER JOIN shot_character_outfit sco ON sco.character_id = cc.id
                INNER JOIN storyboard_shot ss ON ss.id = sco.shot_id
                INNER JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?""", (chapter_id,)).fetchall()
            context["characters"] = [dict(c) for c in chars]
            scenes = conn.execute("""SELECT DISTINCT sc.id, sc.name FROM scene_card sc
                INNER JOIN storyboard_shot ss ON ss.scene_id = sc.id
                INNER JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?""", (chapter_id,)).fetchall()
            context["scenes"] = [dict(s) for s in scenes]

        try:
            config = load_config()
            llm = build_llm_client(config)

            def llm_call(sys_prompt: str, user_prompt: str) -> str:
                import json as _j
                result = llm.generate_json(sys_prompt, user_prompt)
                return _j.dumps(result, ensure_ascii=False)

            intent = parse_intent_with_llm(message, context, llm_call)
        except Exception as e:
            intent = {"intent": "chat", "reply": f"（意图解析暂不可用: {e}）"}

        reply = ""
        task_id = None
        if intent["intent"] == "generate_chapter":
            cn = intent.get("chapter_num", 1)
            reply = f"好的，我来为你生成第{cn}章。请通过 Pipeline API 触发: POST /api/pipeline/run?chapter_id=<ID>"
        elif intent["intent"] == "regenerate_character":
            reply = f"好的，重新生成 {intent.get('character_name', '未知')} 的图片" + (f"，要求: {intent.get('extra_hint', '')}" if intent.get("extra_hint") else "")
        elif intent["intent"] == "regenerate_scene":
            reply = f"好的，重新生成 {intent.get('scene_name', '未知')} 的场景图" + (f"，要求: {intent.get('extra_hint', '')}" if intent.get("extra_hint") else "")
        elif intent["intent"] == "regenerate_video":
            reply = f"好的，重新生成第{intent.get('chapter_num', '?')}章的视频。请通过 Agents API 触发。"
        elif intent["intent"] == "import_novel":
            reply = "请上传小说文件 (.txt / .docx / .pdf)，我会帮你解析并入库。"
        elif intent["intent"] == "query":
            reply = f"查询: {intent.get('query_text', message)}（可在素材库页面浏览详细信息）"
        else:
            reply = intent.get("reply", "你好！我是AI漫剧助手，可以帮你生成漫画章节、管理素材和视频。")

        store.insert(chapter_id, "assistant", reply)
        return {"reply": reply, "intent": intent["intent"], "intent_detail": intent, "task_id": task_id}
    finally:
        conn.close()


@router.get("/history")
def chat_history(chapter_id: int | None = None):
    from server.db import ChatStore
    conn = _conn()
    try:
        store = ChatStore(conn)
        return [dict(m) for m in store.get_by_chapter(chapter_id)]
    finally:
        conn.close()
