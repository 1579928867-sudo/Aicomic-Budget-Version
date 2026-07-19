"""Interactive Doubao login — opens a browser, you log in manually, saves browser profile.

Uses Playwright's storageState (not just cookies) to persist the full session
across runs — cookies + localStorage + sessionStorage + IndexedDB.

Usage:
    python scripts/login_doubao.py
"""

import sys
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Error: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)

STATE_FILE = Path("data/doubao_state.json")
DOUBAO_URL = "https://www.doubao.com"

print("=" * 60)
print("  Doubao 登录助手 (storageState 模式)")
print("=" * 60)
print()
print("即将打开浏览器窗口，请手动登录豆包。")
print(f"登录成功后浏览器会话将保存到 {STATE_FILE}")
print("(保存的是完整浏览器状态，不只是 cookie)")
print()

input("按 Enter 打开浏览器...")

pw = sync_playwright().start()

# Use persistent context — this automatically saves/restores everything
browser = pw.chromium.launch_persistent_context(
    user_data_dir=str(Path("data/doubao_profile")),
    headless=False,
    args=["--disable-blink-features=AutomationControlled"],
)
page = browser.pages[0] if browser.pages else browser.new_page()

# Navigate to Doubao
page.goto(f"{DOUBAO_URL}/chat/create-image", wait_until="domcontentloaded")
print()
print("浏览器已打开，请在窗口中操作：")
print("  1. 如果页面跳转到登录页，请用手机号/微信扫码登录")
print("  2. 确保能看到图片生成页面（说明已登录成功）")
print()

input("登录成功后按 Enter 保存状态...")

# Save storage state (full browser profile)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
browser.storage_state(path=str(STATE_FILE))

print()
print(f"✓ 浏览器状态已保存到 {STATE_FILE}")
print()

# Verify
page.goto(DOUBAO_URL, wait_until="domcontentloaded")
import time
time.sleep(2)
current_url = page.url.lower()
if "login" in current_url or "passport" in current_url:
    print("⚠ 警告: 似乎未登录成功 (当前 URL 仍包含 login/passport)")
    print(f"  当前 URL: {page.url}")
else:
    print("✓ 验证通过: 已登录豆包")

browser.close()
pw.stop()
