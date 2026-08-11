# 朋友内测打包方案 — 设计文档

**日期**: 2026-08-09
**状态**: 设计中

## 目标

让零技术背景的朋友（仅 Windows）能用最简单的方式启动 AI 漫剧并完成一次完整生成流程。

## 核心约束

- 朋友自备 DeepSeek API Key（每人免费 500 万 token）
- 朋友环境：Windows（已装或不装 Python 3.12+）
- 打包为 zip，解压即用
- 不开源前不做，只为内测

## 用户体验流程

```
1. 安装 Python 3.12+（如已装 >=3.12 跳过）
2. 去 platform.deepseek.com 注册，复制 API Key
3. 解压 zip 到任意目录
4. 双击 "启动.bat"
   ├─ 首次：自动创建 venv → pip install → playwright install chromium → 生成 config/settings.yaml 模板
   └─ 后续：秒开，跳过安装
5. 浏览器打开 http://localhost:8000
6. 设置页粘贴 DeepSeek API Key → 保存
7. 豆包 Cookie 页 → 一键自动登录
8. 上传小说 → 聊天框输入"生成第1章"
```

## 改动清单

### 1. `启动.bat` — Windows 一键启动脚本（新建）

**功能**:
- 检测 Python 版本：`python --version`，要求 >= 3.12
  - 不满足 → 给出 python.org 下载链接，暂停
  - 满足 → 继续
- 首次运行检测：
  - 若无 `.venv/` → `python -m venv .venv`
  - 若 `server/static/` 为空 → 跳过（前端已预构建在 zip 中）
  - 若无 Playwright → `.venv\Scripts\pip install playwright && .venv\Scripts\playwright install chromium`
  - 若无 `config/settings.yaml` → 从 `config/settings.example.yaml` 复制
- 启动：`.venv\Scripts\python -m server`
- 自动打开浏览器：`start http://localhost:8000`
- 每一步打印中文提示
- 窗口标题设为"AI漫剧"
- 异常时不闪退：打印错误信息 + 暂停

**特殊处理**:
- Python 命令行可能是 `python` 也可能是 `python3`，两者都检测
- venv 内 pip 路径兼容处理（Windows 是 `.venv\Scripts\pip`）
- 首次 Playwright 安装 Chromium 约需 150MB 下载，提示用户等待

### 2. `使用说明.md` — 面向零基础用户（新建）

**结构**:
1. **你需要准备什么**（5 分钟）
   - Python 安装：python.org → 下载 Windows 版 → 勾选"Add python.exe to PATH"
   - DeepSeek Key：platform.deepseek.com → 注册 → API Keys 页面 → 复制
2. **启动**（解压 → 双击 `启动.bat`）
3. **首次配置**（粘贴 Key → 豆包登录）
4. **开始生成**（上传小说 → 发送指令）
5. **常见问题**：黑窗一闪而过 / 端口被占用 / 豆包登录失败 / Playwright 安装慢
6. **额度说明**：DeepSeek 免费 500 万 token（约 2-3 章） / 豆包每日免费额度

### 3. 预构建前端

**操作**（开发者侧，打包前执行一次）:
```
cd web && npm run build
```
产出 `server/static/`，包含 index.html + JS/CSS bundle，打包进 zip。

朋友侧无需 Node.js。

### 4. CORS 修复（小改动）

`server/main.py:18`:
```python
allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
```
加一行：
```python
allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
```
前端构建后的静态文件由 FastAPI 在同一端口 serve，按理不需要 CORS，但加 `localhost:8000` 以防有 API 调用走绝对路径。

### 5. 打包脚本（or 手动步骤）

打包 zip 内容：
```
aicomic-beta/
├── 启动.bat
├── 使用说明.md
├── config/
│   └── settings.example.yaml
├── server/        （含 static/ 预构建前端）
├── src/
├── web/           （不含 node_modules/，前端已预构建不需要）
├── pyproject.toml
├── tests/         （可选：内测版可保留）
├── data/          （空目录结构即可）
│   ├── images/
│   ├── videos/
│   └── temp/
├── README.md
├── LICENSE
└── CONTRIBUTING.md
```

排除：`.git/`、`.venv/`、`__pycache__/`、`node_modules/`、`*.pyc`、`.pytest_cache/`

### 6. 已知问题顺手修复

- **Dockerfile 第 28 行**：`pip install -e .` 在 `COPY pyproject.toml .` 之后但没有 `src/`，会导致安装失败。改为 `pip install --no-cache-dir -e ".[dev]"` 并调整 COPY 顺序（非本次核心，可延后）
- **.gitignore**：当前 `config/settings.yaml` 在 gitignore 中，导致本地修改被忽略。设计不改 gitignore（有意的安全措施），但 `启动.bat` 首次运行时自动从 example 复制。

## 不做的

- Docker 一键部署优化（朋友不做 Docker）
- Mac/Linux 启动脚本（后续按需）
- Electron 打包 / exe 打包（太重，内测不必要）
- 内置 API Key（用户选择方案 2）
- 前端代码修改（只需 build）

## 自检

- [x] 无 TBD / TODO 占位
- [x] 各部分无矛盾
- [x] 单一主题，无需拆分
- [x] 需求无歧义
