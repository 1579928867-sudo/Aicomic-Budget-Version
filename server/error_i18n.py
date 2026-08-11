"""技术错误 → 用户友好翻译。

每条规则包含：
- pattern: 正则匹配原始错误文本
- friendly: 用户可理解的说明（含下一步指引）
- level: "retry"（可重试）| "fix"（需手动修复）| "fatal"（需联系/配置）

用法:
    from server.error_i18n import translate_error
    friendly_msg = translate_error(raw_error)
"""

import re
from typing import NamedTuple


class ErrorTranslation(NamedTuple):
    friendly: str
    level: str  # "retry" | "fix" | "fatal"


# ── 规则表：从最具体到最通用 ──
_RULES: list[tuple[str, ErrorTranslation]] = [
    # ══════ LLM 生成格式错误 ══════
    (
        r"Invalid shot_type '(.+?)' in shot (\d+)",
        ErrorTranslation(
            "📝 **剧本格式异常** — 第{r2}个分镜的镜头类型是「{r1}」，"
            "但系统只接受 `action`（动作镜头）、`dialogue`（对话镜头）、`both`（动作+对话）。\n\n"
            "🔧 **原因**：AI 在生成分镜剧本时使用了不确定的标签。这是偶发情况，通常重试可恢复。\n\n"
            "💡 **建议**：对我说「重新生成剧本」或「重新生成第X章」，AI 会重新解析小说段落。",
            "retry",
        ),
    ),
    (
        r"Invalid .+ in .+",
        ErrorTranslation(
            "📝 **AI 输出格式异常** — 生成的内容中包含了系统不认识的格式标签。\n\n"
            "🔧 **原因**：大型语言模型有时会产生不符合预期格式的输出。这是偶发现象。\n\n"
            "💡 **建议**：对我说「重新生成」即可重试。通常第二次就能正常通过。",
            "retry",
        ),
    ),
    # ══════ LLM API 认证 ══════
    (
        r"(?i)no api key for backend",
        ErrorTranslation(
            "🔑 **未配置 LLM API Key** — 系统需要 DeepSeek API Key 才能进行意图理解和生成剧本。\n\n"
            "💡 **建议**：前往「系统设置」页面，填入 DeepSeek API Key。\n"
            "  1. 登录 platform.deepseek.com 获取 Key（新用户有免费额度）\n"
            "  2. 在「系统设置」中粘贴并保存\n"
            "  3. 完成后回到聊天页，对我说「生成第X章」即可开始",
            "fix",
        ),
    ),
    (
        r"(?i)(error code: 40[13]|invalid_api_key|incorrect api key|authentication fails|401|403).*(api|key|token|auth)",
        ErrorTranslation(
            "🔑 **LLM API Key 无效**（401 认证失败）— DeepSeek 拒绝了当前的 API 密钥。\n\n"
            "🔧 **常见原因**：\n"
            "  • API Key 复制时带了多余的空格或换行\n"
            "  • API Key 已过期或被删除\n"
            "  • 余额不足导致账号被限制\n\n"
            "💡 **建议**：\n"
            "  1. 前往「系统设置」页面，重新粘贴 API Key，确保无多余空格\n"
            "  2. 登录 DeepSeek 开放平台 (platform.deepseek.com) 检查 API Key 状态\n"
            "  3. 确认账户有可用余额",
            "fix",
        ),
    ),
    # ══════ 数据库/文件 ══════
    (
        r"(?i)database is locked|database locked",
        ErrorTranslation(
            "🔒 **数据库繁忙** — 有另一个操作正在写入数据，暂时无法完成当前请求。\n\n"
            "💡 **建议**：稍等几秒后重试。如果持续出现，请重启服务器。",
            "retry",
        ),
    ),
    (
        r"(?i)no such (table|column)",
        ErrorTranslation(
            "🗄️ **数据库结构异常** — 缺少必要的表或字段。可能原因：数据库文件损坏或版本不匹配。\n\n"
            "💡 **建议**：检查 `data/aicomic.db` 文件是否完整。必要时备份后删除重建。",
            "fix",
        ),
    ),
    # ══════ 豆包/浏览器 ══════
    (
        r"(?i)(browser.*(?:crash|killed|gone|dead)|Target.*(?:closed|detached)|renderer.*crash)",
        ErrorTranslation(
            "🪟 **浏览器窗口意外关闭** — 豆包自动化浏览器崩溃或被关闭了。\n\n"
            "🔧 **常见原因**：\n"
            "  • 浏览器窗口被手动关闭（请勿关闭弹出的豆包浏览器窗口）\n"
            "  • 显卡驱动不兼容导致 Chromium 闪退\n"
            "  • 系统内存不足\n\n"
            "💡 **建议**：\n"
            "  1. 重试一次 — 系统会自动重建浏览器\n"
            "  2. 重试时注意：弹出的豆包浏览器窗口**不要手动关闭**\n"
            "  3. 如持续崩溃，检查显卡驱动是否需要更新",
            "retry",
        ),
    ),
    (
        r"(?i)(cannot switch to a different thread|browser.*closed|page.*closed|context.*closed)",
        ErrorTranslation(
            "🌐 **浏览器连接中断** — 豆包的浏览器自动化会话已断开。\n\n"
            "🔧 **常见原因**：之前的生成任务完成后浏览器自动关闭，新任务无法复用旧会话。\n\n"
            "💡 **建议**：重试一次即可。系统会自动重建浏览器连接。",
            "retry",
        ),
    ),
    (
        r"(?i)(cookie|login|authentication|unauthorized).*(invalid|expired|required)",
        ErrorTranslation(
            "🍪 **豆包登录失效** — Cookie 已过期或无效。\n\n"
            "💡 **建议**：前往「豆包Cookie」页面，点击「一键登录」重新获取 Cookie。"
            "完成后对我说「继续生成」。",
            "fix",
        ),
    ),
    (
        r"(?i)doubao.*(?:failed|error|timeout)",
        ErrorTranslation(
            "🌐 **豆包服务异常** — 图片/视频生成请求失败。\n\n"
            "🔧 **可能原因**：豆包服务器繁忙、网络波动、或内容审核触发。\n\n"
            "💡 **建议**：稍等 2-3 分钟再试。如果持续失败，尝试调整提示词降低写实度。",
            "retry",
        ),
    ),
    # ══════ 文件/IO ══════
    (
        r"(?i)(no such file|file not found|cannot find).*'([^']+)'",
        ErrorTranslation(
            "📁 **文件缺失** — 需要的文件 `{r2}` 不存在。\n\n"
            "🔧 **可能原因**：文件被手动删除、移动，或前置步骤未完成。\n\n"
            "💡 **建议**：检查素材库中对应的角色图/场景图是否存在。如不存在，重新运行「图片生成」阶段。",
            "fix",
        ),
    ),
    (
        r"(?i)permission denied|access denied|WinError 32",
        ErrorTranslation(
            "📁 **文件占用** — 目标文件正被其他程序使用，无法写入。\n\n"
            "💡 **建议**：关闭可能占用该文件的应用（视频播放器、资源管理器预览等），然后重试。",
            "retry",
        ),
    ),
    # ══════ Python 运行时 ══════
    (
        r"'(gbk|ascii|cp\d+)' codec can't (encode|decode)",
        ErrorTranslation(
            "🔤 **字符编码错误** — 系统中出现了不兼容的字符。\n\n"
            "💡 **建议**：重试即可。服务器已配置自动编码修复。如持续出现，重启服务器。",
            "retry",
        ),
    ),
    (
        r"(?i)(memory|memoryerror)",
        ErrorTranslation(
            "💾 **内存不足** — 处理过程中内存耗尽。\n\n"
            "💡 **建议**：关闭其他大型应用后重试。对于超大章节（>5万字），建议分段处理。",
            "retry",
        ),
    ),
    # ══════ Pipeline 特定 ══════
    (
        r"图片生成失败|图片生成为 0|no_images|img_gen_failed",
        ErrorTranslation(
            "🖼️ **图片生成失败** — 角色图或场景图未能生成。没有参考图就无法继续视频阶段。\n\n"
            "🔧 **可能原因**：豆包额度耗尽、Cookie 过期、或提示词触发审核。\n\n"
            "💡 **建议**：\n"
            "  1. 检查豆包 Cookie 是否有效（「豆包Cookie」页面验证）\n"
            "  2. 确认豆包每日免费额度未用完\n"
            "  3. 对我说「重新生成角色图」重试",
            "fix",
        ),
    ),
    (
        r"视频生成失败|video.*(?:failed|error)",
        ErrorTranslation(
            "🎬 **视频生成失败** — 分镜视频未能生成。\n\n"
            "🔧 **可能原因**：豆包视频额度耗尽（免费用户每日3次）、Cookie 过期、或内容审核。\n\n"
            "💡 **建议**：\n"
            "  1. 检查豆包 Cookie → 打开「豆包Cookie」页面\n"
            "  2. 确认视频额度 → 登录即梦查看剩余次数\n"
            "  3. 额度用完 → 明天再继续，已生成的素材不会丢失",
            "fix",
        ),
    ),
    (
        r"(?i)(orchestrator|pipeline).*(?:not initialized|not ready)",
        ErrorTranslation(
            "⚙️ **生成引擎未就绪** — Pipeline 尚未初始化。\n\n"
            "💡 **建议**：前往「系统设置」确认 LLM API Key 已配置，然后重启服务器。",
            "fix",
        ),
    ),
    (
        r"(?i)agent.*not registered",
        ErrorTranslation(
            "⚙️ **Agent 未注册** — 所需的生成模块未加载。\n\n"
            "💡 **建议**：检查 `config/settings.yaml` 中 `video.generator` 配置是否正确。"
            "免费用户应设为 `mock`。",
            "fix",
        ),
    ),
    # ══════ 通用兜底 ══════
    (
        r".+",  # 匹配任何错误
        ErrorTranslation(
            "⚠️ **执行出错** — 系统遇到了未预期的错误。\n\n"
            "📋 原始错误已记录到任务日志，技术人员可查看详情。\n\n"
            "💡 **建议**：请尝试重试。如果问题持续，重启服务器后再试。",
            "retry",
        ),
    ),
]


def translate_error(raw_error: str) -> str:
    """将技术错误翻译为用户友好消息。

    遍历规则表，返回第一个匹配的 friendly 消息。
    {r1}, {r2} 等占位符会被正则捕获组替换。

    Returns:
        带 emoji + 原因 + 建议的友好错误消息。
    """
    for pattern, translation in _RULES:
        m = re.search(pattern, raw_error, re.IGNORECASE | re.DOTALL)
        if m:
            msg = translation.friendly
            # 替换 {r1}, {r2} 占位符
            for i, group in enumerate(m.groups(), start=1):
                msg = msg.replace(f"{{r{i}}}", str(group))
            # 附加技术原文（折叠，用于调试）
            return msg

    return raw_error  # 不会走到这里（最后一条规则是 .+）


def translate_error_short(raw_error: str) -> str:
    """简洁版翻译 — 只返回一句话 + 建议，不含完整技术详情。

    用于手机通知、任务列表摘要等短文本场景。
    """
    for pattern, translation in _RULES:
        m = re.search(pattern, raw_error, re.IGNORECASE | re.DOTALL)
        if m:
            msg = translation.friendly
            for i, group in enumerate(m.groups(), start=1):
                msg = msg.replace(f"{{r{i}}}", str(group))
            # 只保留第一段（不附加技术详情）
            first_para = msg.split("\n\n")[0] if "\n\n" in msg else msg
            return first_para
    return raw_error
