# AI漫剧 Web 前端设计规格

Date: 2026-08-04
Status: draft
Version: 1.0

---

## 1. 项目目标

将 AI漫剧 Pipeline（第1、2章已验证）封装为 Web 前端应用，提供 Chat 交互入口、素材库浏览/预览/重新生成、视频管理、豆包 Cookie 配置等功能，面向个人用户使用。

**非目标：** 多用户系统、权限管理、分布式部署、商业化。

---

## 2. 架构概览

```
web/ (React 18 + TypeScript + Vite + shadcn/ui + Tailwind)
        │
   HTTP REST + SSE (单端口)
        │
server/ (FastAPI + uvicorn)
   ├── api/chat.py          ← Chat 消息 + NLU 意图路由
   ├── api/pipeline.py      ← 全链路触发 + 取消
   ├── api/library.py       ← 素材库查询 (novels/chapters/characters/scenes/shots)
   ├── api/agents.py        ← 单 Agent 调用 (重新生成)
   ├── api/videos.py        ← 视频管理
   ├── api/settings.py      ← Cookie / LLM 配置
   ├── api/tasks.py         ← 任务管理
   └── events.py            ← SSE 进度推送
        │
   直接调用 (同一进程)
        │
src/aicomic/ (现有，不动)
   ├── orchestrator.py      ← run_chapter() 全链路
   ├── agents/*             ← 单 Agent
   ├── doubao/              ← 浏览器自动化
   ├── db/repository.py     ← SQLite
   └── parsers/*            ← 文件摄入
```

| 层 | 技术 | 理由 |
|---|---|---|
| 前端 | React 18 + TS + Vite + shadcn/ui + Tailwind | web-design skill 指导 UI，shadcn/ui 契合设计体系 |
| 后端 | FastAPI + uvicorn | 异步原生，SSE 开箱即用，Python 与现有 Agent 同语言 |
| 实时推送 | SSE | 单向进度推送，比 WebSocket 简单够用 |
| 任务调度 | BackgroundTasks (同一进程) | 单用户场景无需 Celery |
| 数据库 | 现有 SQLite (WAL 模式) | 已有，读写分离通过 WAL 实现 |
| 部署 | 前端构建产物放入 server/static/，一个命令启动 | `python -m server` |

---

## 3. 导航 & 页面结构

```
┌──────────────────────────────────────────────┐
│  🎬 AI漫剧                            [设置]  │
├────────────┬─────────────────────────────────┤
│ 💬 助手     │         主内容区                 │
│ 📚 素材库   │                                  │
│ 🎞️ 视频     │                                  │
│ 🔐 Cookie   │                                  │
│ ────────── │                                  │
│ 📋 任务中心  │                                  │
│ ⚙️ 系统设置  │                                  │
└────────────┴─────────────────────────────────┘
```

### 3.1 💬 AI漫剧助手 (Chat)

- 对话式交互，用户自然语言描述需求
- 支持文件上传 (.txt / .docx / .pdf)
- LLM 做 NLU 意图分类，路由到 Pipeline / 单 Agent / 查询
- SSE 流式回复（先返回到文本，再推进度）
- 上下文记忆：DB 持久化 + LLM 摘要（最近 N 轮完整 + 早期摘要）
- System Prompt 注入当前小说、章节、角色/场景列表
- 历史对话可查看

### 3.2 📚 漫剧素材库

层级结构：

```
📚 素材库
├── 逆天邪神
│   ├── 第1章 云澈、萧澈
│   │   ├── 👤 人物卡片 (6人)
│   │   │   ├── 萧澈 [预览大图] [重新生成]
│   │   │   └── ...
│   │   ├── 🏞️ 场景卡片 (3场景)
│   │   │   ├── 婚房 [预览大图] [重新生成]
│   │   │   └── ...
│   │   ├── 📜 剧本 (JSON 可折叠预览)
│   │   └── 🎬 镜头 (9 shots)
│   │       └── 每个 Shot 可展开查看分镜细节 + 提示词
│   ├── 第2章 情不自禁
│   │   └── ...
│   └── [导入新章节]
└── [导入新小说]
```

- 预览：点击卡片放大显示图片/视频
- 重新生成：仅调用对应单个 Agent（如 ImageGenerator 重跑该角色），传递额外提示词
- 素材数据来源：现有 SQLite 查询，图片/视频路径拼装成可访问 URL

### 3.3 🎞️ 漫剧视频

- 按章节列出已生成的视频
- 支持播放、下载
- 重新生成按钮绑定 `ShotVideoGenerator + VideoComposer`
- 触发前弹窗警告："⚠️ 此操作将消耗豆包额度，已生成的视频不会返回，是否继续？"
- 显示预估额度消耗

### 3.4 🔐 豆包 Cookie 验证

- 显示当前 Cookie 状态（有效 / 过期 / 未设置）
- 图文引导：分步截图教用户如何从浏览器 DevTools 中获取 Cookie
- 输入框粘贴 Cookie + 保存
- 后端提供验证接口（尝试访问豆包页面检测 Cookie 是否有效）

### 3.5 📋 任务中心

- 当前运行中的任务 + 进度条
- 历史任务列表（按时间倒序）
- 失败任务可重试
- 运行中任务可取消
- SSE 实时更新

### 3.6 ⚙️ 系统设置

- LLM API Key 配置（DeepSeek / Claude）
- 输出目录配置
- 图片质量偏好
- 视频时长偏好

---

## 4. Chat 意图路由

```
用户输入: "重新生成萧澈的图，眼神要更冷峻"
              │
              ▼
    ┌─────────────────────┐
    │  NLU 意图解析        │  ← FastAPI 调用 LLM
    │  (轻量 prompt)       │
    └──────┬──────────────┘
           │
    ┌──────┴──────────────┐
    │ {                    │
    │   intent: "regenerate",
    │   target: "character",
    │   name: "萧澈",       │
    │   params: "眼神更冷峻" │
    │ }                    │
    └──────┬──────────────┘
           │
           ▼
    ImageGenerator.execute(
      character_name="萧澈",
      extra_hint="眼神更冷峻"
    )
```

### 支持意图

| Intent | Chat 示例 | 路由 |
|--------|----------|------|
| `generate_chapter` | "生成第3章" | Orchestrator.run_chapter() |
| `regenerate_character` | "重新生成萧澈的图" | ImageGenerator (单角色) |
| `regenerate_scene` | "婚房场景换一张" | ImageGenerator (单场景) |
| `regenerate_video` | "第2章视频重新生成" | ShotVideoGenerator + VideoComposer |
| `import_novel` | 上传文件 | Parser → DB |
| `query` | "萧澈现在用的什么图？" | DB 查询 |
| `regenerate_char_design` | "萧澈形象设计重新来" | CharDesigner + ImageGenerator |

### 上下文记忆

- 每个对话存 SQLite，关联 `novel_id` / `chapter_id`
- 保留最近 N 轮（默认 20）完整上下文
- 早期对话用 LLM 摘要压缩
- 切换小说/章节时自动变更 System Prompt

### 文件上传

- Chat 中附加文件，或拖拽到对话区
- 后端解析 (.txt/.docx/.pdf) → 入库 → 返回 novel_id + chapter_id
- 解析结果在 Chat 中反馈给用户

---

## 5. API 端点设计

### 5.1 Chat & Pipeline

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/send` | 发送消息 `{ message, files?, chapter_id?, novel_id? }` |
| GET | `/api/chat/history` | 聊天历史 `?chapter_id=X` |
| POST | `/api/pipeline/run` | 启动全链路 `{ chapter_id, with_images?, with_video? }` |
| POST | `/api/pipeline/cancel` | 取消运行 `{ task_id }` |

### 5.2 素材库

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/novels` | 小说列表 |
| GET | `/api/novels/{id}/chapters` | 章节列表 |
| GET | `/api/chapters/{id}/characters` | 角色卡片含图片 |
| GET | `/api/chapters/{id}/scenes` | 场景卡片含图片 |
| GET | `/api/chapters/{id}/script` | 剧本 JSON |
| GET | `/api/chapters/{id}/shots` | 分镜列表(含提示词) |
| POST | `/api/upload` | 上传小说文件 |

### 5.3 单 Agent 调用 (重新生成)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agents/run` | `{ agent, target_type, target_id, extra? }` |

target_type: `character` | `scene` | `video`
agent: `image-generator` | `char-designer` | `scene-designer` | `shot-video-generator`

### 5.4 视频

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chapters/{id}/videos` | 视频列表 |
| POST | `/api/chapters/{id}/videos/regenerate` | 重新生成 |

### 5.5 Settings

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings/cookie-status` | 豆包 Cookie 状态 |
| POST | `/api/settings/cookie` | 保存 Cookie |
| GET | `/api/settings/llm` | LLM 配置 |
| POST | `/api/settings/llm` | 更新 LLM 配置 |

### 5.6 任务

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 任务列表 (含当前运行) |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| POST | `/api/tasks/{id}/retry` | 重试任务 |

### 5.7 SSE

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/events/{task_id}` | SSE 事件流 |

### SSE 事件格式

```
event: progress
data: {"step": "scriptwriter", "status": "done", "pct": 10, "message": "剧本已完成"}

event: progress
data: {"step": "char-designer", "status": "running", "pct": 20, "message": "生成角色设定..."}

event: complete
data: {"status": "done", "final_video_path": "ch3_final.mp4"}

event: error
data: {"status": "failed", "error": "Cookie expired", "failed_at": "image-generator"}
```

---

## 6. 数据库（新增表）

在现有 SQLite 基础上新增：

```sql
-- 聊天记录
CREATE TABLE chat_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER REFERENCES chapter(id),  -- NULL 表示全局对话
    role TEXT NOT NULL,       -- 'user' | 'assistant' | 'system'
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',  -- {intent, task_id, ...}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 聊天摘要（早期对话压缩）
CREATE TABLE chat_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER REFERENCES chapter(id),  -- NULL 表示全局摘要
    summary_text TEXT NOT NULL,
    start_msg_id INTEGER NOT NULL,
    end_msg_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 系统设置 (KV store)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 任务记录
CREATE TABLE task (
    id TEXT PRIMARY KEY,       -- UUID
    type TEXT NOT NULL,        -- 'pipeline' | 'agent'
    chapter_id INTEGER REFERENCES chapter(id),
    status TEXT NOT NULL,      -- 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
    params TEXT DEFAULT '{}',  -- 请求参数
    progress REAL DEFAULT 0,   -- 0.0 - 1.0
    result TEXT DEFAULT '{}',
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. 部署 & 启动

### 开发模式
```bash
# Terminal 1: FastAPI (端口 8000)
cd server && uvicorn main:app --reload --port 8000

# Terminal 2: Vite dev server (端口 5173, 代理 API 到 8000)
cd web && npm run dev
```

### 生产模式
```bash
# 构建前端 → server/static/
cd web && npm run build

# 启动一体化服务 (端口 8000)
python -m server --port 8000
# FastAPI serve static/ + API routes on :8000
```

---

## 8. 开发阶段规划

| Phase | 内容 | 预估 |
|-------|------|------|
| Phase 1 | FastAPI 骨架 + SSE + 任务管理 + 现有 DB 对接 | 后端基础 |
| Phase 2 | React 项目初始化 + 导航框架 + 页面路由 | 前端壳子 |
| Phase 3 | 素材库 (浏览+预览+重新生成) | 核心功能 |
| Phase 4 | Chat 助手 (NLU意图 + 文件上传 + 上下文记忆) | 核心功能 |
| Phase 5 | 视频管理 (浏览+播放+重新生成含额度警告) | 核心功能 |
| Phase 6 | Cookie 设置 + 系统设置 + 打包部署 | 收尾 |
