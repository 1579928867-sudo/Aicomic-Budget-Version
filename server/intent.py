"""NLU 意图解析 — LLM 将用户消息映射到结构化意图."""
from __future__ import annotations

import json
from typing import Any, Callable

INTENT_PROMPT = """你是一个 AI漫剧助手的意图分类器。根据用户的消息和当前上下文，输出一个 JSON 对象。

支持的意图:
- generate_chapter: 用户要生成/制作某个章节。输出: {"intent": "generate_chapter", "chapter_num": <数字>}
- regenerate_character: 用户要重新生成某个角色的图片。输出: {"intent": "regenerate_character", "character_name": "<名>", "extra_hint": "<用户的额外要求>"}
- regenerate_scene: 用户要重新生成某个场景。输出: {"intent": "regenerate_scene", "scene_name": "<名>", "extra_hint": "<...>"}
- regenerate_video: 用户要重新生成视频。输出: {"intent": "regenerate_video", "chapter_num": <数字>}
- import_novel: 用户要上传/导入小说。输出: {"intent": "import_novel"}
- regenerate_char_design: 用户要重新设计角色形象。输出: {"intent": "regenerate_char_design", "character_name": "<名>", "extra_hint": "<...>"}
- query: 用户是查询/问问题。输出: {"intent": "query", "query_text": "<用户的原始问题>"}
- chat: 一般闲聊，不触发任何操作。输出: {"intent": "chat", "reply": "<友好回复>"}

规则:
1. 尽量在 extra_hint 中保留用户的具体要求（如"眼神更冷峻""光影更暖"等）
2. 如果上下文中已有角色/章节列表，优先匹配已有的名称
3. 只输出 JSON，不要任何其他文本

当前上下文:
{context}

用户消息: {message}"""


def build_context_text(context: dict) -> str:
    """将上下文 dict 转为 prompt 可读文本."""
    parts = []
    if context.get("novel"):
        parts.append(f"当前小说: {context['novel']['title']} (id={context['novel']['id']})")
    if context.get("chapters"):
        ch_list = ", ".join(f"第{c['chapter_num']}章(id={c['id']})" for c in context["chapters"])
        parts.append(f"已有章节: {ch_list}")
    if context.get("characters"):
        ch_list = ", ".join(f"{c['name']}(id={c['id']})" for c in context["characters"])
        parts.append(f"已有角色: {ch_list}")
    if context.get("scenes"):
        s_list = ", ".join(f"{s['name']}(id={s['id']})" for s in context["scenes"])
        parts.append(f"已有场景: {s_list}")
    return "\n".join(parts) if parts else "无特定上下文"


def parse_intent_with_llm(
    message: str,
    context: dict,
    llm_call: Callable[[str, str], str],
) -> dict:
    """调用 LLM 做意图解析，返回 dict.

    Args:
        message: 用户原始消息
        context: {novel, chapters, characters, scenes} 等上下文信息
        llm_call: (system_prompt, user_message) -> response_text 的 callable

    Returns:
        {"intent": str, ...}
    """
    ctx_text = build_context_text(context)
    prompt = INTENT_PROMPT.replace("{context}", ctx_text).replace("{message}", message)

    response = llm_call(
        "你是一个精确的意图分类器。只输出 JSON。",
        prompt,
    )

    # 清理可能的 markdown 代码块包裹
    response = response.strip()
    if response.startswith("```"):
        # 找到第一行换行，去掉开头的 ```json 或 ```
        first_newline = response.find("\n")
        if first_newline != -1:
            response = response[first_newline + 1:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

    try:
        result = json.loads(response)
    except json.JSONDecodeError:
        # 回退: 当作一般聊天处理
        result = {"intent": "chat", "reply": response}
    return result
