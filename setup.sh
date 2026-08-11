#!/usr/bin/env bash
# AI漫剧 — 环境检测脚本
# 运行: bash setup.sh
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err() { echo -e "${RED}❌ $1${NC}"; }

echo "🎬 AI漫剧 环境检测"
echo "===================="
echo ""

# Python
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "Python: $PY_VER"
elif command -v python &>/dev/null; then
    PY_VER=$(python --version 2>&1)
    ok "Python: $PY_VER"
else
    err "Python 3.12+ 未安装 → https://www.python.org/downloads/"
    exit 1
fi

# Node.js
if command -v node &>/dev/null; then
    NODE_VER=$(node --version)
    ok "Node.js: $NODE_VER"
else
    warn "Node.js 未安装 → https://nodejs.org/ (前端构建需要)"
fi

# Playwright
if python3 -c "import playwright" 2>/dev/null || python -c "import playwright" 2>/dev/null; then
    ok "Playwright: 已安装"
else
    warn "Playwright 未安装 → 运行: pip install playwright && playwright install chromium"
fi

# Tesseract (optional)
if command -v tesseract &>/dev/null; then
    ok "Tesseract OCR: $(tesseract --version 2>&1 | head -1)"
else
    warn "Tesseract OCR 未安装 (可选，仅扫描版PDF需要)"
fi

echo ""

# Check config
if [ -f "config/settings.yaml" ]; then
    ok "config/settings.yaml 已配置"
else
    warn "config/settings.yaml 未配置 → 运行: cp config/settings.example.yaml config/settings.yaml"
    echo "   然后编辑 settings.yaml 填入 DeepSeek API Key"
fi

echo ""
echo "===================="
echo "如所有必需项 ✅，运行以下命令启动:"
echo ""
echo "  pip install -e ."
echo "  cd web && npm install && cd .."
echo "  python -m server"
echo ""
echo "然后打开 http://localhost:8000"
