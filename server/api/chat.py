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

        match intent.get("intent"):
            case "generate_chapter":
                cn = intent.get("chapter_num", 1)
                reply = f"收到！要生成第{cn}章，请先在「素材库」左侧上传该章节的小说文件（.txt/.docx/.pdf），然后在 Pipeline 触发。\n\n💡 提示：你可以点击左侧「漫剧素材库」进入上传页面。"
            case "regenerate_character":
                cn = intent.get("character_name", "未知")
                eh = intent.get("extra_hint", "")
                hint_text = f"，微调要求：{eh}" if eh else ""
                reply = f"好的，重新生成「{cn}」的角色图{hint_text}。\n\n请到「漫剧素材库」→ 选择章节 → 人物卡片上点击刷新按钮来触发。"
            case "regenerate_char_design":
                cn = intent.get("character_name", "未知")
                eh = intent.get("extra_hint", "")
                hint_text = f"，设计方向：{eh}" if eh else ""
                reply = f"好的，重新设计「{cn}」的形象{hint_text}。\n\n请到「漫剧素材库」选择该角色，点击刷新按钮触发。你也可以在提示词中写入具体的外观要求。"
            case "regenerate_scene":
                sn = intent.get("scene_name", "未知")
                eh = intent.get("extra_hint", "")
                hint_text = f"，要求：{eh}" if eh else ""
                reply = f"好的，重新生成「{sn}」的场景图{hint_text}。\n\n请到「漫剧素材库」→ 选择章节 → 场景卡片上点击刷新按钮来触发。"
            case "regenerate_video":
                cn = intent.get("chapter_num", "?")
                reply = f"好的，重新生成第{cn}章的视频。\n\n请到「漫剧视频」页选择该章节，点击「重新生成」按钮。"
            case "import_novel":
                reply = "请上传小说文件！（支持 .txt / .docx / .pdf）\n\n📂 推荐方式：点击左侧「漫剧素材库」，在左侧小说列表上方使用上传功能。\n\n✏️ 也可以直接把小说文本粘贴到对话框里，我会帮你保存为章节。"
            case "query":
                reply = f"关于「{intent.get('query_text', message)}」的查询：\n\n你可以在左侧「漫剧素材库」浏览角色、场景和分镜的详细信息。如果想知道特定角色的装扮或场景的光影设置，选对应章节即可看到。"
            case _:
                reply = intent.get("reply", "你好！我是AI漫剧助手 🎬\n\n我可以帮你了解如何使用这个平台：\n• 上传小说：去「漫剧素材库」\n• 看视频：去「漫剧视频」\n• 配Cookie：去「豆包Cookie」\n• 设API Key：去「系统设置」\n\n有什么想了解的？")

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
