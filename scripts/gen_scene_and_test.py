"""Generate scene image for 天毒珠内部 + test Shot 1 download."""
import os, sys, time
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

from aicomic.db.repository import Database
from aicomic.llm.deepseek import DeepSeekClient

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# ── Step 1: Generate scene prompt for 天毒珠内部 via DeepSeek ──
scene = dict(db.conn.execute("SELECT * FROM scene_card WHERE id=6").fetchone())
print(f"Scene: {scene['name']}")

llm = DeepSeekClient(api_key=os.environ["DEEPSEEK_API_KEY"], model="deepseek-chat")

SCENE_PROMPT = """你是场景设计师。为以下场景生成多景别场景提示词：

场景名: {name}
氛围: {atmosphere}

要求：
1. 无人纯场景，no humans, landscape only
2. 写实电影感风格，横向16:9
3. 不能出现纯白背景，用真实环境背景
4. 输出格式：{"multi_view_prompt": "场景多景别合并提示词（9:16竖屏三联画格式，上全景/中中景/下特写，白色分隔条）"}

只输出JSON。"""

# Get atmosphere from the script
import json
script_json = json.loads(db.conn.execute(
    "SELECT raw_json FROM script WHERE id=1").fetchone()["raw_json"])

atmosphere = ""
for s in script_json["scenes"]:
    if "天毒珠内部" in s.get("scene_name", ""):
        atmosphere = s.get("atmosphere", "")
        break

print(f"Atmosphere: {atmosphere}")

prompt = SCENE_PROMPT.format(name=scene["name"], atmosphere=atmosphere)
result = llm.generate_json(system_prompt="输出纯JSON。", user_prompt=prompt, max_tokens=2048)
multi_prompt = result.get("multi_view_prompt", "")
print(f"Prompt generated: {len(multi_prompt)} chars")

# Save to DB
db.conn.execute(
    "UPDATE scene_card SET multi_view_prompt=? WHERE id=6",
    (multi_prompt,))
db.conn.commit()

# ── Step 2: Generate scene image via Doubao ──
print("\n--- Generating scene image via Doubao ---")
from aicomic.doubao.browser import DoubaoBrowserClient
browser = DoubaoBrowserClient(headless=False)
browser.ensure_browser()

result = browser.generate_scene_multiview(
    prompt=multi_prompt,
    scene_name=scene["name"],
)
if result.success and result.file_paths:
    img_path = result.file_paths[0]
    db.conn.execute(
        "UPDATE scene_card SET multi_view_image=?, status='done' WHERE id=6",
        (img_path,))
    db.conn.commit()
    print(f"Scene image saved: {img_path}")
else:
    print(f"Scene image failed: {result.error}")

db.close()
