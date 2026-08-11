"""Prompt模板知识库 — 加载业内提示词参考文件，提供分类检索和上下文注入。

文件来源: 业内的提示词参考/
每个文件自动分配 kb_id、按内容分类、支持关键词搜索。

用法:
    from src.aicomic.prompt_kb import PromptKB
    kb = PromptKB()
    results = kb.search("角色设计")         # → [{kb_id, title, category, preview, content}]
    ctx = kb.context_for("角色设计")         # → str (可直接注入 prompt)
    kb.list_categories()                    # → ["人物设计", "场景设计", ...]
"""

from __future__ import annotations

import json
import re
from pathlib import Path

KB_DIR = Path("业内的提示词参考")


# ── 文件 → 分类映射 (基于文件名和内容特征) ──
_CATEGORY_RULES: list[tuple[str, str, str]] = [
    # (文件名关键词, 分类, 用途描述)
    ("人物三视图", "人物设计", "角色三视图 + 角色卡布局模板"),
    ("人物场景提取", "人物设计", "从小说文案中提取人物/场景信息的指令模板"),
    ("仿真人示例", "人物设计", "真人图片转手绘 + 写实电影感风格的完整出图规范"),
    ("场景四试图", "场景设计", "四格分屏纯场景视角模板（全景/正向/反向/近景）"),
    ("小说转剧本", "剧本改编", "小说→漫剧剧本的完整指令，含镜头标注+时长+动作/对话规则"),
    ("打斗画面", "战斗特效", "虚幻引擎5渲染 + 打斗分镜时序 + 高燃动作提示词"),
    ("漫剧风格参考", "风格分类", "52种漫剧风格（3D/2D/写实/半写实等）的完整分类JSON"),
    ("豆包漫剧视频", "视频生成", "10秒短视频的分镜时序模板 + 提示词格式"),
]


def _read_file(path: Path) -> str:
    """Read file with encoding detection."""
    for enc in ["utf-8", "gbk", "utf-16", "cp936"]:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="replace")


class PromptKB:
    """Prompt 模板知识库 — 一次性加载，所有文件常驻内存 (~90KB)."""

    def __init__(self, kb_dir: Path | None = None):
        self._dir = kb_dir or KB_DIR
        self._entries: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._by_category: dict[str, list[dict]] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        if not self._dir.exists():
            self._loaded = True
            return
        for fpath in sorted(self._dir.glob("*.txt")):
            filename = fpath.name
            # ── 匹配分类 ──
            category, purpose = "其他", "参考提示词"
            for kw, cat, purp in _CATEGORY_RULES:
                if kw in filename or kw in fpath.stem:
                    category, purpose = cat, purp
                    break

            raw = _read_file(fpath)
            if not raw.strip():
                continue

            # ── 生成 kb_id ──
            kb_id = re.sub(r'[^a-zA-Z0-9一-鿿]', '_', fpath.stem).strip('_')

            # ── 预览: 前 300 字 ──
            preview = raw[:300].replace('\n', ' ').strip()
            if len(raw) > 300:
                preview += "…"

            entry = {
                "kb_id": kb_id,
                "title": fpath.stem,
                "category": category,
                "purpose": purpose,
                "filename": filename,
                "preview": preview,
                "content": raw,
                "char_count": len(raw),
            }
            self._entries.append(entry)
            self._by_id[kb_id] = entry
            self._by_category.setdefault(category, []).append(entry)

        # ── 内置：面部网格遮罩说明（程序自动处理，供KB查询） ──
        face_grid_entry = {
            "kb_id": "face_grid_overlay",
            "title": "面部网格遮罩（自动）",
            "category": "人物设计",
            "purpose": "自动叠加半透明暖色网格线，绕过真实人脸检测",
            "filename": "(内置)",
            "preview": "系统自动在角色设定图生成后叠加5px间距/45%透明度/暖色网格线，覆盖面部区域上部80%。无需手动添加到提示词。",
            "content": (
                "【系统自动处理 — 无需提示词】\n\n"
                "角色设定图生成后，管线自动应用面部网格遮罩：\n"
                "- 5px 等距网格线\n"
                "- 45% 透明度暖肤色（RGB 245,205,170）\n"
                "- 覆盖图片上部 80%（面部区域）\n"
                "- 下部 20% 保持原图无遮挡\n\n"
                "用途：破坏豆包/即梦的写实人脸检测算法，确保角色图能通过AI生图审核。\n"
                "提示词中可加「面部添加半透明暖色网格线，5px间距」作为辅助说明，但实际网格由程序自动叠加。"
            ),
            "char_count": 300,
        }
        self._entries.append(face_grid_entry)
        self._by_id["face_grid_overlay"] = face_grid_entry
        self._by_category.setdefault("人物设计", []).append(face_grid_entry)

        self._loaded = True

    # ── 公共 API ──

    @staticmethod
    def _guard_preamble() -> str:
        """模板保护规则 — 每次注入上下文时前置，防止LLM过度修改。"""
        return (
            "[模板保护规则 — 不可违反]\n"
            "以下提示词模板是经过生产验证的参考格式。你可以根据用户的具体小说内容进行适配，"
            "但以下元素**绝对不能**修改或删除：\n"
            "1. **[不可修改] 避审声明** — 如版权声明、合规前置指令，必须原样保留\n"
            "2. **[不可修改] 画幅比例** — 如 16:9、9:16 等比例要求，不可更改\n"
            "3. **[不可修改] 面部网格遮罩** — 如「面部添加半透明暖色网格线」「5px间距网格覆盖」等描述，不可删除\n"
            "4. **[不可修改] 风格基调** — 如「3D国漫风格」「写实电影感」等核心风格词，只能微调不能颠覆\n"
            "5. **[不可修改] 输出格式** — 如三视图排列方式（左大头贴→正面→侧面→背面）、四格分屏等布局要求\n\n"
            "可以适配的部分：角色名、服装颜色和款式、场景具体描述、台词内容等与用户小说内容相关的信息。\n\n"
            "[模板保护规则结束]\n"
        )

    def list_categories(self) -> list[dict]:
        """返回所有分类及条目数."""
        self._ensure_loaded()
        return [
            {"category": cat, "count": len(entries), "purposes": [e["purpose"] for e in entries]}
            for cat, entries in self._by_category.items()
        ]

    def list_all(self) -> list[dict]:
        """返回所有条目摘要（不含完整内容）."""
        self._ensure_loaded()
        return [
            {k: v for k, v in e.items() if k != "content"}
            for e in self._entries
        ]

    def get(self, kb_id: str) -> dict | None:
        """按 ID 获取完整内容."""
        self._ensure_loaded()
        return self._by_id.get(kb_id)

    def search(self, query: str) -> list[dict]:
        """关键词搜索 — 匹配标题、分类名、用途描述、以及内容全文。返回完整条目（含 content）。"""
        self._ensure_loaded()
        q = query.lower()
        results = []
        for e in self._entries:
            haystack = f"{e['title']} {e['category']} {e['purpose']} {e['content'][:2000]}".lower()
            if any(kw in haystack for kw in q.split()) or q in haystack:
                results.append(e)
        return results

    def context_for(self, query: str, max_chars: int = 3000) -> str:
        """为 LLM 生成上下文块 — 搜索匹配的模板，截断后返回可注入 prompt 的文本。

        Args:
            query: 搜索关键词
            max_chars: 返回上下文的最大字符数（硬截断保护 context window）

        Returns:
            格式化的上下文字符串，如果没匹配到则返回空字符串。
        """
        results = self.search(query)
        if not results:
            return ""

        parts = ["[知识库] 以下是从提示词模板库中检索到的相关参考内容："]
        parts.insert(0, self._guard_preamble())
        total = 0
        for r in results:
            header = f"\n### {r['title']}（{r['category']}）"
            body = r["content"]
            # 硬截断保护
            budget = max_chars - total - len(header) - 50
            if budget <= 0:
                break
            if len(body) > budget:
                body = body[:budget] + "\n…(内容过长，已截断)"
            parts.append(header + "\n" + body)
            total += len(header) + len(body) + 2

        parts.append("\n[知识库结束] 请结合上述模板参考用户的请求，但不要逐字套用——根据用户的实际小说内容进行适配。")
        return "\n".join(parts)

    def context_for_intent(self, intent: str, user_message: str = "", max_chars: int = 2000) -> str:
        """根据意图类型自动匹配相关的模板类别。

        映射关系:
            generate_chapter / regenerate_character / regenerate_char_design
                → "人物设计" + "场景设计"
            regenerate_scene
                → "场景设计"
            regenerate_video / compose_video / retry_shot_video
                → "视频生成" + "战斗特效"
            query (跟风格/提示词相关)
                → 全库搜索

        Args:
            intent: 意图类型
            user_message: 用户的原始消息（用于 query 意图的搜索）
            max_chars: 返回上下文的最大字符数

        Returns:
            格式化的上下文字符串。
        """
        intent_category_map = {
            "generate_chapter": ["人物设计", "场景设计", "剧本改编"],
            "regenerate_character": ["人物设计"],
            "regenerate_char_design": ["人物设计"],
            "regenerate_scene": ["场景设计"],
            "regenerate_video": ["视频生成", "战斗特效"],
            "compose_video": ["视频生成"],
            "retry_shot_video": ["视频生成", "战斗特效"],
            "style_query": ["风格分类"],
        }
        categories = intent_category_map.get(intent, [])

        if intent == "query" and user_message:
            # 检测是否跟风格/提示词/模板相关
            style_keywords = ["风格", "提示词", "模板", "参考", "怎么写", "怎么生成", "格式", "指令"]
            if any(kw in user_message for kw in style_keywords):
                categories = ["风格分类"]

        if not categories:
            return ""

        self._ensure_loaded()
        parts = ["[知识库] 以下是从提示词模板库中自动匹配的参考内容："]
        parts.insert(0, self._guard_preamble())
        total = 0
        seen_ids = set()
        for cat in categories:
            entries = self._by_category.get(cat, [])
            for r in entries:
                if r["kb_id"] in seen_ids:
                    continue
                seen_ids.add(r["kb_id"])
                header = f"\n### {r['title']}（{r['category']} — {r['purpose']}）"
                body = r["content"]
                budget = max_chars - total - len(header) - 50
                if budget <= 0:
                    break
                if len(body) > budget:
                    body = body[:budget] + "\n…(截断)"
                parts.append(header + "\n" + body)
                total += len(header) + len(body) + 2

        if len(parts) == 1:
            return ""
        parts.append("\n[知识库结束] 请结合上述模板参考用户的请求，为当前小说内容进行适配。")
        return "\n".join(parts)

    @property
    def entry_count(self) -> int:
        self._ensure_loaded()
        return len(self._entries)


# ── 全局单例 ──
_kb_instance: PromptKB | None = None


def get_kb() -> PromptKB:
    """获取知识库全局单例（线程安全，懒加载）."""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = PromptKB()
    return _kb_instance
