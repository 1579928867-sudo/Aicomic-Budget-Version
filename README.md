# 🎬 AI漫剧 — 把小说变成漫剧视频，人人都能当导演

> 10 个 AI Agent 协作，从小说到成品视频一站式生成。**平民价格，人人玩得起。**
> 一个新手写的 Agent 学习项目 — **欢迎各位大佬批评指正 🙏**

## 🙋 关于我和这个项目

我是一个正在学习 AI Agent 开发的普通程序员。AI漫剧是我用来**边学边练**的个人项目 — 通过亲手搭建一个多 Agent 协作系统，理解 Agent 之间如何通信、编排、纠错。

所以：**代码不完美，架构不优雅，实现方式可能很稚嫩。** 如果你发现了更好的做法，或者觉得哪里写得一塌糊涂——**请直接指出来，这正是我开源它的原因**。Issue、PR、评论区留言，每一种反馈都是我的学习材料。

如果你也是正在学习 Agent 开发的朋友，希望这个项目能给你一些参考（哪怕是个反面教材也行 😄）。

## 💡 为什么选短剧这个方向

短剧赛道很热，但门槛不低——专业短剧需要长时间打磨、昂贵的模型开销、以及一支懂行的团队。**AI漫剧不是专业短剧工具**，不对标一线精致作品。

我们想做的是：**让每个感兴趣的人都能先体验一把，再决定要不要加入这场短剧浪潮。**

两个关键选择让这件事变得平民：

- 🆓 **豆包（字节跳动）** 生图和视频能力**几乎免费**，每天有大量免费额度
- 💰 **DeepSeek** 文本模型**业内最低价**，处理一整章小说只要几分钱

把门槛降到最低——先玩玩看，喜欢再深入。这就是 AI漫剧的初衷。

## ✨ 功能

- **📖 多格式导入** — 支持 `.txt` / `.docx` / `.pdf`，自动识别书名和章节
- **🤖 全自动 Pipeline** — 10 个 AI Agent 协作：剧本改编 → 角色设计 → AI 生图 → AI 视频 → 自动合成
- **💬 对话式交互** — 自然语言控制，说「生成第2章」「重新生成角色萧澈」「合成视频」即可
- **🎨 智能角色设计** — 自动分析角色外貌、服装变化、场景氛围，生成设计提示词
- **📸 AI 生图** — 通过豆包/即梦生成角色设定图 + 场景环境图
- **🎥 AI 视频** — 分镜级视频生成 + 转场合成
- **🌐 Web UI** — 3D 封面页 + 对话工作台 + 素材库 + 视频管理
- **⚡ 实时进度** — SSE 推送，每阶段可审计确认后继续

## 🏗 架构

```
┌─────────────────────────────────────────────────────────┐
│  Web UI (React 18 + TypeScript + Three.js)              │
│  ChatPage · LibraryPage · VideosPage · SettingsPage      │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────┐
│  FastAPI Server (server/)                                │
│  Intent NLU → PipelineRunner / AgentRunner → EventMgr    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  Orchestrator (10-Agent Pipeline)                        │
│                                                          │
│  Scriptwriter → CharDesigner → SceneDesigner             │
│     → OutfitManager → StoryboardAgent                    │
│     → ImageGenerator → ShotVisualizer                    │
│     → ShotVideoGenerator → VideoComposer                 │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  External Services                                       │
│  DeepSeek / Claude (LLM)  +  豆包/即梦 (Image & Video)    │
└─────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- 一个 [DeepSeek API Key](https://platform.deepseek.com/api_keys)（几块钱能用很久）
- 一个豆包账号（免费注册，每天大量免费生图/视频额度）

### Docker（推荐，一键启动）

```bash
git clone <repo-url> && cd first_agent
cp config/settings.example.yaml config/settings.yaml
# 编辑 config/settings.yaml — 填入 DeepSeek API Key
# 并将 doubao.headless 改为 true（Docker 无桌面环境）
docker compose up -d
# 打开 http://localhost:8000
```

### 手动安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd first_agent

# 2. 安装后端
pip install -e .

# 3. 安装前端依赖
cd web && npm install && cd ..

# 4. 配置
cp config/settings.example.yaml config/settings.yaml
# 编辑 config/settings.yaml，填入你的 DeepSeek API Key

# 5. 启动
python -m server
# 打开 http://localhost:8000
```

### 配置豆包（用于 AI 生图/视频）

1. 启动后在浏览器打开 http://localhost:8000
2. 点击左侧「豆包Cookie」
3. 点击「一键登录」→ 在弹出浏览器中登录豆包账号
4. 系统自动保存 Cookie，即可开始生成

### 使用流程

1. **上传小说** — 在聊天页或素材库上传 `.txt`/`.docx`/`.pdf` 文件
2. **开始生成** — 在聊天框输入「生成第1章」
3. **交互确认** — 每个阶段完成后展示审计报告，确认后继续
4. **查看成品** — 在「视频管理」页查看和下载成品视频

## 🧪 测试

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## 📁 项目结构

```
├── src/aicomic/
│   ├── agents/          # 10 个 AI Agent（Pipeline 各环节）
│   ├── doubao/          # Playwright 浏览器自动化（豆包/即梦）
│   ├── db/              # SQLite 数据层
│   ├── llm/             # LLM 客户端（DeepSeek / Claude）
│   ├── parsers/         # 文件解析（txt/docx/pdf + OCR）
│   └── orchestrator.py  # Pipeline 编排器
├── server/              # FastAPI Web 服务
│   ├── api/             # REST + SSE 端点
│   ├── intent.py        # NLU 意图解析
│   └── runner.py        # 后台任务执行器
├── web/                 # React 18 前端
│   └── src/pages/       # 7 个页面组件
├── tests/               # pytest 测试套件
└── config/              # 配置文件模板
```

## 🔧 技术栈

| 层 | 技术 |
|---|---|
| LLM | DeepSeek（默认，最低价）/ Claude |
| 生图/视频 | 豆包 / 即梦（几乎免费） |
| 后端 | Python 3.12 + FastAPI + SQLite |
| 前端 | React 18 + TypeScript + Vite + Tailwind CSS 4 + Three.js |
| 浏览器自动化 | Playwright（Chromium） |
| 文件解析 | python-docx + PyMuPDF + Tesseract OCR |
| 视频处理 | MoviePy |
| 状态管理 | Zustand |

## 🤝 贡献

**新手友好，大佬请随意鞭策。** 如果你有想法、改进建议、发现 bug，或者想指出代码里写得烂的地方——欢迎提 Issue 和 PR，照脸批评不用留情。这是学习项目，批评是进步的阶梯。详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。

## 📄 许可

MIT License — 详见 [LICENSE](./LICENSE)。
