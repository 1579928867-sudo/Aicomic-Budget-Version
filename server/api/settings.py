"""系统设置端点 — Cookie 配置、LLM 配置."""
import json
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")
COOKIE_FILE = Path("data/doubao_cookies.json")

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Cookie ──

@router.get("/cookie-status")
def cookie_status():
    """检查豆包 Cookie 是否已配置."""
    cookie_valid = COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 10
    return {"valid": cookie_valid, "cookie_file": str(COOKIE_FILE)}


@router.post("/cookie")
def set_cookie(value: str):
    """保存豆包 Cookie."""
    try:
        # 尝试解析为 JSON 验证格式
        cookies = json.loads(value)
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "message": f"Cookie saved to {COOKIE_FILE}"}
    except json.JSONDecodeError:
        # 如果不是 JSON，当作原始 cookie 字符串保存
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(value)
        return {"status": "ok", "message": f"Raw cookie saved to {COOKIE_FILE}"}


# ── LLM ──

@router.get("/llm")
def get_llm_config():
    """获取当前 LLM 配置 (不返回 API key 完整值)."""
    from server.main import _load_config
    config = _load_config()

    backend = config.get("backend", "deepseek")
    backend_config = config.get(backend, {})

    # 遮盖 API key
    api_key = backend_config.get("api_key", "")
    masked_key = api_key[:4] + "****" + api_key[-4:] if len(api_key) > 8 else "****"

    return {
        "backend": backend,
        "model": backend_config.get("model", "unknown"),
        "api_key": masked_key,
        "has_key": bool(api_key),
    }


@router.post("/llm")
def set_llm_config(backend: str = "deepseek", api_key: str = "", model: str = ""):
    """更新 LLM 配置 (写入 config/settings.yaml)."""
    import yaml

    config_path = Path("config/settings.yaml")
    config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    config["backend"] = backend
    if backend not in config:
        config[backend] = {}
    if api_key:
        config[backend]["api_key"] = api_key
    if model:
        config[backend]["model"] = model

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    return {"status": "ok", "message": f"LLM config updated for backend '{backend}'"}
