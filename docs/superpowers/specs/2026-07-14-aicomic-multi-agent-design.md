# AI 漫剧生成助手 · 多 Agent 协作框架 — 设计文档

> 日期: 2026-07-14 | 状态: 待实现

## 项目目标

输入小说章节文本 → 自动生成剧本（含分镜） → 提取人物与场景并固化多视图 → 豆包生成漫剧视频片段 → 拼接合成带配音、字幕、运镜的完整漫剧，全程保证视觉一致性。

第一版目标：搭完整框架骨架，跑通端到端链路（CLI 入口 → 协调器 → 6 Agent → SQLite → 输出 MP4）。配音跳过，后续版本加。

---

## 技术选型

| 维度 | 选择 |
|------|------|
| 语言 | Python 3.12+ |
| 架构模式 | 插件式 Agent 总线（AgentInterface + AgentBus） |
| Agent 通信 | 本地函数调用（后续可加 Redis 分布式） |
| LLM | Claude API |
| 知识库/状态 | SQLite（单文件，零运维） |
| 图片/视频生成 | Playwright 操控豆包网页端（无 API，用浏览器自动化） |
| 配音 | 第一版跳过 |
| 视频处理 | MoviePy（拼接 + 字幕 + 运镜） |
| 用户交互 | CLI 先跑通，后续加 Web UI |

---

## 核心架构

```
┌─────────────────────────────────────────────────┐
│                   CLI 入口                       │
│         (python -m aicomic run chapter.txt)      │
└─────────────────────┬───────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│               协调 Agent (Orchestrator)          │
│  Pipeline: 编剧 → 人物+场景 → 视觉 → 合成        │
│  状态机: idle→scripting→assets→video→done        │
│  异常处理 + 断点续跑 + 进度日志                   │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
┌──────▼──────▼──────▼──────▼──────▼──────────────┐
│                Agent Bus (注册 + 调度)            │
│  AgentInterface: validate/execute/status         │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
  ┌────▼┐┌───▼──┐┌──▼──┐┌──▼──┐┌──▼───┐
  │编剧 ││人物  ││场景 ││视觉 ││合成  │
  └─────┘└──────┘└─────┘└─────┘└──────┘
       │      │      │      │      │
       └──────┴──────┴──────┴──────┘
                      │
         ┌────────────▼────────────┐
         │    SQLite 知识库         │
         └─────────────────────────┘
```

---

## 知识库设计 (SQLite Schema)

```
novel                    chapter                script
┌──────────────┐        ┌──────────────┐       ┌──────────────────┐
│ id (PK)      │──1:N──▶│ id (PK)      │──1:1─▶│ id (PK)          │
│ title        │        │ novel_id (FK)│       │ chapter_id (FK)  │
│ author       │        │ chapter_num  │       │ raw_json (剧本JSON)│
│ created_at   │        │ raw_text     │       │ status           │
└──────────────┘        │ status       │       │ created_at       │
                        └──────────────┘       └──────┬───────────┘
                                                      │ 1:N
                                              ┌───────▼────────────┐
                                              │ storyboard_shot    │
                    character_card           │ id, script_id,      │
                    ┌──────────────┐         │ shot_num, narration │
                    │ id (PK)      │         │ dialogue, camera_move│
                    │ name         │         │ duration_sec        │
                    │ default_look │         │ char_ids (JSON arr) │
                    │ status       │         │ scene_id            │
                    └──────┬───────┘         └─────────────────────┘
                           │ 1:N
              ┌────────────▼──────────────┐
              │ appearance_variant        │         scene_card
              │ id, character_id (FK),    │         ┌──────────────┐
              │ variant_name,             │         │ id (PK)      │
              │ type: "default"|          │         │ name         │
              │   "temporary"|"permanent" │         │ description  │
              │ applies_to (JSON scope),  │         │ multi_views  │
              │ appearance_json,          │         │ status       │
              │ views: {front,side,back}  │         └──────────────┘
              └───────────────────────────┘

                    video_clip              task_log
                    ┌──────────────┐        ┌──────────────┐
                    │ id (PK)      │        │ id (PK)      │
                    │ shot_id (FK) │        │ agent_name   │
                    │ file_path    │        │ chapter_id   │
                    │ status       │        │ event        │
                    └──────────────┘        │ detail (JSON)│
                                            │ level        │
                    final_video             │ created_at   │
                    ┌──────────────┐        └──────────────┘
                    │ id (PK)      │
                    │ chapter_id   │
                    │ file_path    │
                    │ created_at   │
                    └──────────────┘
```

**关键规则：**
- 每张表都有 `status` 字段（pending / running / done / failed），断点续跑的基础
- `task_log` 记录每个 Agent 的关键事件，既作日志也作审计
- `character_card` 和 `scene_card` 存图片路径
- `storyboard_shot` 中的 `char_ids` 和 `scene_id` 关联资产

---

## Agent 接口与总线

```python
class AgentInterface(ABC):
    """每个 Agent 必须实现的接口"""
    agent_name: str

    @abstractmethod
    def validate_input(self, input_data: dict) -> bool: ...

    @abstractmethod
    def execute(self, input_data: dict, db: Database) -> AgentResult: ...

@dataclass
class AgentResult:
    success: bool
    data: dict | None
    error: str | None
    artifacts: list[str]    # 产出的文件路径列表

class AgentBus:
    def register(self, agent: AgentInterface): ...
    def run(self, agent_name: str, input_data: dict, db: Database) -> AgentResult: ...
```

**设计原则：**
- Agent 接收 `db` 参数——读写知识库由 Agent 自己负责
- Agent 之间不传对象，只传 id
- `AgentResult.artifacts` 记录产出文件路径
- 后续切 Redis 分布式：新增 `RemoteAgentProxy` 实现 `AgentInterface` 即可

---

## 协调 Agent 编排流程

```
输入: chapter_id, raw_text

1. 编剧 Agent
   输入 raw_text → 输出 script JSON（含分镜 + 人物列表 + 场景列表）
   写入 script 表 + storyboard_shot 表

2a. 人物 Agent (与 2b 并行)
   遍历人物列表 → 查重 → Claude 生成外貌 → Playwright 豆包三视图
   写入 character_card 表 + appearance_variant 表

2b. 场景 Agent (与 2a 并行)
   遍历场景列表 → 查重 → Claude 生成描述 → Playwright 豆包多视图
   写入 scene_card 表

3. 视觉 Agent
   遍历 storyboard_shot → 拿人物/场景参考图 → Playwright 豆包生成视频(≤10s)
   写入 video_clip 表

4. 合成 Agent
   收集 video_clips → MoviePy 拼接+运镜+字幕 → 输出 final_video.mp4
```

**状态机：** `idle → scripting → assets → video → composing → done`

- 步骤 2a 和 2b 并行（人物和场景互不依赖）
- 每步开始前检查 `status`，`done` 则跳过
- 任一步 `failed`，协调器记录错误并终止

---

## 编剧 Agent

- **LLM:** Claude API，JSON mode
- **输出:** Script JSON（含分镜 storyboard_shot + 人物列表 + 场景列表）
- **运镜指令限定值:** `static`, `slow_push_in`, `slow_pan`, `slow_zoom`
- **每个 shot 的 characters** 使用 `{name, variant}` 结构，支持外貌变体标识

---

## 人物 Agent & 场景 Agent

两个 Agent 结构对称，可并行执行。

### 人物 Agent 流程
1. 查 SQLite → 该人物已存在? → done → 跳过
2. Claude 生成外貌描述（结构化 JSON，含 face/hair/body/clothing/style）
3. Playwright 豆包文生图 → 生成正面/侧面/背面三视图
4. 下载到 `data/characters/{name}/`
5. 写入 character_card + appearance_variant（type=default）

### 场景 Agent 流程
1. 查重 → 跳过
2. Claude 生成场景描述（含 lighting, style）
3. Playwright 豆包文生图 → 生成广角/中景/特写
4. 下载到 `data/scenes/{name}/`
5. 写入 scene_card

### 外貌变体（Appearance Variant）

解决人物服饰变化/易容导致的视觉不一致问题：

| 类型 | 含义 | 示例 | 行为 |
|------|------|------|------|
| `default` | 常规形象 | 默认道袍造型 | 初始即生成 |
| `temporary` | 临时变化，之后恢复 | 赴宴换装、易容潜入 | shot 结束后回 default |
| `permanent` | 永久改变 | 受伤留疤、换门派 | 从某 shot 起替代 default |

- 编剧 Agent 检测外貌变化时自动创建 variant
- 视觉 Agent 按 `(character, variant)` 取图，不匹配则 fallback 到 `default`

---

## 视觉 Agent

- 逐镜执行：查 shot → 查 character variant 三视图 → 查 scene 多视图 → 组装豆包 prompt → Playwright 图生视频 → 下载
- 每个 shot 生成 ≤10s 视频片段
- 写入 video_clip 表

---

## 合成 Agent

- 收集所有 video_clip（按 shot_num 排序）
- MoviePy 拼接片段 + 运镜效果 + 字幕烧录
- 片段间 crossfadein(0.5) 转场
- 统一输出分辨率 1920×1080
- 输出 `data/final_video/{chapter_id}.mp4`

**运镜实现：** `slow_push_in`（线性放大5%）、`slow_pan`（横向平移）、`static`（不处理）

---

## Playwright 豆包操控层 (DoubaoClient)

参考开源项目 doubao-2api、doubao-browser-agent 的反爬与自动化设计。

### 核心操作
- `text_to_image(prompt, count)` → 文生图，人物/场景 Agent 用
- `image_to_video(prompt, ref_images, duration)` → 图生视频，视觉 Agent 用

### 可靠性保障

| 关注点 | 处理方式 |
|--------|----------|
| 登录检测 | 启动时验证 cookie 有效性，过期抛异常要求用户更新 |
| 限流 | 最多同时 2 个生成任务，队列控制 |
| 超时 | 单个生成任务 300s 超时，异步轮询检查 |
| 重试 | 指数退避（5s→10s→20s），最多 3 次 |
| 反爬 | playwright-stealth + 真实 UA + 设备指纹伪装 |
| cookie 持久化 | 首次手动登录后保存 cookie，后续自动加载 |

---

## 错误处理

| 错误类型 | 处理策略 |
|----------|----------|
| 可重试（超时、网络错误） | 自动重试，Agent 内部处理 |
| 可跳过（某 shot 反复失败） | 标记 failed，生成占位黑屏，继续 |
| 需人工（登录过期、API key 失效、磁盘满） | 抛到协调层，记录日志，终止并通知用户 |
| 数据错误（JSON 不合法） | 协调层校验，不合法则终止并报告 |

### 幂等性
- 状态先落 DB（悲观标记），宁可少跑不重跑
- 失败后清理半成品 artifact

---

## 项目结构

```
first_agent/
├── pyproject.toml
├── README.md
├── docs/superpowers/specs/
├── config/
│   └── settings.yaml
├── data/
│   ├── aicomic.db
│   ├── characters/{name}/   ← front/side/back.png
│   ├── scenes/{name}/       ← wide/mid/close.png
│   ├── clips/               ← 视频片段
│   └── final_video/         ← 最终输出
├── src/aicomic/
│   ├── main.py              ← CLI 入口
│   ├── orchestrator.py      ← 协调 Agent
│   ├── bus.py               ← Agent Bus
│   ├── interface.py         ← AgentInterface
│   ├── agents/
│   │   ├── screenwriter.py
│   │   ├── character.py
│   │   ├── scene.py
│   │   ├── visual.py
│   │   └── composer.py
│   ├── db/
│   │   ├── models.py
│   │   └── repository.py
│   ├── doubao/
│   │   └── client.py
│   ├── llm/
│   │   └── claude.py
│   └── video/
│       ├── effects.py
│       └── render.py
└── tests/
    ├── test_screenwriter.py
    ├── test_character.py
    ├── test_scene.py
    ├── test_visual.py
    ├── test_composer.py
    ├── test_orchestrator.py
    └── test_doubao.py
```

---

## 版本规划

| 版本 | 目标 |
|------|------|
| v0.1 | 完整框架骨架 + 编剧 Agent + SQLite + CLI 入口 |
| v0.2 | 人物 Agent + 场景 Agent（含 Playwright 豆包操控） |
| v0.3 | 视觉 Agent（图生视频） |
| v0.4 | 合成 Agent（拼接 + 字幕 + 运镜） |
| v0.5 | 断点续跑 + 错误恢复完善 |
| v1.0 | 配音 + Redis 分布式扩展 |
