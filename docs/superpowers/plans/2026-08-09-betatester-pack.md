# 朋友内测打包 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让零技术背景的 Windows 朋友解压 zip 后，双击 `启动.bat` 即可运行 AI 漫剧。

**Architecture:** 预构建前端到 `server/static/`，消去 Node.js 依赖。`启动.bat` 负责自动检测 Python 版本 → 创建 venv → 安装依赖 → 安装 Playwright Chromium → 启动服务并打开浏览器。

**Tech Stack:** Windows Batch (.bat) + Python 3.12 + FastAPI (server/main.py) + 前端预构建静态文件

## Global Constraints

- 目标 OS: Windows 10/11
- Python >= 3.12（需自动检测）
- 朋友自备 DeepSeek API Key
- 打包格式: zip
- 无需 Node.js / npm（前端已预构建）
- 所有提示用中文

---

### Task 1: CORS 修复 — 加 localhost:8000

**Files:**
- Modify: `server/main.py:18-19`

**Interfaces:**
- Consumes: 无
- Produces: `allow_origins` 列表增加两个入口

- [ ] **Step 1: 修改 CORS allow_origins**

`server/main.py` 第 18-19 行，当前:
```python
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
```

替换为:
```python
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
```

- [ ] **Step 2: 验证服务器启动正常**

```bash
cd web && npm run build && cd ..
timeout 5 python -m server &
# 等 3 秒后 curl 验证
curl -s http://localhost:8000/api/health
```

应返回 `{"status":"ok","version":"0.2.0",...}`

- [ ] **Step 3: Commit**

```bash
git add server/main.py
git commit -m "fix(server): add localhost:8000 to CORS origins for static frontend access"
```

---

### Task 2: 新建 `启动.bat` — Windows 一键启动脚本

**Files:**
- Create: `启动.bat`

**Interfaces:**
- Consumes: Python 3.12+ on PATH, `pyproject.toml`, `config/settings.example.yaml`, `server/static/index.html` (prebuilt)
- Produces: Running server at port 8000, browser opened to localhost:8000

- [ ] **Step 1: 创建 `启动.bat`**

在项目根目录创建文件，完整内容:

```batch
@echo off
chcp 65001 >nul
title AI漫剧

echo.
echo ============================================
echo   🎬 AI漫剧 — 启动中...
echo   安装位置: %~dp0
echo ============================================
echo.

:: ── 1. 检测 Python ──
set PYTHON=
for %%p in (python python3) do (
    where %%p >nul 2>&1
    if %errorlevel%==0 (
        %%p --version >nul 2>&1
        if %errorlevel%==0 set PYTHON=%%p
    )
)
if "%PYTHON%"=="" (
    echo [❌] 未找到 Python！
    echo.
    echo 请安装 Python 3.12 或更新版本：
    echo https://www.python.org/downloads/
    echo.
    echo ⚠️ 安装时请勾选 "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

:: ── 2. 检测 Python 版本 >= 3.12 ──
for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
for /f "tokens=2 delims=." %%a in ("%PYVER%") do set PYMINOR=%%b
echo [✓] 检测到 %PYTHON% 版本 %PYVER%

if %PYMINOR% LSS 12 (
    echo [❌] Python 版本过低（需要 3.12 或更新版本）
    echo.
    echo 请从以下地址安装最新版 Python：
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ── 3. 首次运行：创建虚拟环境 ──
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [🔧] 首次运行 — 正在创建虚拟环境...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo [❌] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [✓] 虚拟环境创建完成
)

:: ── 4. 安装 Python 依赖 ──
if not exist ".venv\pip-deps-installed" (
    echo.
    echo [🔧] 正在安装 Python 依赖（约 1-2 分钟）...
    .venv\Scripts\pip install -e . --quiet
    if %errorlevel% neq 0 (
        echo [❌] 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo . > ".venv\pip-deps-installed"
    echo [✓] Python 依赖安装完成
)

:: ── 5. 安装 Playwright Chromium ──
if not exist ".venv\playwright-installed" (
    echo.
    echo [🔧] 正在下载 Chromium 浏览器（约 150MB，首次需等待）...
    .venv\Scripts\pip install playwright --quiet
    .venv\Scripts\playwright install chromium
    if %errorlevel% neq 0 (
        echo [❌] Chromium 安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo . > ".venv\playwright-installed"
    echo [✓] Chromium 安装完成
)

:: ── 6. 检测配置文件 ──
if not exist "config\settings.yaml" (
    echo.
    echo [🔧] 未检测到配置文件，正在创建模板...
    copy "config\settings.example.yaml" "config\settings.yaml" >nul
    echo [✓] 已创建 config\settings.yaml（需填入 API Key）
)

:: ── 7. 检测前端是否已构建 ──
if not exist "server\static\index.html" (
    echo.
    echo [⚠️] 前端未构建，仅 API 可用
    echo     如需完整界面，请运行：cd web ^&^& npm run build
)

:: ── 8. 确保 data/ 目录结构 ──
if not exist "data\images" mkdir "data\images"
if not exist "data\videos" mkdir "data\videos"
if not exist "data\temp" mkdir "data\temp"

:: ── 9. 启动服务器 ──
echo.
echo ============================================
echo   🟢 启动服务器...
echo ============================================
echo.
echo 正在打开浏览器 http://localhost:8000
echo.
echo ⚠️ 关闭此窗口将停止服务
echo ⚠️ 按 Ctrl+C 可随时停止
echo.

start "" http://localhost:8000
.venv\Scripts\python -m server

pause
```

- [ ] **Step 2: 手动测试启动脚本**

```bash
# 模拟首次运行（清除安装标记）
rm -rf .venv 2>/dev/null
rm -f .venv/pip-deps-installed 2>/dev/null
cmd /c 启动.bat
```

验证点:
- Python 版本检测正确
- venv 创建成功
- `pip install -e .` 成功
- `playwright install chromium` 成功
- `config/settings.yaml` 从 example 复制
- 服务启动，浏览器打开 localhost:8000
- `curl http://localhost:8000/api/health` 返回 200

- [ ] **Step 3: Commit**

```bash
git add 启动.bat
git commit -m "feat: add one-click Windows startup script (启动.bat)"
```

---

### Task 3: 新建 `使用说明.md` — 面向零基础用户

**Files:**
- Create: `使用说明.md`

**Interfaces:**
- Consumes: 无
- Produces: 用户独立阅读的 .md 文件

- [ ] **Step 1: 创建 `使用说明.md`**

在项目根目录创建文件，完整内容:

```markdown
# AI漫剧 — 使用说明

> **一个将小说自动转化为漫剧视频的工具。** 上传小说 → AI 自动改编剧本、设计角色场景、生成图片和视频 → 下载成品。

---

## 第一步：安装 Python（如已装 Python 3.12+ 可跳过）

1. 打开浏览器，访问 **https://www.python.org/downloads/**
2. 点击黄色大按钮下载最新版 Python
3. 运行下载的安装程序
4. ⚠️ **务必勾选底部的 "Add python.exe to PATH"**，否则后续无法使用
5. 点击 Install Now，等待安装完成

> 如何确认已安装？按 `Win+R`，输入 `cmd`，回车，输入 `python --version`。如显示 `Python 3.12.x` 或更高版本，说明已安装。

---

## 第二步：获取 DeepSeek API Key（免费）

1. 打开浏览器，访问 **https://platform.deepseek.com/**
2. 点击右上角「注册」，用手机号注册账号
3. 登录后，点击左侧菜单「API Keys」
4. 点击「创建 API Key」，复制生成的 `sk-` 开头的密钥
5. ⚠️ **妥善保存这个 Key，只显示一次**

> DeepSeek 新用户赠送 **500 万 token**（约可生成 2-3 章内容），用完需自行充值。

---

## 第三步：解压并启动

1. 将收到的 `aicomic-beta.zip` 解压到**你喜欢的任意位置**（桌面、D盘、文档文件夹……都可以）
2. 找到解压出的文件夹里的 `启动.bat`，**双击运行**
3. 首次运行会自动安装依赖（约 3-5 分钟），请耐心等待
4. 看到「🟢 启动服务器」后，**浏览器会自动打开** http://localhost:8000
5. 之后每次使用只需双击 `启动.bat`，几秒内启动

---

## 第四步：首次配置

### 4.1 填入 API Key

1. 浏览器打开后，点击左侧「系统设置」
2. 在「DeepSeek API Key」输入框中粘贴你复制的 `sk-` 密钥
3. 点击「保存」

### 4.2 登录豆包（用于图片和视频生成）

1. 点击左侧「豆包 Cookie」
2. 点击蓝色「打开浏览器自动登录」按钮
3. 在弹出的浏览器窗口中，扫码或输入手机号登录豆包
4. 登录成功后，回到网页点击「确认已登录」
5. 看到「已保存 ✓」即完成

---

## 第五步：开始生成

1. 准备好小说文件（支持 `.txt` / `.docx` / `.pdf` 格式）
2. 在聊天页面上传文件（拖拽或点击上传）
3. 在聊天框输入「生成第1章」
4. 系统开始工作，每个阶段完成后会展示结果
5. 全部完成后，去「视频管理」页查看和下载成品

### 常用指令

| 输入 | 效果 |
|------|------|
| `生成第1章` | 从第1章开始完整管线 |
| `重新生成角色设计` | 仅重新设计角色 |
| `重新生成第2章` | 重新为第2章生成 |
| `查看当前进度` | 查看各阶段完成情况 |

---

## 常见问题

### 双击 `启动.bat` 黑窗口一闪而过

- 按 `Win+R`，输入 `cmd`，回车打开命令行
- 把 `启动.bat` **拖入**命令行窗口，按回车执行
- 这样可以看到具体的错误信息

### 想删除或移动 AI 漫剧

- **想删掉？** → 直接删除解压出来的整个文件夹即可，不会在系统里留下任何残留
- **想换位置？** → 直接把文件夹剪切到新位置就行，下次双击 `启动.bat` 会自动重新创建虚拟环境（约 2 分钟）

### 端口 8000 被占用

- 错误提示通常包含 `Address already in use`
- 关闭其他可能占用端口的程序
- 或重启电脑后再试

### 豆包自动登录失败

- 确认电脑已有 Chromium 浏览器（随 Playwright 自动安装）
- 尝试手动方式：参考豆包 Cookie 页面下方的「手动复制 Cookie」步骤
- 确认豆包账号已注册并可正常使用

### Playwright 安装很慢

- Chromium 浏览器约 150MB，下载需要一些时间
- 如下载失败，可尝试手动安装：
  - 打开命令行，输入 `pip install playwright`
  - 再输入 `playwright install chromium`

### 生成的图片/视频在哪里

- 图片保存在解压目录的 `data/images/` 下
- 视频保存在 `data/videos/` 下
- 也可在网页「素材库」和「视频管理」页面查看和下载

---

## 额度说明

| 服务 | 免费额度 | 约可用 |
|------|----------|--------|
| DeepSeek API | 500 万 token（新用户） | 2-3 章 |
| 豆包生图 | 每日免费 | 约 10-20 张 |
| 豆包生视频（即梦） | 每日 3 次 | 3 段视频 |

> 豆包额度用完后需等到第二天自动刷新。已生成的内容不会丢失。

---

## 获取帮助

遇到问题？联系开发者并附上：
- 错误截图
- `启动.bat` 窗口中的错误文字
- 操作到哪一步出现问题
```

- [ ] **Step 2: Commit**

```bash
git add 使用说明.md
git commit -m "docs: add user-friendly quickstart guide (使用说明.md)"
```

---

### Task 4: 预构建前端

**Files:**
- Create: `server/static/` (目录 + 构建产物，已 gitignored)

**Interfaces:**
- Consumes: `web/src/**` (React 源码), `web/package.json`, `web/vite.config.ts`
- Produces: `server/static/index.html` + JS/CSS/assets

- [ ] **Step 1: 构建前端**

```bash
cd web
npm install
npm run build
cd ..
```

- [ ] **Step 2: 验证构建产物**

```bash
ls server/static/index.html
ls server/static/assets/
```

应看到 `index.html` 和 `assets/` 目录（含 JS/CSS 文件）。

- [ ] **Step 3: 验证前端可正常加载**

启动服务器后访问 http://localhost:8000，确认:
- 3D 球体封面页正常渲染
- 各页面路由正常工作
- 无 404 或空白页

> 此步骤不单独 commit，产物 `.gitignored`，仅用于 zip 打包。

---

### Task 5: 打包 zip

- [ ] **Step 1: 清除不需要的文件**

```bash
# 删除之前的安装标记（朋友环境需重新安装）
rm -rf .venv
rm -f .venv/pip-deps-installed .venv/playwright-installed 2>/dev/null

# 删除已有的 settings.yaml（朋友需要自动从 example 生成）
rm -f config/settings.yaml

# 清理缓存
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null
find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null
rm -rf web/node_modules 2>/dev/null
rm -rf .venv 2>/dev/null
```

- [ ] **Step 2: 确认 data/ 目录结构**

```bash
mkdir -p data/images data/videos data/temp
# 确保 data/ 下没有敏感数据（DB 可保留空表模板）
# 当前 data/aicomic.db 含开发测试数据，清空或替换为空 DB
```

- [ ] **Step 3: 打包为 zip**

```bash
# 方法 1: PowerShell
powershell -Command "Compress-Archive -Path '启动.bat','使用说明.md','config','server','src','pyproject.toml','data','README.md','LICENSE','CONTRIBUTING.md' -DestinationPath 'aicomic-beta.zip'"

# 方法 2: 手动用 Windows 右键 → 发送到 → 压缩文件夹
# 确保包含：启动.bat, 使用说明.md, config/, server/, src/, pyproject.toml, data/, README.md, LICENSE
# 排除：__pycache__/, *.pyc, .git/, .venv/, node_modules/, web/ (前端已在 server/static/)
```

- [ ] **Step 4: 验证 zip 内容**

```bash
powershell -Command "(Get-ChildItem aicomic-beta.zip).Length / 1MB"
# 确认大小合理（预计 10-30MB，不含 Chromium）
```

关键检查:
- `server/static/index.html` 在 zip 中 ✅
- `启动.bat` 在 zip 根目录 ✅
- `使用说明.md` 在 zip 根目录 ✅
- `config/settings.example.yaml` 在 zip 中 ✅
- `config/settings.yaml` **不在** zip 中（由启动脚本自动生成）✅
- `__pycache__/` 不在 zip 中 ✅

> 打包脚本不 commit，纯手动操作。

---

### Task 6: 端到端验证（模拟朋友环境）

- [ ] **Step 1: 找一个干净目录模拟朋友解压**

```bash
mkdir -p ~/Desktop/aicomic-test
cd ~/Desktop/aicomic-test
unzip /path/to/aicomic-beta.zip
```

- [ ] **Step 2: 运行启动脚本**

```cmd
启动.bat
```

- [ ] **Step 3: 验证完整流程**

- [ ] `启动.bat` 检测到 Python 版本 ✅
- [ ] venv 创建 + pip install 自动完成 ✅
- [ ] Playwright Chromium 自动安装 ✅
- [ ] `config/settings.yaml` 自动从 example 复制 ✅
- [ ] 浏览器自动打开 http://localhost:8000 ✅
- [ ] 页面正常显示（3D 球体封面）✅
- [ ] 点击各页面：素材库、视频管理、豆包 Cookie、系统设置 ✅
- [ ] 在设置页粘贴 DeepSeek Key → 保存 ✅
- [ ] 豆包 Cookie 页一键登录功能正常 ✅

- [ ] **Step 4: 结束时清理测试目录**

```bash
rm -rf ~/Desktop/aicomic-test
```

> 验证结束，zip 可以发给朋友了。
