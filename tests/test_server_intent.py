"""Tests for server/intent.py — NLU intent parser."""
from server.intent import parse_intent_with_llm, build_context_text


def mock_llm_intent(expected_intent: str, extra: dict):
    """返回一个 mock LLM callable，返回固定意图 JSON."""
    def _mock(system_prompt: str, user_message: str) -> str:
        import json
        return json.dumps({"intent": expected_intent, **extra}, ensure_ascii=False)
    return _mock


def test_parse_generate_chapter_intent():
    """'生成第3章' → intent=generate_chapter, chapter_num=3."""
    result = parse_intent_with_llm(
        message="生成第3章",
        context={"novel": {"id": 1, "title": "逆天邪神"}, "chapters": []},
        llm_call=mock_llm_intent("generate_chapter", {"chapter_num": 3}),
    )
    assert result["intent"] == "generate_chapter"
    assert result["chapter_num"] == 3


def test_parse_regenerate_character_intent():
    """'重新生成萧澈的图' → intent=regenerate_character."""
    result = parse_intent_with_llm(
        message="重新生成萧澈的图，眼神更冷峻",
        context={
            "novel": {"id": 1, "title": "逆天邪神"},
            "characters": [{"id": 1, "name": "萧澈"}, {"id": 3, "name": "萧泠汐"}],
        },
        llm_call=mock_llm_intent("regenerate_character", {
            "character_name": "萧澈", "character_id": 1,
            "extra_hint": "眼神更冷峻",
        }),
    )
    assert result["intent"] == "regenerate_character"
    assert result["character_id"] == 1


def test_parse_query_intent():
    """'萧澈现在用的什么图' → intent=query."""
    result = parse_intent_with_llm(
        message="萧澈现在用的什么图？",
        context={"characters": [{"id": 1, "name": "萧澈"}]},
        llm_call=mock_llm_intent("query", {"query_type": "character_image"}),
    )
    assert result["intent"] == "query"


def test_parse_chat_intent():
    """'你好' → intent=chat."""
    result = parse_intent_with_llm(
        message="你好，今天天气真好",
        context={},
        llm_call=mock_llm_intent("chat", {"reply": "你好！有什么可以帮你的？"}),
    )
    assert result["intent"] == "chat"
    assert "reply" in result


def test_parse_import_novel_intent():
    """'上传小说' → intent=import_novel."""
    result = parse_intent_with_llm(
        message="我要上传一本小说",
        context={},
        llm_call=mock_llm_intent("import_novel", {}),
    )
    assert result["intent"] == "import_novel"


def test_parse_regenerate_scene_intent():
    """'重新生成场景' → intent=regenerate_scene."""
    result = parse_intent_with_llm(
        message="重新生成流云城的场景图，黄昏光线",
        context={
            "scenes": [{"id": 2, "name": "流云城"}, {"id": 5, "name": "萧家大厅"}],
        },
        llm_call=mock_llm_intent("regenerate_scene", {
            "scene_name": "流云城", "scene_id": 2,
            "extra_hint": "黄昏光线",
        }),
    )
    assert result["intent"] == "regenerate_scene"
    assert result["extra_hint"] == "黄昏光线"


def test_parse_regenerate_video_intent():
    """'重新生成视频' → intent=regenerate_video."""
    result = parse_intent_with_llm(
        message="第2章的视频重做一下",
        context={"chapters": [{"id": 2, "chapter_num": 2}]},
        llm_call=mock_llm_intent("regenerate_video", {"chapter_num": 2}),
    )
    assert result["intent"] == "regenerate_video"
    assert result["chapter_num"] == 2


def test_fallback_on_invalid_json():
    """LLM 返回非法 JSON 时回退为 chat 意图."""
    def bad_llm(_sys, _usr):
        return "不是有效的 JSON {"

    result = parse_intent_with_llm(
        message="随便说点什么",
        context={},
        llm_call=bad_llm,
    )
    assert result["intent"] == "chat"


def test_strip_markdown_code_block():
    """LLM 返回带 markdown 包裹的 JSON 时也能正确解析."""
    def markdown_llm(_sys, _usr):
        return '```json\n{"intent": "chat", "reply": "你好!"}\n```'

    result = parse_intent_with_llm(
        message="hello",
        context={},
        llm_call=markdown_llm,
    )
    assert result["intent"] == "chat"
    assert result["reply"] == "你好!"


def test_build_context_text():
    """build_context_text 正确拼接上下文."""
    ctx = {
        "novel": {"id": 1, "title": "逆天邪神"},
        "chapters": [
            {"id": 1, "chapter_num": 1},
            {"id": 2, "chapter_num": 2},
        ],
        "characters": [
            {"id": 1, "name": "萧澈"},
            {"id": 2, "name": "夏倾月"},
        ],
        "scenes": [
            {"id": 1, "name": "流云城"},
        ],
    }
    text = build_context_text(ctx)
    assert "逆天邪神" in text
    assert "第1章" in text
    assert "第2章" in text
    assert "萧澈" in text
    assert "夏倾月" in text
    assert "流云城" in text
    assert "id=" in text
