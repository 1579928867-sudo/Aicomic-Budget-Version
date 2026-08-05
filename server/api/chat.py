"""Chat 端点 — 消息发送、历史查询、意图路由."""
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatSendRequest(BaseModel):
    message: str
    chapter_id: int | None = None
    novel_id: int | None = None


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@router.post("/send")
async def chat_send(body: ChatSendRequest):
    """发送消息，返回意图解析结果和回复.

    核心流程:
    1. 存储用户消息
    2. 构建上下文 (novel, chapters, characters, scenes)
    3. 调用意图解析
    4. switch intent → 触发相应的 action 或返回 chat 回复
    5. 存储 assistant 回复
    """
    message = body.message
    chapter_id = body.chapter_id
    novel_id = body.novel_id

    from server.db import ChatStore
    from server.intent import parse_intent_with_llm

    conn = _get_conn()
    try:
        store = ChatStore(conn)

        # 1. 存储用户消息
        store.insert(chapter_id, "user", message)

        # 2. 构建上下文
        context = {}
        if novel_id:
            novel = conn.execute("SELECT id, title FROM novel WHERE id = ?", (novel_id,)).fetchone()
            if novel:
                context["novel"] = dict(novel)
                chapters = conn.execute(
                    "SELECT id, chapter_num FROM chapter WHERE novel_id = ? ORDER BY chapter_num",
                    (novel_id,),
                ).fetchall()
                context["chapters"] = [dict(c) for c in chapters]

        if chapter_id:
            # 查询该章节的角色和场景
            chars = conn.execute("""
                SELECT DISTINCT cc.id, cc.name
                FROM character_card cc
                INNER JOIN shot_character_outfit sco ON sco.character_id = cc.id
                INNER JOIN storyboard_shot ss ON ss.id = sco.shot_id
                INNER JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?
            """, (chapter_id,)).fetchall()
            context["characters"] = [dict(c) for c in chars]

            scenes = conn.execute("""
                SELECT DISTINCT sc.id, sc.name
                FROM scene_card sc
                INNER JOIN storyboard_shot ss ON ss.scene_id = sc.id
                INNER JOIN script s ON s.id = ss.script_id
                WHERE s.chapter_id = ?
            """, (chapter_id,)).fetchall()
            context["scenes"] = [dict(s) for s in scenes]

        # 3. 意图解析 (使用现有 LLM)
        try:
            from server.main import _build_llm_client, _load_config
            config = _load_config()
            llm = _build_llm_client(config)

            def llm_call(sys_prompt: str, user_prompt: str) -> str:
                import json as _json
                result = llm.generate_json(sys_prompt, user_prompt)
                # generate_json 返回 dict，转回 JSON 字符串供 intent parser 使用
                return _json.dumps(result, ensure_ascii=False)

            intent = parse_intent_with_llm(message, context, llm_call)
        except Exception as e:
            # LLM 不可用时回退到 chat
            intent = {"intent": "chat", "reply": f"（意图解析暂不可用: {e}）"}

        # 4. 根据意图生成回复
        reply = ""
        task_id = None

        if intent["intent"] == "generate_chapter":
            chapter_num = intent.get("chapter_num", 1)
            # 返回 pipeline 触发指引
            reply = f"好的，我来为你生成第{chapter_num}章。请通过 Pipeline API 触发: POST /api/pipeline/run?chapter_id=<ID>"
        elif intent["intent"] == "regenerate_character":
            char_name = intent.get("character_name", "未知")
            extra = intent.get("extra_hint", "")
            reply = f"好的，重新生成 {char_name} 的图片" + (f"，要求: {extra}" if extra else "")
        elif intent["intent"] == "regenerate_scene":
            scene_name = intent.get("scene_name", "未知")
            extra = intent.get("extra_hint", "")
            reply = f"好的，重新生成 {scene_name} 的场景图" + (f"，要求: {extra}" if extra else "")
        elif intent["intent"] == "regenerate_video":
            chapter_num = intent.get("chapter_num", "?")
            reply = f"好的，重新生成第{chapter_num}章的视频。请通过 Agents API 触发。"
        elif intent["intent"] == "import_novel":
            reply = "请上传小说文件 (.txt / .docx / .pdf)，我会帮你解析并入库。"
        elif intent["intent"] == "query":
            reply = f"查询: {intent.get('query_text', message)}（素材库查询功能开发中，可先在素材库页面浏览）"
        else:  # chat
            reply = intent.get("reply", "你好！我是AI漫剧助手，可以帮你生成漫画章节、管理素材和视频。")

        # 5. 存储 assistant 回复
        store.insert(chapter_id, "assistant", reply)

        return {
            "reply": reply,
            "intent": intent["intent"],
            "intent_detail": intent,
            "task_id": task_id,
        }
    finally:
        conn.close()


@router.get("/history")
def chat_history(chapter_id: int | None = None):
    """获取聊天历史."""
    from server.db import ChatStore
    conn = _get_conn()
    try:
        store = ChatStore(conn)
        msgs = store.get_by_chapter(chapter_id)
        return [dict(m) for m in msgs]
    finally:
        conn.close()
