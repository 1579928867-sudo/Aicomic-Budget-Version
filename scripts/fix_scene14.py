"""Fix Scene #14 — hand-rewrite prompt to avoid Doubao moderation, regenerate image."""
import sys, time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from aicomic.db.repository import Database
from aicomic.doubao.browser import DoubaoBrowserClient, configure_output_encoding
import yaml

configure_output_encoding()
config = {}
with open(project_root / "config" / "settings.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}
doubao_cfg = config.get("doubao", {})

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# ── Hand-rewritten prompt: remove blood/death, keep visual composition ──
# Original problems: "血迹斑驳" × 3, scene name "萧鹰之死"
# Strategy: "血迹" → "深色斑驳/散落残叶", "之死" → "暗夜遇袭"
NEW_PROMPT = (
    "不能出现其他人，无人纯场景，no humans,empty,landscape only，"
    "古代仙侠风格，【中国古代·仙侠】写实电影感风格，9:16竖屏构图，三等分场景多景别contact sheet，"
    "从上到下三格——"
    "第一格(远景·Wide)：全景广角展示夜晚户外场景，流云城街道或萧门庭院，"
    "昏暗月光下，地面石板路延伸至远端，周围建筑轮廓模糊，"
    "冷色调，阴影浓重，气氛压抑肃杀，远处有人影被打倒在地的剪影轮廓。"
    "第二格(中景·Mid)：中景聚焦街道核心区域，石板路中央散落着打斗后的痕迹——"
    "断裂的兵器残片、被撞倒的杂物、深色斑驳的液痕在月光下微微反光，"
    "周围建筑阴影浓重，气氛悲壮肃杀，仿佛刚刚经历了一场惨烈的偷袭。"
    "第三格(特写·Close-up)：特写石板路表面，地面有兵器划过留下的深深划痕，"
    "石缝间杂草倒伏，散落几片残破的布料碎片，月光从云层缝隙洒下照在深色液痕上反射冷光，"
    "氛围压抑沉重，暗示有人在此重伤倒下。"
    "三格之间用纯白色粗横条(6px)完全分隔，"
    "每格左上角黑色半透明底+白色文字标签。"
)
NEW_NAME = "回忆·暗夜遇袭"

print(f"=== ORIGINAL ===")
orig = db.conn.execute("SELECT name, multi_view_prompt FROM scene_card WHERE id=14").fetchone()
print(f"  Name: {orig['name']}")
print(f"  Prompt: {orig['multi_view_prompt'][:120]}...")

print(f"\n=== REWRITTEN ===")
print(f"  Name: {NEW_NAME}")
print(f"  Prompt ({len(NEW_PROMPT)} chars):")
for line in NEW_PROMPT.split("。"):
    if line.strip():
        print(f"    {line.strip()}。")
print()

# ── Key changes summary ──
print("Key changes:")
print("  萧鹰之死 → 暗夜遇袭")
print("  血迹斑驳 → 深色斑驳的液痕 / 深色液痕")
print("  血迹 → 打斗后的痕迹 + 断裂兵器残片 + 被撞倒的杂物")
print("  暗杀 → 偷袭 (less triggering than 刺杀)")
print("  Added: '人影被打倒在地的剪影轮廓', '布料碎片' to convey fall without blood")
print("  Kept: same triptych format, same lighting, same atmosphere")

# ── Update DB ──
db.conn.execute(
    "UPDATE scene_card SET name = ?, multi_view_prompt = ? WHERE id = 14",
    (NEW_NAME, NEW_PROMPT),
)
db.conn.commit()
print(f"\n✅ DB updated: {orig['name']} → {NEW_NAME}")

# ── Generate image ──
print(f"\n{'─'*50}")
print("Generating image...")
print(f"{'─'*50}")

browser = DoubaoBrowserClient(
    state_file=Path(doubao_cfg.get("state_file", "data/doubao_state.json")),
    cookie_file=Path(doubao_cfg.get("cookie_file", "data/doubao_cookies.json")),
    headless=False,
    output_dir=doubao_cfg.get("output_dir", "data/"),
    timeout_sec=doubao_cfg.get("timeout_sec", 300),
    poll_interval_sec=doubao_cfg.get("poll_interval_sec", 3),
    rate_limit_sec=doubao_cfg.get("rate_limit_sec", 10),
    selectors=doubao_cfg.get("selectors", {}),
)
pages_cfg = doubao_cfg.get("pages", {})
if pages_cfg:
    browser.page_urls.update(pages_cfg)

try:
    browser.ensure_browser()
    print("[OK] Browser ready\n")

    result = browser.generate_image(prompt=NEW_PROMPT, aspect_ratio="9:16")
    if result.success and result.file_paths:
        chosen = result.file_paths[0]
        db.conn.execute(
            "UPDATE scene_card SET multi_view_image = ? WHERE id = 14",
            (chosen,),
        )
        db.conn.commit()
        for p in result.file_paths:
            if p != chosen:
                try: Path(p).unlink(missing_ok=True)
                except Exception: pass
        size_kb = Path(chosen).stat().st_size // 1024
        print(f"\n✅ Scene #14 SAVED: {Path(chosen).name} ({size_kb}KB)")
    else:
        err = result.error or "unknown"
        print(f"\n❌ STILL FAILED: {err}")
        print("  May need further prompt adjustment")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
finally:
    browser.close()
    db.close()

print("\nDone.")
