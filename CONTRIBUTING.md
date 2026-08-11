# Contributing to AI漫剧 (AI Comic Generator)

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- **Python 3.12+** — `python --version`
- **Node.js 20+** — `node --version`
- **Playwright** — `playwright install chromium`
- **Tesseract OCR** (optional, for scanned PDF support) — `tesseract --version`

### Quick Start

```bash
# Clone and install
git clone <repo-url> && cd first_agent

# Backend
pip install -e ".[dev]"

# Frontend
cd web && npm install && cd ..

# Configure
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml — add your DeepSeek API Key

# Run
python -m server
# Open http://localhost:8000
```

### Running Tests

```bash
python -m pytest tests/ -v
# 166 tests, expect all passing
```

## Code Style

- **Python**: Follow PEP 8. Use type hints.
- **TypeScript/React**: Follow the project's existing patterns. Run `npm run lint` in `web/`.
- **Comments**: Currently in Chinese. New code may use either Chinese or English — just be consistent within a file.

## Project Architecture

```
src/aicomic/agents/   — 10 AI agents that form the pipeline
src/aicomic/doubao/   — Playwright browser automation for Doubao image/video
src/aicomic/db/       — SQLite data layer
server/               — FastAPI web server + REST API
web/                  — React 18 + TypeScript frontend
tests/                — pytest test suite
```

Each agent implements `AgentInterface` (`src/aicomic/interface.py`) with `validate_input()` + `execute()`. The orchestrator (`src/aicomic/orchestrator.py`) chains them in order.

## Pull Request Process

1. Create a feature branch from `master`
2. Make your changes, add tests if applicable
3. Run `python -m pytest tests/` — all tests must pass
4. Open a PR with a clear description of what changed and why
5. Keep PRs focused — one concern per PR

## Questions?

Open an issue or start a discussion. We're happy to help!

---

*This project uses the MIT License. By contributing, you agree that your contributions will be licensed under the same terms.*
