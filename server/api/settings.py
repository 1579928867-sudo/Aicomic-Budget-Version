"""系统设置端点 — Cookie 配置、LLM 配置（安全：不暴露完整 API Key）."""
import json
import sqlite3
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")
COOKIE_FILE = Path("data/doubao_cookies.json")
router = APIRouter(prefix="/api/settings", tags=["settings"])


def _conn():
    c = sqlite3.connect(str(DB_PATH)); c.row_factory = sqlite3.Row; return c


# ── Cookie ──

@router.get("/cookie-status")
def cookie_status():
    cookie_valid = COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 10
    return {"valid": cookie_valid, "cookie_file": str(COOKIE_FILE)}


class CookieBody(BaseModel):
    value: str


@router.post("/cookie")
def set_cookie(body: CookieBody):
    try:
        cookies = json.loads(body.value)
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "message": f"Cookie saved to {COOKIE_FILE}"}
    except json.JSONDecodeError:
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(body.value)
        return {"status": "ok", "message": f"Raw cookie saved to {COOKIE_FILE}"}


# ── LLM ──

@router.get("/llm")
def get_llm_config():
    """获取当前 LLM 配置 — 仅返回脱敏后的部分字段."""
    from server.config import load_config
    config = load_config()
    backend = config.get("backend", "deepseek")
    backend_config = config.get(backend, {})
    api_key = backend_config.get("api_key", "")

    # 只展示前后各4位
    if len(api_key) > 12:
        masked = api_key[:4] + "•" * 8 + api_key[-4:]
    elif api_key:
        masked = api_key[:2] + "••••"
    else:
        masked = "未配置"

    return {
        "backend": backend,
        "model": backend_config.get("model", ""),
        "base_url": backend_config.get("base_url", ""),
        "api_key_masked": masked,
        "has_key": bool(api_key),
    }


class LLMBody(BaseModel):
    backend: str = "deepseek"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@router.post("/llm")
def set_llm_config(body: LLMBody):
    """更新 LLM 配置 — 每个用户设置自己的 API Key."""
    if body.backend not in ("deepseek", "claude"):
        raise HTTPException(400, "Backend must be 'deepseek' or 'claude'")

    from server.config import load_config, save_config
    config = load_config()

    config["backend"] = body.backend
    if body.backend not in config:
        config[body.backend] = {}
    if body.api_key:
        config[body.backend]["api_key"] = body.api_key
    if body.model:
        config[body.backend]["model"] = body.model
    if body.base_url:
        config[body.backend]["base_url"] = body.base_url

    save_config(config)

    # 返回脱敏信息
    masked = body.api_key[:4] + "••••" + body.api_key[-4:] if len(body.api_key) > 10 else "••••"
    return {"status": "ok", "backend": body.backend, "api_key_masked": masked}
