@echo off
setlocal EnableDelayedExpansion
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
    if !errorlevel!==0 (
        %%p --version >nul 2>&1
        if !errorlevel!==0 if not defined PYTHON set PYTHON=%%p
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
for /f "tokens=2 delims=." %%a in ("%PYVER%") do set PYMINOR=%%a
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
    if !errorlevel! neq 0 (
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
    if !errorlevel! neq 0 (
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
    if !errorlevel! neq 0 (
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
