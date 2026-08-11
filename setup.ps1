# AI漫剧 — 环境检测脚本 (Windows PowerShell)
# 运行: .\setup.ps1

Write-Host "🎬 AI漫剧 环境检测" -ForegroundColor Cyan
Write-Host "===================="
Write-Host ""

$allOk = $true

# Python
try {
    $pyVer = python --version 2>&1
    Write-Host "✅ Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "❌ Python 3.12+ 未安装" -ForegroundColor Red
    Write-Host "   → https://www.python.org/downloads/"
    $allOk = $false
}

# Node.js
try {
    $nodeVer = node --version 2>&1
    Write-Host "✅ Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Node.js 未安装 (前端构建需要)" -ForegroundColor Yellow
    Write-Host "   → https://nodejs.org/"
}

# Playwright
try {
    $null = python -c "import playwright" 2>&1
    Write-Host "✅ Playwright: 已安装" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Playwright 未安装" -ForegroundColor Yellow
    Write-Host "   → 运行: pip install playwright && playwright install chromium"
}

# Tesseract (optional)
try {
    $tesVer = tesseract --version 2>&1 | Select-Object -First 1
    Write-Host "✅ Tesseract OCR: $tesVer" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Tesseract OCR 未安装 (可选)" -ForegroundColor Yellow
}

Write-Host ""

# Config
if (Test-Path "config/settings.yaml") {
    Write-Host "✅ config/settings.yaml 已配置" -ForegroundColor Green
} else {
    Write-Host "⚠️  config/settings.yaml 未配置" -ForegroundColor Yellow
    Write-Host "   → 运行: copy config\settings.example.yaml config\settings.yaml"
    Write-Host "   然后编辑 settings.yaml 填入 DeepSeek API Key"
}

Write-Host ""
Write-Host "===================="
Write-Host "如所有必需项通过，运行以下命令启动:"
Write-Host ""
Write-Host "  pip install -e ."
Write-Host "  cd web; npm install; cd .."
Write-Host "  python -m server"
Write-Host ""
Write-Host "然后打开 http://localhost:8000"
