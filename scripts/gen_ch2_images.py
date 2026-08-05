"""Run only image_generator on existing Chapter 2 (PDF) data.

Usage: py -3 scripts/gen_ch2_images.py
"""
import os, sys, time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import yaml
from aicomic.db.repository import Database
from aicomic.bus import AgentBus
from aicomic.orchestrator import Orchestrator
from aicomic.doubao.browser import DoubaoBrowserClient
from aicomic.agents.image_generator import ImageGeneratorAgent
from aicomic.agents.scriptwriter import ScriptwriterAgent
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.agents.char_designer import CharacterDesignerAgent
from aicomic.agents.scene_designer import SceneDesignerAgent
from aicomic.agents.shot_visualizer import ShotVisualizerAgent
from aicomic.agents.outfit_manager import OutfitManagerAgent
from aicomic.llm.deepseek import DeepSeekClient

config_path = project_root / "config" / "settings.yaml"
config = yaml.safe_load(open(config_path, encoding="utf-8")) if config_path.exists() else {}

api_key = os.environ.get("DEEPSEEK_API_KEY") or config.get("deepseek", {}).get("api_key", "")
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not set", file=sys.stderr)
    sys.exit(1)

db = Database(project_root / "data" / "aicomic.db")
db.connect()
db.init_schema()
db.migrate_schema()

# ── Check what needs images ──
outfits_need = db.conn.execute(
    "SELECT co.id, cc.name, co.tag FROM character_outfit co "
    "JOIN character_card cc ON co.character_id = cc.id "
    "WHERE co.prompt != '' AND (co.image_path = '' OR co.image_path IS NULL)"
).fetchall()
scenes_need = db.conn.execute(
    "SELECT id, name FROM scene_card "
    "WHERE multi_view_prompt != '' AND (multi_view_image = '' OR multi_view_image IS NULL)"
).fetchall()

print(f"待生成图片:")
print(f"  角色设定图: {len(outfits_need)} 个")
for o in outfits_need:
    print(f"    #{o['id']} {o['name']}/{o['tag']}")
print(f"  场景多景别: {len(scenes_need)} 个")
for s in scenes_need:
    print(f"    #{s['id']} {s['name']}")

if not outfits_need and not scenes_need:
    print("\n✅ 没有需要生成的图片，退出")
    db.close()
    sys.exit(0)

# ── Setup agents and browser ──
llm = DeepSeekClient(
    api_key=api_key,
    model=config.get("deepseek", {}).get("model", "deepseek-chat"),
    base_url=config.get("deepseek", {}).get("base_url", "https://api.deepseek.com"),
)

doubao_cfg = config.get("doubao", {})
browser_client = DoubaoBrowserClient(
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
    browser_client.page_urls.update(pages_cfg)

bus = AgentBus()
# Register all agents (needed for orchestrator to skip them)
bus.register(ScriptwriterAgent(llm_client=llm))
bus.register(ScreenwriterAgent(llm_client=llm))
bus.register(CharacterDesignerAgent(llm_client=llm))
bus.register(SceneDesignerAgent(llm_client=llm))
bus.register(OutfitManagerAgent(llm_client=llm))
bus.register(ImageGeneratorAgent(browser_client=browser_client))
bus.register(ShotVisualizerAgent(llm_client=llm))

orchestrator = Orchestrator(bus, db)

# ── Chapter 4 = PDF run ──
chapter_id = 4
script_id = 4

# Load raw_text
ch = db.conn.execute("SELECT raw_text FROM chapter WHERE id = ?", (chapter_id,)).fetchone()
raw_text = ch["raw_text"]

print(f"\n{'='*60}")
print(f"运行 Pipeline (chapter_id={chapter_id}, with_images=True)")
print(f"{'='*60}\n")

t0 = time.time()
result = orchestrator.run_chapter(
    chapter_id=chapter_id,
    raw_text=raw_text,
    with_images=True,
    with_video=False,
)
elapsed = time.time() - t0

print(f"\n{'='*60}")
print(f"结果: {'✅ 成功' if result.success else '❌ 失败'} ({elapsed:.0f}s)")
if not result.success:
    print(f"错误: {result.error}")
if result.data:
    print(f"  图片生成: {result.data.get('images_generated', 0)}")

# ── Verify ──
print(f"\n=== 验证 ===")
outfits_after = db.conn.execute(
    "SELECT co.id, cc.name, co.tag, co.image_path FROM character_outfit co "
    "JOIN character_card cc ON co.character_id = cc.id "
    "WHERE co.prompt != '' AND (co.image_path = '' OR co.image_path IS NULL)"
).fetchall()
scenes_after = db.conn.execute(
    "SELECT id, name FROM scene_card "
    "WHERE multi_view_prompt != '' AND (multi_view_image = '' OR multi_view_image IS NULL)"
).fetchall()

print(f"  角色图待补: {len(outfits_after)}")
for o in outfits_after:
    print(f"    #{o['id']} {o['name']}/{o['tag']}")
print(f"  场景图待补: {len(scenes_after)}")
for s in scenes_after:
    print(f"    #{s['id']} {s['name']}")

browser_client.close()
db.close()
