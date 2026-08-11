"""NLU 意图解析 — LLM 将用户消息映射到结构化意图."""
from __future__ import annotations

import json
from typing import Any, Callable

INTENT_PROMPT = """你是一个 AI漫剧助手的意图分类器。根据用户的消息和当前上下文，输出一个 JSON 对象。

支持的意图:
- generate_chapter: 用户要生成/制作/创建某个章节（首次）。这是最常见的"生成"意图。
  输出: {"intent": "generate_chapter", "chapter_num": <数字>, "with_video": <true/false>}
  规则：如果用户说"生成第X章"或"生成...第X章的视频"/"第X章做成视频"，都是 generate_chapter。
  只有明确说"重新生成"/"重做"/"再做一次"时才可能是 regenerate 系列。
- retry_shot_video: 用户要生成/重试某个特定分镜的视频。说"生成镜头N"、"镜头N视频"、"重新生成镜头N"、"生成第N个镜头"等。
  输出: {"intent": "retry_shot_video", "shot_num": <数字>}
  注意：这与"生成第X章"完全不同——"章"是大章节，"镜头"/分镜"是章节内的分镜单元。
- compose_video: 用户要合成/拼接/合并视频。说"合成"、"拼接"、"合成第X章"、"合成镜头"、"把XXX合成视频"等。
  输出: {"intent": "compose_video", "chapter_num": <数字>}  如果没有明确指定章节号则默认为当前章节。
- regenerate_character: 用户明确要**重新**生成某个角色的图片，或微调角色图。
  输出: {"intent": "regenerate_character", "character_name": "<名>", "extra_hint": "<用户额外要求>"}
- regenerate_scene: 用户明确要**重新**生成某个场景图。
  输出: {"intent": "regenerate_scene", "scene_name": "<名>", "extra_hint": "<...>"}
- regenerate_video: 用户明确要**重新**生成视频（已经生成过，再来一次）。
  输出: {"intent": "regenerate_video", "chapter_num": <数字>}
- import_novel: 用户要上传/导入小说。
  输出: {"intent": "import_novel"}
- regenerate_char_design: 用户明确要**重新**设计角色形象。
  输出: {"intent": "regenerate_char_design", "character_name": "<名>", "extra_hint": "<...>"}
- delete_novel_or_chapter: 用户要删除小说或章节。说"删除第X章"、"删除《XXX》"、"删掉小说"、"移除XXX"等。
  输出: {"intent": "delete_novel_or_chapter", "target_type": "<novel|chapter>", "target_name": "<书名或章节号>", "chapter_num": <数字或null>}
  规则：明确说"删除"/"删掉"/"移除"时触发。不确定时宁可归为 query 或 chat。

- query: 用户是查询/问问题。输出: {"intent": "query", "query_text": "<用户的原始问题>"}
- chat: 一般闲聊、问功能怎么用，不触发任何操作。输出: {"intent": "chat", "reply": "<友好回复>"}
- off_topic: 用户的提问与AI漫剧完全无关（如天气、编程、数学、写代码、翻译、写文章、心理咨询等）。
  输出: {"intent": "off_topic", "reply": "<礼貌拒绝的简短回复>"}
  规则：用户问的是与小说生成/角色设计/视频制作/漫剧完全无关的话题时，使用此意图。不确定时归为 chat。

**关键规则:**
1. "生成"和"重新生成"完全不同。只有用户说"重新生成"/"重做"/"再来一次"时，才用 regenerate 系列。
2. "生成第X章"/"生成第X章视频"/"把第X章做成视频"/"制作第X章" → generate_chapter，with_video 根据是否提到视频决定
3. "生成镜头N"/"镜头N视频"/"重新生成镜头N"/"生成第N个镜头" → retry_shot_video，这是单个分镜视频而非整个章节
4. "合成"/"拼接"/"合成第X章"/"合成镜头"/"把XX合成视频" → compose_video，这是合并已有视频片段成成品，不需要重新生成
5. "生成X章"（无"第"字）时，X 是章节号 → generate_chapter
5. 额外要求放在 extra_hint 中
6. 如上下文中有章节列表，优先匹配已有章节
7. "删除"/"删掉"/"移除" + 小说/章节 → delete_novel_or_chapter
8. 与AI漫剧完全无关的问题（天气、编程、数学、翻译、写文章、心理咨询等）→ off_topic
9. **"继续"规则**："继续"表示恢复之前的任务、继续当前章节，**绝不**表示跳到下一章。用户说"继续"+"第X章"时，chapter_num=第X章本身（用户明确说的数字），不要自动+1。用户说"继续生成情绪第一章"时 chapter_num=1，说"继续生成情绪第二章"时才是 chapter_num=2。
10. 只输出 JSON，不要任何其他文本

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
