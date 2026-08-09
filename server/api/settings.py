"""系统设置端点 — Cookie 配置、LLM 配置."""
import json
import logging
import threading
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

DB_PATH = Path("data/aicomic.db")
COOKIE_FILE = Path("data/doubao_cookies.json")
STATE_FILE = Path("data/doubao_state.json")
DOUBAO_URL = "https://www.doubao.com"

logger = logging.getLogger("aicomic-server")
router = APIRouter(prefix="/api/settings", tags=["settings"])


# ═══════════════════════════════════════════════════════
# 一键自动登录
# 流程: POST /cookie-auto → 浏览器打开 → 用户登录
#       → POST /cookie-auto-confirm → 后台线程保存+关闭
#       → POST /cookie-auto-cancel → 关闭不保存
# ═══════════════════════════════════════════════════════

_login_state: dict = {"running": False, "browser": None, "playwright": None,
                      "error": None, "confirmed": False}

@router.get("/cookie-auto-status")
def cookie_auto_status():
    return {"running": _login_state["running"], "confirmed": _login_state.get("confirmed", False),
            "error": _login_state["error"]}


@router.post("/cookie-auto")
async def cookie_auto():
    global _login_state

    # Auto-clean stale state
    if _login_state["running"]:
        b = _login_state.get("browser")
        alive = False
        if b:
            try: b.pages; alive = True
            except: pass
        if not alive:
            _login_state = {"running": False, "browser": None, "playwright": None,
                            "error": None, "confirmed": False}

    if _login_state["running"]:
        raise HTTPException(409, "已有登录流程在进行中，请先关闭浏览器窗口再重试")

    _login_state = {"running": True, "browser": None, "playwright": None,
                    "error": None, "confirmed": False}

    def _open():
        global _login_state
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            _login_state["playwright"] = pw

            profile_dir = Path("data/doubao_profile")
            profile_dir.mkdir(parents=True, exist_ok=True)
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            _login_state["browser"] = browser
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto(f"{DOUBAO_URL}/chat/create-image", wait_until="domcontentloaded")
            logger.info("Doubao login: browser opened, waiting for confirm...")

            import time as _time
            while _login_state["running"] and not _login_state.get("confirmed"):
                _time.sleep(2)
                try: browser.pages
                except:
                    _login_state["error"] = "Browser closed"
                    _login_state["running"] = False
                    break

            # Save if confirmed
            if _login_state.get("confirmed") and _login_state["running"]:
                try:
                    cookies = browser.cookies()
                    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                        json.dump(cookies, f, ensure_ascii=False, indent=2)
                    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    browser.storage_state(path=str(STATE_FILE))
                    logger.info(f"Doubao login: saved {len(cookies)} cookies")
                except Exception as e:
                    logger.error(f"Save failed: {e}")
                    _login_state["error"] = str(e)

            browser.close()
            pw.stop()
            _login_state = {"running": False, "browser": None, "playwright": None,
                            "error": _login_state.get("error"), "confirmed": False}
            logger.info("Doubao login: done")
        except Exception as e:
            logger.error(f"Login error: {e}")
            _login_state = {"running": False, "browser": None, "playwright": None,
                            "error": str(e), "confirmed": False}

    threading.Thread(target=_open, daemon=True).start()
    return {"status": "opened", "message": "浏览器已打开，登录后点击「确认已登录」"}


@router.post("/cookie-auto-confirm")
def cookie_auto_confirm():
    """用户确认已登录 → 后台线程保存并关闭."""
    if not _login_state["running"]:
        raise HTTPException(400, "没有正在进行的登录流程")
    _login_state["confirmed"] = True
    return {"status": "ok", "message": "已确认，正在保存 Cookie…"}


@router.post("/cookie-auto-cancel")
def cookie_auto_cancel():
    """取消 — 后台线程检测到 running=False 会关闭浏览器."""
    _login_state["running"] = False
    _login_state["confirmed"] = False
    return {"status": "cancelled", "message": "正在关闭浏览器…"}


# ═══════════════════════════════════════════════════════
# Cookie 管理
# ═══════════════════════════════════════════════════════

@router.get("/cookie-status")
def cookie_status():
    state_valid = STATE_FILE.exists() and STATE_FILE.stat().st_size > 100
    cookie_valid = COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 10
    return {"valid": state_valid or cookie_valid, "state_file": str(STATE_FILE),
            "cookie_file": str(COOKIE_FILE)}


class CookieBody(BaseModel):
    value: str


@router.post("/cookie")
def set_cookie(body: CookieBody):
    cookies_list = None
    try:
        parsed = json.loads(body.value)
        if isinstance(parsed, list): cookies_list = parsed
        elif isinstance(parsed, dict) and "cookies" in parsed: cookies_list = parsed["cookies"]
        elif isinstance(parsed, str): cookies_list = json.loads(parsed)
    except (json.JSONDecodeError, TypeError): pass

    if cookies_list is None:
        raw = body.value.strip()
        if "=" in raw:
            cookies_list = []
            for part in raw.split(";"):
                part = part.strip()
                if "=" in part:
                    n, _, v = part.partition("=")
                    if n.strip() and v.strip():
                        cookies_list.append({"name": n.strip(), "value": v.strip(),
                                            "domain": ".doubao.com", "path": "/"})
    if cookies_list is None:
        raise HTTPException(400, "无法解析 Cookie 格式")

    # Delete stale state so browser client uses cookies
    if STATE_FILE.exists(): STATE_FILE.unlink()

    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies_list, f, ensure_ascii=False, indent=2)

    # Also write storageState format
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookies": cookies_list, "origins": []}, f, ensure_ascii=False, indent=2)

    return {"status": "ok", "cookie_count": len(cookies_list),
            "message": f"已保存 {len(cookies_list)} 个 Cookie"}


@router.post("/cookie-verify")
def cookie_verify():
    if not STATE_FILE.exists() and not COOKIE_FILE.exists():
        return {"valid": False, "error": "未配置任何 Cookie"}
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        ctx_kwargs = {"accept_downloads": True}
        if STATE_FILE.exists(): ctx_kwargs["storage_state"] = str(STATE_FILE)
        ctx = browser.new_context(**ctx_kwargs)
        if not STATE_FILE.exists() and COOKIE_FILE.exists():
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                ctx.add_cookies(json.load(f))
        page = ctx.new_page()
        page.goto(DOUBAO_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)
        u = page.url.lower()
        t = page.title()
        valid = "login" not in u and "passport" not in u and "登录" not in t
        ctx.close(); browser.close(); pw.stop()
        return {"valid": valid, "current_url": page.url, "title": t}
    except Exception as e:
        return {"valid": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# LLM 配置
# ═══════════════════════════════════════════════════════

@router.get("/llm")
def get_llm_config():
    from server.config import load_config
    config = load_config()
    backend = config.get("backend", "deepseek")
    bc = config.get(backend, {})
    key = bc.get("api_key", "")
    masked = key[:4] + "•" * 8 + key[-4:] if len(key) > 12 else (key[:2] + "••••" if key else "未配置")
    return {"backend": backend, "model": bc.get("model", ""), "base_url": bc.get("base_url", ""),
            "api_key_masked": masked, "has_key": bool(key)}


class LLMBody(BaseModel):
    backend: str = "deepseek"
    api_key: str = ""
    model: str = ""
    base_url: str = ""


@router.post("/llm")
def set_llm_config(body: LLMBody):
    if body.backend not in ("deepseek", "claude"):
        raise HTTPException(400, "Backend must be 'deepseek' or 'claude'")
    from server.config import load_config, save_config
    config = load_config()
    config["backend"] = body.backend
    if body.backend not in config: config[body.backend] = {}
    if body.api_key: config[body.backend]["api_key"] = body.api_key
    if body.model: config[body.backend]["model"] = body.model
    if body.base_url: config[body.backend]["base_url"] = body.base_url
    save_config(config)
    masked = body.api_key[:4] + "••••" + body.api_key[-4:] if len(body.api_key) > 10 else "••••"

    # 保存 Key 后尝试重新初始化引擎
    from server.main import init_orchestrator
    ok, err = init_orchestrator()
    if ok:
        logger.info("LLM config updated, orchestrator re-initialized")
    else:
        logger.warning("LLM config updated but orchestrator init failed: %s", err)

    return {"status": "ok", "backend": body.backend, "api_key_masked": masked,
            "orchestrator_ready": ok}


# ═══════════════════════════════════════════════════════
# 视频模型偏好
# ═══════════════════════════════════════════════════════

@router.get("/video-model")
def get_video_model():
    from server.db import get_db, SettingsStore
    conn = get_db()
    try:
        store = SettingsStore(conn)
        return {"model": store.get("video_model") or "mini"}
    finally:
        conn.close()


class VideoModelBody(BaseModel):
    model: str  # "mini" or "fast"

@router.post("/video-model")
def set_video_model(body: VideoModelBody):
    if body.model not in ("mini", "fast"):
        raise HTTPException(400, "model must be 'mini' or 'fast'")
    from server.db import get_db, SettingsStore
    conn = get_db()
    try:
        store = SettingsStore(conn)
        store.set("video_model", body.model)
        return {"status": "ok", "model": body.model}
    finally:
        conn.close()
