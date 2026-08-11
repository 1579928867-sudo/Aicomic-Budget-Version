"""Chat 端点 — 消息发送、历史查询、意图路由."""
import json
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from server.db import get_db

DB_PATH = Path("data/aicomic.db")
router = APIRouter(prefix="/api/chat", tags=["chat"])

# ── 无关问题计数器（模块级，服务重启清零）──
_off_topic_count: int = 0
_OFF_TOPIC_THRESHOLD = 3  # 连续无关提问超过此次数，自动发送能力手册


def _capability_guide() -> str:
    """AI漫剧能力手册 — 向用户说明系统能做什么。"""
    return (
        "📖 **AI漫剧 能力手册**\n\n"
        "我是一个专注于**小说→漫剧视频**的AI助手。以下是我能帮你做的事：\n\n"
        "### 🎬 核心功能\n"
        "1. **导入小说** — 上传 .txt / .docx / .pdf 文件，自动解析入库\n"
        "2. **生成漫剧** — 说「生成第X章」启动全自动管线：\n"
        "   剧本改编 → 角色设计 → 场景设计 → 分镜编排 → AI生图 → AI视频 → 合成成品\n"
        "3. **对话式操控** — 用自然语言操控每个环节\n"
        "   - 「重新生成萧澈的角色图」\n"
        "   - 「生成镜头3的视频」\n"
        "   - 「合成第1章视频」\n"
        "4. **查询进度** — 问「第X章进度如何」「有哪些角色」\n"
        "5. **删除管理** — 在素材库中删除不需要的小说或章节\n\n"
        "### 📚 提示词模板库\n"
        "内置 8 类经过验证的提示词模板：\n"
        "人物三视图 · 场景四视图 · 小说转剧本 · 打斗特效 · 风格参考(52种) · 仿真人出图 · 视频分镜时长\n"
        "对我说「有哪些提示词模板」或「帮我用XX模板生成」即可调用。\n\n"
        "### ⚙️ 前置条件\n"
        "- LLM API Key（DeepSeek / Claude）— 在「系统设置」配置\n"
        "- 豆包/即梦 Cookie — 在「豆包Cookie」页面一键登录\n\n"
        "💡 现在可以对我说「生成第X章」开始制作你的第一部漫剧！"
    )


class ChatSendBody(BaseModel):
    message: str
    chapter_id: int | None = None
    novel_id: int | None = None


@router.get("/status")
def chat_status():
    """检查使用环境是否就绪 — LLM API Key + 豆包 Cookie."""
    from server.config import load_config
    from pathlib import Path as _Path

    # ── LLM Key ──
    try:
        config = load_config()
        backend = config.get("backend", "deepseek")
        api_key = config.get(backend, {}).get("api_key", "")
        llm_ready = bool(api_key)
        llm_detail = f"{backend} API Key 已配置" if llm_ready else f"{backend} API Key 未配置"
    except Exception:
        llm_ready = False
        llm_detail = "无法加载配置"

    # ── 豆包 Cookie ──
    state_file = _Path("data/doubao_state.json")
    cookie_file = _Path("data/doubao_cookies.json")
    cookie_ready = (state_file.exists() and state_file.stat().st_size > 100) or \
                   (cookie_file.exists() and cookie_file.stat().st_size > 10)
    cookie_detail = "豆包 Cookie 已配置" if cookie_ready else "豆包 Cookie 未配置"

    # ── 小说/章节 ──
    db = get_db()
    novel_count = db.execute("SELECT COUNT(*) as c FROM novel").fetchone()["c"]
    chapter_count = db.execute("SELECT COUNT(*) as c FROM chapter").fetchone()["c"]
    db.close()

    all_ready = llm_ready and cookie_ready

    return {
        "llm_ready": llm_ready,
        "llm_detail": llm_detail,
        "cookie_ready": cookie_ready,
        "cookie_detail": cookie_detail,
        "all_ready": all_ready,
        "novel_count": novel_count,
        "chapter_count": chapter_count,
        "next_step": _next_step(all_ready, llm_ready, cookie_ready, novel_count, chapter_count),
    }


def _next_step(all_ready: bool, llm_ready: bool, cookie_ready: bool,
               novel_count: int, chapter_count: int) -> str:
    """生成下一步指引."""
    if all_ready and novel_count == 0:
        return "环境已就绪！请上传小说文件开始生成。"
    if all_ready and chapter_count > 0:
        return "一切就绪！可以直接对我说「生成第X章」开始制作漫剧。"
    if not llm_ready and not cookie_ready:
        return "请先到「系统设置」配置 LLM API Key，再到「豆包Cookie」配置豆包账号。"
    if not llm_ready:
        return "请先到「系统设置」配置 LLM API Key。"
    if not cookie_ready:
        return "请先到「豆包Cookie」配置豆包账号。"
    return "一切就绪！"


def _find_novel_in_message(conn, message: str) -> dict | None:
    """从用户消息中提取书名并查库.

    支持模式:
    - 《书名》 → 精准匹配
    - "XXX 第N章" → 书名部分匹配
    """
    import re
    # 模式1: 《书名》
    m = re.search(r'《(.+?)》', message)
    if m:
        title = m.group(1).strip()
        # 精确匹配
        row = conn.execute("SELECT id, title FROM novel WHERE title = ?", (title,)).fetchone()
        if row: return dict(row)
        # 模糊匹配
        row = conn.execute("SELECT id, title FROM novel WHERE title LIKE ?", (f"%{title[:4]}%",)).fetchone()
        if row: return dict(row)

    # 模式2: "生成XXX第N章" — 提取可能的小说名
    m = re.search(r'生成\s*(.+?)\s*第\s*\d+\s*章', message)
    if m:
        title = m.group(1).strip()
        title = re.sub(r'的视频$', '', title)  # strip "的视频"
        if title and '《' not in title:  # 没被《》包住的
            row = conn.execute("SELECT id, title FROM novel WHERE title LIKE ?", (f"%{title[:4]}%",)).fetchone()
            if row: return dict(row)

    return None


def _fuzzy_novel_match(conn, message: str) -> int | None:
    """模糊匹配小说缩写/简称。将消息分词后在所有小说标题中做 LIKE 匹配。

    如 "情绪" → "看见情绪颜色后，她们都变粉色了"
    如 "邪神" → "逆天邪神"

    只返回一个结果的情况才返回（无歧义）。
    """
    import re as _re
    # Try the longest distinctive substring first
    # Remove common sentence structure words
    cleaned = _re.sub(r'[帮我给让请把的去吗呢吧啊，。！？\s]', '', message)
    # Also strip "生成第X章" / "视频" / "图片" etc
    cleaned = _re.sub(r'生成第?\d*章?', '', cleaned)
    cleaned = _re.sub(r'(视频|图片|角色|场景|分镜|合成|制作|漫剧|镜头\d*)', '', cleaned)

    if len(cleaned) < 2:
        return None

    all_novels = conn.execute("SELECT id, title FROM novel ORDER BY id").fetchall()
    matches = []
    for n in all_novels:
        title = n["title"]
        # Match: cleaned is substring of title, or title is substring of cleaned
        if cleaned in title or (len(cleaned) >= 3 and any(
            cleaned[i:i+2] in title for i in range(len(cleaned) - 1)
        )):
            matches.append(n["id"])

    if len(matches) == 1:
        return matches[0]
    return None


def _find_chapter_num(conn, chapter_id: int) -> int:
    """Get chapter_num for a chapter_id."""
    row = conn.execute("SELECT chapter_num FROM chapter WHERE id=?", (chapter_id,)).fetchone()
    return row["chapter_num"] if row else chapter_id


def _find_script_for_chapter(conn, chapter_id: int) -> int | None:
    """Get the latest script_id for a chapter."""
    row = conn.execute(
        "SELECT id FROM script WHERE chapter_id = ? ORDER BY id DESC LIMIT 1",
        (chapter_id,),
    ).fetchone()
    return row["id"] if row else None


def _resolve_chapter_for_shot(
    conn, shot_num: int, chapter_id: int | None, novel_id: int | None
) -> tuple[int | None, str]:
    """Resolve which chapter a shot number belongs to. Returns (chapter_id, novel_title).

    Priority:
    1. If chapter_id provided by frontend → use it (verify shot exists)
    2. If novel_id provided → search its chapters for the shot
    3. Most recent task's chapter → search there
    4. Global search → return only if exactly one match
    """
    # Priority 1: Explicit chapter context from frontend
    if chapter_id:
        row = conn.execute(
            "SELECT 1 FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=? AND ss.shot_num=?",
            (chapter_id, shot_num),
        ).fetchone()
        if row:
            novel_row = conn.execute(
                "SELECT n.title FROM novel n JOIN chapter c ON c.novel_id=n.id WHERE c.id=?",
                (chapter_id,),
            ).fetchone()
            return chapter_id, novel_row["title"] if novel_row else ""
        return None, ""

    # Priority 2: Novel context from frontend — search its chapters
    if novel_id:
        row = conn.execute(
            """SELECT c.id, n.title FROM chapter c JOIN novel n ON n.id=c.novel_id
               JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               WHERE c.novel_id=? AND ss.shot_num=? LIMIT 1""",
            (novel_id, shot_num),
        ).fetchone()
        if row:
            return row["id"], row["title"]

    # Priority 3: Most recent pipeline task's chapter
    task_row = conn.execute(
        "SELECT chapter_id FROM task WHERE chapter_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if task_row:
        cid = task_row["chapter_id"]
        row = conn.execute(
            "SELECT 1 FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=? AND ss.shot_num=?",
            (cid, shot_num),
        ).fetchone()
        if row:
            novel_row = conn.execute(
                "SELECT n.title FROM novel n JOIN chapter c ON c.novel_id=n.id WHERE c.id=?",
                (cid,),
            ).fetchone()
            return cid, novel_row["title"] if novel_row else ""

    # Priority 4: Global — only if exactly one chapter has this shot
    rows = conn.execute(
        """SELECT c.id, n.title FROM chapter c JOIN novel n ON n.id=c.novel_id
           JOIN script s ON s.chapter_id=c.id
           JOIN storyboard_shot ss ON ss.script_id=s.id
           WHERE ss.shot_num=?""",
        (shot_num,),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]["id"], rows[0]["title"]

    return None, ""


def _resolve_chapter_for_character(conn, character_name: str, novel_id: int | None) -> int | None:
    """Find which chapter a character belongs to. Uses novel_id if provided, else most recent task."""
    import json as _json

    # ── Primary: shot_character_outfit junction table ──
    def _find_in_junction(cids: list[int] | None = None):
        extra = "AND c.id = ?" if cids else ""
        params = [character_name] + (cids if cids else [])
        return conn.execute(
            f"""SELECT c.id FROM chapter c JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               JOIN shot_character_outfit sco ON sco.shot_id=ss.id
               JOIN character_card cc ON cc.id=sco.character_id
               WHERE cc.name=? {extra} LIMIT 1""",
            tuple(params),
        ).fetchone()

    # ── Fallback: storyboard_shot.char_ids JSON column ──
    def _find_in_char_ids(cids: list[int] | None = None):
        # Get character's ID first
        cc = conn.execute("SELECT id FROM character_card WHERE name=?", (character_name,)).fetchone()
        if not cc: return None
        char_id = cc["id"]
        # Scan all shots' char_ids for this character
        extra = "AND c.id = ?" if cids else ""
        params = cids if cids else []
        rows = conn.execute(
            f"""SELECT c.id, ss.char_ids FROM chapter c
               JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               WHERE ss.char_ids IS NOT NULL AND ss.char_ids != '' {extra}""",
            tuple(params),
        ).fetchall()
        for row in rows:
            try:
                cids_list = _json.loads(row["char_ids"])
                if char_id in cids_list:
                    return row["id"]
            except Exception:
                pass
        return None

    if novel_id:
        # Get chapter IDs for this novel
        ch_rows = conn.execute("SELECT id FROM chapter WHERE novel_id=?", (novel_id,)).fetchall()
        ch_ids = [r["id"] for r in ch_rows]
        if ch_ids:
            row = _find_in_junction(ch_ids) or _find_in_char_ids(ch_ids)
            if row: return row[0] if isinstance(row, dict) else row

    # Most recent task's chapter
    task_row = conn.execute(
        "SELECT chapter_id FROM task WHERE chapter_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if task_row:
        cid = task_row["chapter_id"]
        row = _find_in_junction([cid]) or _find_in_char_ids([cid])
        if row: return cid

    # Global search — single match only
    j_rows = conn.execute(
        """SELECT DISTINCT c.id FROM chapter c JOIN script s ON s.chapter_id=c.id
           JOIN storyboard_shot ss ON ss.script_id=s.id
           JOIN shot_character_outfit sco ON sco.shot_id=ss.id
           JOIN character_card cc ON cc.id=sco.character_id
           WHERE cc.name=?""",
        (character_name,),
    ).fetchall()
    if len(j_rows) == 1: return j_rows[0]["id"]

    # Fallback global: char_ids JSON scan
    cc = conn.execute("SELECT id FROM character_card WHERE name=?", (character_name,)).fetchone()
    if cc:
        char_id = cc["id"]
        matches = set()
        rows = conn.execute(
            """SELECT c.id, ss.char_ids FROM chapter c
               JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               WHERE ss.char_ids IS NOT NULL AND ss.char_ids != ''"""
        ).fetchall()
        for row in rows:
            try:
                if char_id in _json.loads(row["char_ids"]):
                    matches.add(row["id"])
            except Exception:
                pass
        if len(matches) == 1:
            return list(matches)[0]
        elif len(matches) > 1:
            # Ambiguous — prefer most recent task chapter
            if task_row and task_row["chapter_id"] in matches:
                return task_row["chapter_id"]

    return None


def _resolve_chapter_for_scene(conn, scene_name: str, novel_id: int | None) -> int | None:
    """Find which chapter a scene belongs to."""
    if novel_id:
        row = conn.execute(
            """SELECT c.id FROM chapter c JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               JOIN scene_card sc ON sc.id=ss.scene_id
               WHERE c.novel_id=? AND sc.name=? LIMIT 1""",
            (novel_id, scene_name),
        ).fetchone()
        if row: return row[0]

    # Most recent task
    task_row = conn.execute(
        "SELECT chapter_id FROM task WHERE chapter_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if task_row:
        cid = task_row["chapter_id"]
        row = conn.execute(
            """SELECT 1 FROM storyboard_shot ss JOIN script s ON s.id=ss.script_id
               JOIN scene_card sc ON sc.id=ss.scene_id
               WHERE s.chapter_id=? AND sc.name=? LIMIT 1""",
            (cid, scene_name),
        ).fetchone()
        if row: return cid

    # Global single match — exact first, then LIKE
    rows = conn.execute(
        """SELECT DISTINCT c.id FROM chapter c JOIN script s ON s.chapter_id=c.id
           JOIN storyboard_shot ss ON ss.script_id=s.id
           JOIN scene_card sc ON sc.id=ss.scene_id WHERE sc.name=?""",
        (scene_name,),
    ).fetchall()
    if len(rows) == 1: return rows[0][0]
    if len(rows) == 0:
        # Try LIKE matching (user may say "人民广场" when DB has "人民广场·侧边")
        rows = conn.execute(
            """SELECT DISTINCT c.id FROM chapter c JOIN script s ON s.chapter_id=c.id
               JOIN storyboard_shot ss ON ss.script_id=s.id
               JOIN scene_card sc ON sc.id=ss.scene_id WHERE sc.name LIKE ?""",
            (f"%{scene_name}%",),
        ).fetchall()
        if len(rows) == 1: return rows[0][0]
    return None


def _count_chapters_for_shot(conn, shot_num: int) -> int:
    """Count how many chapters have a given shot number (for ambiguity detection)."""
    row = conn.execute(
        """SELECT COUNT(DISTINCT c.id) FROM chapter c
           JOIN script s ON s.chapter_id=c.id
           JOIN storyboard_shot ss ON ss.script_id=s.id
           WHERE ss.shot_num=?""",
        (shot_num,),
    ).fetchone()
    return row[0] if row else 0


def _find_chapter_for_intent(conn, novel_id: int | None, chapter_num: int) -> tuple[int | None, int]:
    """为意图查找匹配的 chapter_id. 优先当前 novel, 其次全局搜索.

    Returns:
        (chapter_id, ambiguity_count) — ambiguity_count > 1 表示有多部小说同时有该章节。
    """
    if novel_id:
        row = conn.execute(
            "SELECT id FROM chapter WHERE novel_id = ? AND chapter_num = ?",
            (novel_id, chapter_num),
        ).fetchone()
        if row: return row["id"], 1
        # novel_id 指定了但该章节不存在 → 立即返回 None，不全局搜索
        return None, 0

    # 全局搜索（仅当 novel_id 未指定时）
    rows = conn.execute(
        "SELECT id, novel_id FROM chapter WHERE chapter_num = ? ORDER BY id",
        (chapter_num,),
    ).fetchall()
    if not rows:
        return None, 0
    if len(rows) == 1:
        return rows[0]["id"], 1
    # 多义 — 有多部小说同时有该章节号，不静默选择，让调用者处理
    return None, len(rows)


@router.post("/send")
async def chat_send(body: ChatSendBody):
    global _off_topic_count
    message = body.message; chapter_id = body.chapter_id; novel_id = body.novel_id
    from server.db import ChatStore
    from server.intent import parse_intent_with_llm
    from server.config import load_config, build_llm_client

    conn = get_db()
    try:
        store = ChatStore(conn)
        store.insert(chapter_id, "user", message)

        context = {}

        # ── 自动检测消息中提到的书名 ──
        matched_novel = _find_novel_in_message(conn, message)
        if matched_novel and not novel_id:
            novel_id = matched_novel["id"]
            context["message_novel"] = matched_novel

        # ── 模糊匹配：缩写/简称匹配（如"情绪"→"看见情绪颜色后..."）──
        if not matched_novel and not novel_id:
            novel_id = _fuzzy_novel_match(conn, message)
            if novel_id:
                novel = conn.execute("SELECT id, title FROM novel WHERE id = ?", (novel_id,)).fetchone()
                if novel:
                    context["novel"] = dict(novel)
                    chapters = conn.execute("SELECT id, chapter_num FROM chapter WHERE novel_id = ? ORDER BY chapter_num", (novel_id,)).fetchall()
                    context["chapters"] = [dict(c) for c in chapters]

        if novel_id:
            novel = conn.execute("SELECT id, title FROM novel WHERE id = ?", (novel_id,)).fetchone()
            if novel:
                context["novel"] = dict(novel)
                chapters = conn.execute("SELECT id, chapter_num FROM chapter WHERE novel_id = ? ORDER BY chapter_num", (novel_id,)).fetchall()
                context["chapters"] = [dict(c) for c in chapters]

        if chapter_id:
            # 填充角色/场景上下文 (fallback: 联结表 → char_ids 直接解析)
            chars = _get_chapter_characters(conn, chapter_id)
            context["characters"] = chars
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
            from server.error_i18n import translate_error
            friendly = translate_error(str(e))
            intent = {"intent": "chat", "reply": friendly}

        reply = ""
        task_id = None
        import asyncio as _asyncio

        # ── 知识库注入：根据意图自动附加 Prompt 模板参考 ──
        kb_context = ""
        try:
            from src.aicomic.prompt_kb import get_kb
            kb = get_kb()
            # 为生成类意图自动匹配模板
            gen_intents = {
                "generate_chapter", "regenerate_character", "regenerate_char_design",
                "regenerate_scene", "regenerate_video", "compose_video", "retry_shot_video",
            }
            if intent.get("intent") in gen_intents:
                kb_context = kb.context_for_intent(intent["intent"])
        except Exception:
            pass  # KB 不可用时静默跳过

        # ── 无关问题计数器：非 off_topic 意图时清零 ──
        if intent.get("intent") != "off_topic":
            _off_topic_count = 0

        match intent.get("intent"):
            case "retry_shot_video":
                sn = intent.get("shot_num", 1)
                target_ch_id, novel_title = _resolve_chapter_for_shot(conn, sn, chapter_id, novel_id)
                if target_ch_id:
                    try:
                        from server.api.agents import agent_runner as _ar, task_store as _ts
                        if _ar and _ts:
                            tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "shot-video-generator", "shot_num": sn}))
                            _asyncio.create_task(_ar.run_in_background("shot-video-generator",
                                {"chapter_id": target_ch_id, "script_id": _find_script_for_chapter(conn, target_ch_id), "shot_num": sn, "max_clips_per_run": 0}, tid))
                            task_id = tid
                            label = f"《{novel_title}》" if novel_title else ""
                            reply = f"🎬 正在生成{label}镜头 {sn} 的视频…\n\n📋 任务 ID: `{tid}`\n\n💡 提示：如果再次被审核拦截，可以尝试对我说「重新生成角色图，风格改为动漫插画」来降低写实度。"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 启动镜头视频生成失败：{e}"
                else:
                    # Couldn't resolve which chapter
                    all_chapters = _count_chapters_for_shot(conn, sn)
                    if all_chapters == 0:
                        reply = f"没有找到镜头 {sn}。请先在素材库中确认分镜已生成。\n\n💡 提示：分镜需要先完成「剧本与设计」阶段才会创建。"
                    else:
                        reply = f"镜头 {sn} 存在于多个章节中。请告诉我具体是哪部小说？（例如「《逆天邪神》生成镜头{sn}」）"

            case "compose_video":
                cn = intent.get("chapter_num")
                # Resolve chapter: from intent → frontend context → most recent task
                target_ch_id = None
                if cn:
                    target_ch_id, _amb = _find_chapter_for_intent(conn, novel_id, cn)
                if not target_ch_id and chapter_id:
                    target_ch_id = chapter_id
                if not target_ch_id:
                    # Most recent task
                    task_row = conn.execute(
                        "SELECT chapter_id FROM task WHERE chapter_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"
                    ).fetchone()
                    if task_row: target_ch_id = task_row["chapter_id"]

                if target_ch_id:
                    try:
                        from server.api.agents import agent_runner as _ar, task_store as _ts
                        if _ar and _ts:
                            tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "video-composer"}))
                            _asyncio.create_task(_ar.run_in_background("video-composer",
                                {"chapter_id": target_ch_id, "script_id": _find_script_for_chapter(conn, target_ch_id)}, tid))
                            task_id = tid
                            novel_title = context.get("novel", {}).get("title", "")
                            label = f"《{novel_title}》" if novel_title else ""
                            ch_num = _find_chapter_num(conn, target_ch_id)
                            reply = f"🎬 正在合成{label}第{ch_num}章视频…\n\n📋 任务 ID: `{tid}`\n⏳ 合并 mp4 片段需要 1-3 分钟…"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 启动视频合成失败：{e}"
                else:
                    reply = "没有找到需要合成的章节。请先在素材库中选择一个章节，或对我说「合成第X章」。"

            case "generate_chapter":
                cn = intent.get("chapter_num", 1)
                target_ch_id, ambiguity = _find_chapter_for_intent(conn, novel_id, cn)

                # Detect mode: "自动" or "一口气" → auto, default → interactive
                is_auto = any(kw in message for kw in ["自动", "一口气", "不用问我", "直接全部"])
                mode = "auto" if is_auto else "interactive"

                # ── 多小说歧义保护 ──
                if not target_ch_id and ambiguity > 1:
                    # 找出所有有该章节号的小说
                    amb_rows = conn.execute(
                        """SELECT n.title, c.id FROM chapter c
                           JOIN novel n ON n.id = c.novel_id
                           WHERE c.chapter_num = ?""",
                        (cn,),
                    ).fetchall()
                    novel_names = "、".join(f"《{r['title']}》" for r in amb_rows)
                    reply = (
                        f"⚠️ 第{cn}章在 {ambiguity} 部小说中都存在（{novel_names}）。\n\n"
                        f"请明确告诉我要生成哪部小说的章节，例如「生成《逆天邪神》第{cn}章」。\n\n"
                        f"💡 也可以在左侧「漫剧素材库」先选择对应的小说和章节。"
                    )
                    store.insert(chapter_id, "assistant", reply)
                    return {"reply": reply, "intent": intent["intent"], "intent_detail": intent, "task_id": task_id}

                if target_ch_id:
                    # ── 验证章节原文非空 ──
                    ch_row = conn.execute(
                        "SELECT raw_text, status FROM chapter WHERE id = ?", (target_ch_id,)
                    ).fetchone()
                    if not ch_row or not (ch_row["raw_text"] or "").strip():
                        novel_title = context.get("novel", {}).get("title", "")
                        label = f"《{novel_title}》" if novel_title else ""
                        reply = (
                            f"⚠️ {label}第{cn}章的原文内容为空。\n\n"
                            f"可能的原因：\n"
                            f"• 章节已被删除\n"
                            f"• 上传时解析失败\n\n"
                            f"💡 请点击输入框旁的 📎 重新上传第{cn}章的小说文件，上传后再对我说「生成第{cn}章」。"
                        )
                        store.insert(chapter_id, "assistant", reply)
                        return {"reply": reply, "intent": intent["intent"], "intent_detail": intent, "task_id": task_id}
                    # ── 验证完毕 ──
                    try:
                        from server.api.pipeline import pipeline_runner as _pr, task_store as _ts
                        if _pr and _ts:
                            with_images = True
                            # Default: with_video=True. Only skip if user explicitly says NO video.
                            with_video = True
                            if any(kw in message for kw in ["不要视频", "不用视频", "不生成视频", "跳过视频", "只图片", "只要图片", "只生成图片", "不加视频"]):
                                with_video = False
                            elif "视频" in message:
                                with_video = True
                            elif any(kw in message for kw in ["只生成剧本", "只要剧本", "只到分镜", "不做视频"]):
                                with_video = False

                            tid = _ts.create("pipeline", chapter_id=target_ch_id,
                                params=json.dumps({"with_images": with_images, "with_video": with_video, "mode": mode}))
                            _asyncio.create_task(_pr.run_in_background(target_ch_id, "", with_images, with_video, tid, mode))
                            task_id = tid

                            novel_title = context.get("novel", {}).get("title", "")
                            label = f"《{novel_title}》" if novel_title else ""
                            mode_label = "（自动模式）" if is_auto else "（逐步确认模式）"
                            reply = f"🚀 已启动{label}第{cn}章生成 {mode_label}\n\n📋 任务 ID: `{tid}`\n⏳ 进度实时推送中…"
                            if kb_context:
                                reply += "\n\n📚 检测到提示词模板库可用。你可以对我说「用XXX模板重新生成」来应用特定风格（如「用打斗画面模板生成战斗镜头」）。"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 启动生成失败：{e}"
                else:
                    novel_title = context.get("novel", {}).get("title", "")
                    label = f"《{novel_title}》" if novel_title else ""
                    reply = f"还没有找到{label}第{cn}章。\n\n💡 请点击输入框旁的 📎 按钮上传第{cn}章的小说文件（.txt/.docx/.pdf），上传后对我说「生成第{cn}章」即可。"
            case "regenerate_character":
                cn = intent.get("character_name", "未知")
                eh = intent.get("extra_hint", "")
                cid = intent.get("character_id")
                if not cid and context.get("characters"):
                    for c in context["characters"]:
                        if c.get("name") == cn: cid = c["id"]; break
                if not cid:
                    row = conn.execute("SELECT id FROM character_card WHERE name = ?", (cn,)).fetchone()
                    if row: cid = row["id"]
                target_ch_id = chapter_id
                if not target_ch_id and cid:
                    target_ch_id = _resolve_chapter_for_character(conn, cn, novel_id)
                if cid and target_ch_id:
                    try:
                        from server.api.agents import agent_runner as _ar, task_store as _ts
                        if _ar and _ts:
                            # Resolve raw_text for char-designer
                            ch_row = conn.execute("SELECT raw_text FROM chapter WHERE id=?", (target_ch_id,)).fetchone()
                            raw_text = ch_row["raw_text"] if ch_row else ""
                            # Step 1: char-designer 重写设计提示词（统一CG风格 + force 跳过幂等）
                            cd_tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "char-designer", "character": cn}))
                            _asyncio.create_task(_ar.run_in_background("char-designer",
                                {"chapter_id": target_ch_id, "raw_text": raw_text, "characters": [cn], "force": True}, cd_tid))
                            # Step 2: image-generator 生成新图片（等 char-designer 完成后再跑）
                            img_tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "image-generator", "target_type": "character", "target_id": cid, "extra": eh}))
                            _asyncio.create_task(_ar.run_in_background("image-generator",
                                {"chapter_id": target_ch_id, "target_type": "character", "target_id": cid, "extra": eh}, img_tid))
                            task_id = img_tid
                            hint_text = f"，微调要求：{eh}" if eh else ""
                            reply = f"🎨 正在用统一 CG 风格重新设计并生成「{cn}」的角色图{hint_text}\n\n📋 任务 ID: `{img_tid}`\n⏳ 先重写设计提示词，再生成图片..."
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 重新生成失败：{e}"
                else:
                    reply = f"好的，重新生成「{cn}」的角色图。" + (f" 微调要求：{eh}" if eh else "") + "\n\n💡 请先在「漫剧素材库」选择包含该角色的章节，然后再告诉我。"
            case "regenerate_char_design":
                cn = intent.get("character_name", "未知")
                eh = intent.get("extra_hint", "")
                cid = intent.get("character_id")
                if not cid and context.get("characters"):
                    for c in context["characters"]:
                        if c.get("name") == cn:
                            cid = c["id"]
                            break
                if not cid:
                    row = conn.execute("SELECT id FROM character_card WHERE name = ?", (cn,)).fetchone()
                    if row: cid = row["id"]
                target_ch_id = chapter_id
                if not target_ch_id and cid:
                    target_ch_id = _resolve_chapter_for_character(conn, cn, novel_id)
                if cid and target_ch_id:
                    try:
                        from server.api.agents import agent_runner as _ar, task_store as _ts
                        if _ar and _ts:
                            tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "char-designer", "target_type": "character", "target_id": cid, "extra": eh}))
                            _asyncio.create_task(_ar.run_in_background("char-designer",
                                {"chapter_id": target_ch_id, "target_type": "character", "target_id": cid, "extra": eh}, tid))
                            task_id = tid
                            hint_text = f"，设计方向：{eh}" if eh else ""
                            reply = f"🖌️ 正在重新设计「{cn}」的形象{hint_text}\n\n📋 任务 ID: `{tid}`"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 重新设计失败：{e}"
                else:
                    reply = f"好的，重新设计「{cn}」的形象。" + (f" 设计方向：{eh}" if eh else "") + "\n\n💡 请先在「漫剧素材库」选择包含该角色的章节，然后再告诉我。"
            case "regenerate_scene":
                sn = intent.get("scene_name", "未知")
                eh = intent.get("extra_hint", "")
                sid = intent.get("scene_id")
                if not sid and context.get("scenes"):
                    for s in context["scenes"]:
                        if s.get("name") == sn:
                            sid = s["id"]
                            break
                if not sid:
                    row = conn.execute("SELECT id FROM scene_card WHERE name = ?", (sn,)).fetchone()
                    if row: sid = row["id"]
                # Smart chapter resolution
                target_ch_id = chapter_id
                if not target_ch_id and sid:
                    target_ch_id = _resolve_chapter_for_scene(conn, sn, novel_id)
                if sid and target_ch_id:
                    try:
                        from server.api.agents import agent_runner as _ar, task_store as _ts
                        if _ar and _ts:
                            tid = _ts.create("agent", chapter_id=target_ch_id,
                                params=json.dumps({"agent": "image-generator", "target_type": "scene", "target_id": sid, "extra": eh}))
                            _asyncio.create_task(_ar.run_in_background("image-generator",
                                {"chapter_id": target_ch_id, "target_type": "scene", "target_id": sid, "extra": eh}, tid))
                            task_id = tid
                            hint_text = f"，要求：{eh}" if eh else ""
                            reply = f"🏞️ 正在重新生成「{sn}」的场景图{hint_text}\n\n📋 任务 ID: `{tid}`"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 重新生成失败：{e}"
                else:
                    reply = f"好的，重新生成「{sn}」的场景图。" + (f" 要求：{eh}" if eh else "") + "\n\n💡 请先在「漫剧素材库」选择包含该场景的章节，然后再告诉我。"
            case "regenerate_video":
                cn = intent.get("chapter_num", 1)
                target_ch_id, _amb = _find_chapter_for_intent(conn, novel_id, cn)

                if target_ch_id:
                    try:
                        from server.api.pipeline import pipeline_runner as _pr, task_store as _ts
                        if _pr and _ts:
                            tid = _ts.create("pipeline", chapter_id=target_ch_id,
                                params=json.dumps({"with_images": False, "with_video": True}))
                            _asyncio.create_task(_pr.run_in_background(target_ch_id, "", False, True, tid))
                            task_id = tid

                            novel_title = context.get("novel", {}).get("title", "")
                            label = f"《{novel_title}》" if novel_title else ""
                            reply = f"🎬 正在重新生成{label}第{cn}章视频！\n\n📋 任务 ID: `{tid}`\n⏳ 这可能需要几分钟…"
                        else:
                            reply = f"⚠️ 生成引擎未就绪。请先在「系统设置」页配置 LLM API Key。"
                    except Exception as e:
                        reply = f"❌ 重新生成视频失败：{e}"
                else:
                    reply = f"还没找到第{cn}章。\n\n💡 请先在「漫剧素材库」选择该章节，确认章节已上传，然后再告诉我。"
            case "import_novel":
                reply = "📂 请直接上传小说文件！\n\n点击输入框旁边的 📎 按钮，选择你的 .txt / .docx / .pdf 文件，我会自动帮你解析入库。"
            case "delete_novel_or_chapter":
                dt = intent.get("target_type", "")
                dn = intent.get("target_name", "")
                dcn = intent.get("chapter_num")
                # Resolve: target_name might be a novel title or chapter number
                if dt == "novel" or (dn and not dcn):
                    # Find novel by name
                    rows = conn.execute(
                        "SELECT id, title FROM novel WHERE title LIKE ?",
                        (f"%{dn}%",),
                    ).fetchall()
                    if len(rows) == 1:
                        store.insert(chapter_id, "assistant",
                            f"📋 确认要删除《{rows[0]['title']}》及其所有章节和素材吗？\n\n⚠️ 此操作不可撤销。请回复「确认删除《{rows[0]['title']}》」来确认，或回复「取消」。")
                        reply = f"📋 请确认：是否删除《{rows[0]['title']}》？\n\n⚠️ 此操作不可撤销。请在素材库中操作，或回复「确认」后我帮你执行。"
                    elif len(rows) > 1:
                        names = "、".join(f"《{r['title']}》" for r in rows)
                        reply = f"找到多部匹配的小说：{names}\n\n请告诉我要删除哪一部。"
                    else:
                        reply = f"没有找到「{dn}」这部小说。\n\n💡 你可以在「漫剧素材库」页面 hover 小说行显示删除按钮。"
                elif dt == "chapter" or dcn:
                    target_ch_id, amb = _find_chapter_for_intent(conn, novel_id, dcn or 1)
                    if target_ch_id:
                        ch_row = conn.execute(
                            "SELECT n.title, c.chapter_num FROM chapter c JOIN novel n ON n.id=c.novel_id WHERE c.id=?",
                            (target_ch_id,),
                        ).fetchone()
                        if ch_row:
                            reply = (
                                f"📋 确认删除《{ch_row['title']}》第{ch_row['chapter_num']}章吗？\n\n"
                                f"⚠️ 此操作不可撤销，会同时删除该章节的所有角色/场景/分镜/视频。\n\n"
                                f"💡 请在「漫剧素材库」页面操作——hover 章节行右侧会出现 🗑 删除按钮，点击确认即可。"
                            )
                        else:
                            reply = "无法找到该章节。可能已被删除。"
                    elif amb > 1:
                        reply = f"第{dcn}章存在于多部小说中，请先指定是哪部小说。"
                    else:
                        reply = f"没有找到第{dcn}章。\n\n💡 你可以在「漫剧素材库」页面左侧选择小说和章节后，hover 章节行显示删除按钮。"
                else:
                    reply = f"你想删除什么？请告诉我具体的小说名或章节号。\n\n💡 也可以直接在「漫剧素材库」页面操作。"
            case "query":
                q = intent.get('query_text', message)
                # Step 1: Try DB factual questions
                info = _query_info(conn, q, novel_id, chapter_id, context)
                if info:
                    reply = info
                else:
                    # Step 2: Try knowledge base (prompt templates, style references)
                    kb_reply = _query_kb(q)
                    if kb_reply:
                        reply = kb_reply
                    else:
                        reply = f"关于「{q}」的查询：\n\n你可以在左侧「漫剧素材库」浏览角色、场景和分镜的详细信息。也可以直接对我说「生成第X章」开始制作漫剧。"
            case "off_topic":
                _off_topic_count += 1
                off_reply = intent.get("reply", "")
                if not off_reply:
                    off_reply = "抱歉，我是AI漫剧助手，专注于帮你将小说变成漫剧视频。关于这个话题我帮不上忙。\n\n有什么漫剧相关的需求吗？比如上传新小说、生成角色图、制作视频等。"
                reply = off_reply
                if _off_topic_count >= _OFF_TOPIC_THRESHOLD:
                    reply += "\n\n---\n\n" + _capability_guide()
                    _off_topic_count = 0  # reset after showing guide
                store.insert(chapter_id, "assistant", reply)
                return {"reply": reply, "intent": intent["intent"], "intent_detail": intent, "task_id": task_id}
            case "chat":
                reply = intent.get("reply", "你好！我是AI漫剧助手 🎬\n\n我可以帮你：\n• 上传小说：点击输入框旁 📎\n• 生成漫剧：说「生成第X章」\n• 重新生成角色图：说「重新生成XXX的图」\n\n有什么想了解的？")
            case _:
                reply = intent.get("reply", "你好！我是AI漫剧助手 🎬\n\n我可以帮你：\n• 上传小说：点击输入框旁 📎\n• 生成漫剧：说「生成第X章」\n• 重新生成角色图：说「重新生成XXX的图」\n\n有什么想了解的？")

        store.insert(chapter_id, "assistant", reply)
        return {"reply": reply, "intent": intent["intent"], "intent_detail": intent, "task_id": task_id}
    finally:
        conn.close()


def _query_info(conn, question: str, novel_id: int | None, chapter_id: int | None, context: dict) -> str | None:
    """Try to answer factual questions about novels/chapters/characters from the DB."""
    import re

    # "有哪些小说"/"小说列表"
    if any(kw in question for kw in ["有哪些小说", "小说列表", "所有小说", "几部小说"]):
        rows = conn.execute("SELECT title, author FROM novel ORDER BY id").fetchall()
        if rows:
            lines = [f"📚 共有 {len(rows)} 部小说："]
            for r in rows:
                author = f"（{r['author']}）" if r['author'] else ""
                lines.append(f"  • 《{r['title']}》{author}")
            return "\n".join(lines)
        return "还没有导入任何小说。请点击输入框旁的 📎 上传 .txt/.docx/.pdf 文件。"

    # "有哪些章"/"第X章" + status
    if "有哪些章" in question or "章节列表" in question:
        if chapter_id or novel_id:
            nid = novel_id
            if not nid and chapter_id:
                nr = conn.execute("SELECT novel_id FROM chapter WHERE id=?", (chapter_id,)).fetchone()
                if nr: nid = nr["novel_id"]
            if nid:
                rows = conn.execute(
                    "SELECT chapter_num, status FROM chapter WHERE novel_id=? ORDER BY chapter_num", (nid,)
                ).fetchall()
                if rows:
                    novel = conn.execute("SELECT title FROM novel WHERE id=?", (nid,)).fetchone()
                    lines = [f"📖 《{novel['title']}》共有 {len(rows)} 章："] if novel else [f"📖 共有 {len(rows)} 章："]
                    for r in rows:
                        status_map = {"idle": "📝未生成", "processing": "⏳生成中", "done": "✅已完成"}
                        s = status_map.get(r["status"], r["status"])
                        lines.append(f"  • 第{r['chapter_num']}章 — {s}")
                    return "\n".join(lines)
        return None

    # "有哪些角色" / "角色列表"
    if "有哪些角色" in question or "角色列表" in question:
        if chapter_id:
            chars = _get_chapter_characters(conn, chapter_id)
            if chars:
                lines = [f"🎭 当前章节共有 {len(chars)} 个角色："]
                for c in chars:
                    lines.append(f"  • {c['name']} (id={c['id']})")
                return "\n".join(lines)
        return None

    # "有哪些场景"
    if "有哪些场景" in question or "场景列表" in question:
        if chapter_id:
            scenes = conn.execute("""SELECT DISTINCT sc.name FROM scene_card sc
                JOIN storyboard_shot ss ON ss.scene_id=sc.id
                JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""", (chapter_id,)).fetchall()
            if scenes:
                lines = [f"🏞️ 当前章节共有 {len(scenes)} 个场景："]
                for s in scenes:
                    lines.append(f"  • {s['name']}")
                return "\n".join(lines)
        return None

    # "进度" / "状态" / "生成完了吗"
    if any(kw in question for kw in ["进度", "状态", "好了吗", "完了吗", "完成了"]):
        if chapter_id:
            audit = _mini_audit(conn, chapter_id)
            lines = ["📊 当前章节进度："]
            for k, v in audit.items():
                lines.append(f"  • {k}: {v}")
            return "\n".join(lines)
        return None

    # "第X章有没有XX" — generic matching
    m = re.search(r'第\s*(\d+)\s*章', question)
    if m:
        cn = int(m.group(1))
        ch_id, _amb = _find_chapter_for_intent(conn, novel_id, cn)
        if ch_id:
            audit = _mini_audit(conn, ch_id)
            lines = [f"📊 第{cn}章进度："]
            for k, v in audit.items():
                lines.append(f"  • {k}: {v}")
            return "\n".join(lines)

    return None


def _mini_audit(conn, chapter_id: int) -> dict:
    """Lightweight audit for chat replies."""
    import os, json
    # Script
    script = bool(conn.execute("SELECT id FROM script WHERE chapter_id=?", (chapter_id,)).fetchone())
    # Characters with images
    char_done = conn.execute("""
        SELECT COUNT(*) FROM character_outfit co
        JOIN character_card cc ON cc.id=co.character_id
        WHERE co.prompt!='' AND co.image_path!='' AND co.character_id IN (
            SELECT DISTINCT sco.character_id FROM shot_character_outfit sco
            JOIN storyboard_shot ss ON ss.id=sco.shot_id
            JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?
        )""", (chapter_id,)).fetchone()[0]
    char_total = conn.execute("""
        SELECT COUNT(DISTINCT sco.character_id) FROM shot_character_outfit sco
        JOIN storyboard_shot ss ON ss.id=sco.shot_id
        JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?
    """, (chapter_id,)).fetchone()[0]
    shots = conn.execute("""SELECT COUNT(*) FROM storyboard_shot ss
        JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""", (chapter_id,)).fetchone()[0]
    clips = conn.execute("""SELECT COUNT(*) FROM video_clip vc
        JOIN storyboard_shot ss ON ss.id=vc.shot_id
        JOIN script s ON s.id=ss.script_id WHERE s.chapter_id=?""", (chapter_id,)).fetchone()[0]
    final = bool(conn.execute(
        "SELECT file_path FROM final_video WHERE chapter_id=? AND file_size>0 ORDER BY id DESC LIMIT 1",
        (chapter_id,)).fetchone())

    return {
        "剧本": "✓" if script else "✗",
        "角色图": f"{char_done}/{char_total or '?'}",
        "分镜": str(shots),
        "视频片段": str(clips),
        "成品视频": "✓" if final else "✗",
    }


def _get_chapter_characters(conn, chapter_id: int) -> list[dict]:
    """获取章节角色列表. 优先联结表, 降级 char_ids."""
    rows = conn.execute("""SELECT DISTINCT cc.id, cc.name FROM character_card cc
        INNER JOIN shot_character_outfit sco ON sco.character_id = cc.id
        INNER JOIN storyboard_shot ss ON ss.id = sco.shot_id
        INNER JOIN script s ON s.id = ss.script_id
        WHERE s.chapter_id = ?""", (chapter_id,)).fetchall()
    if rows:
        return [dict(c) for c in rows]

    # fallback
    shot_rows = conn.execute("""SELECT ss.char_ids FROM storyboard_shot ss
        INNER JOIN script s ON s.id = ss.script_id
        WHERE s.chapter_id = ?""", (chapter_id,)).fetchall()
    seen_ids = set()
    for sr in shot_rows:
        try:
            ids = json.loads(sr["char_ids"] or "[]")
            for cid in ids:
                if isinstance(cid, int): seen_ids.add(cid)
        except (json.JSONDecodeError, TypeError): pass
    if seen_ids:
        placeholders = ",".join("?" * len(seen_ids))
        rows = conn.execute(f"SELECT id, name FROM character_card WHERE id IN ({placeholders})", tuple(seen_ids)).fetchall()
    return [dict(c) for c in rows]


def _query_kb(question: str) -> str | None:
    """Search the prompt knowledge base for style/template questions.

    Returns formatted reply, or None if no match.
    """
    try:
        from src.aicomic.prompt_kb import get_kb
        kb = get_kb()
    except Exception:
        return None

    results = kb.search(question)
    if not results:
        return None

    # ── 找到匹配：构建回复 ──
    reply_parts = [f"📚 从提示词模板库中找到 {len(results)} 个相关参考：\n"]
    for r in results[:3]:  # 最多展示 3 个
        reply_parts.append(f"### 📄 {r['title']}")
        reply_parts.append(f"**分类**: {r['category']} — {r['purpose']}")
        reply_parts.append(f"**大小**: {r['char_count']} 字符")
        # 展示预览
        preview = r["preview"][:200]
        if len(r["content"]) > 200:
            preview += "…"
        reply_parts.append(f"\n```\n{preview}\n```")
        reply_parts.append("")
    reply_parts.append(
        "💡 需要我将某个模板的完整内容展开应用到当前章节吗？"
        " 例如对我说「用角色三视图模板重新生成萧澈的图」。"
    )
    return "\n".join(reply_parts)


@router.get("/history")
def chat_history(chapter_id: int | None = None):
    from server.db import ChatStore
    conn = get_db()
    try:
        store = ChatStore(conn)
        return [dict(m) for m in store.get_by_chapter(chapter_id)]
    finally:
        conn.close()
