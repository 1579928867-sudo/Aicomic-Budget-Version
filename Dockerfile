# AI漫剧 Docker 镜像
# 构建: docker build -t aicomic .
# 运行: docker compose up -d

FROM python:3.12-slim

# ── 系统依赖 ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Node.js 20 (前端构建)
    curl gnupg \
    # Playwright Chromium 依赖
    libnss3 libnspr4 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64 \
    # Tesseract OCR (扫描PDF)
    tesseract-ocr tesseract-ocr-chi-sim \
    # 杂项
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 ──
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python 依赖 ──
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# ── 前端构建 ──
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci
COPY web/ web/
RUN cd web && npm run build

# ── 应用代码 ──
COPY src/ src/
COPY server/ server/
COPY config/ config/

# ── 数据目录 ──
RUN mkdir -p /app/data /app/data/videos

# Playwright 在容器中必须 headless + no-sandbox
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV AICOMIC_CONTAINER=1

EXPOSE 8000
CMD ["python", "-m", "server"]
