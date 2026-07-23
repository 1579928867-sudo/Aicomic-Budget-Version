"""v0.13: Generate new video-native script and storyboard for review."""
import json
import os
import sys
from pathlib import Path

# Fix GBK encoding on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Project root
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from aicomic.db.repository import Database
from aicomic.agents.scriptwriter import ScriptwriterAgent
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.llm.deepseek import DeepSeekClient

# ── Setup ──
key = os.environ.get("DEEPSEEK_API_KEY", "")
if not key:
    print("ERROR: DEEPSEEK_API_KEY not set")
    sys.exit(1)

llm = DeepSeekClient(api_key=key, model="deepseek-chat")

db = Database(project_root / "data" / "aicomic.db")
db.connect()
db.migrate_schema()  # Ensure v0.13 columns exist

# Clear previous scriptwriter/storyboard results so idempotency check passes
db.conn.execute(
    "DELETE FROM task_log WHERE agent_name IN ('scriptwriter', 'storyboard-agent')"
    " AND event = 'status'"
)
# FK-safe deletion order
db.conn.execute("DELETE FROM shot_character_outfit")
db.conn.execute("DELETE FROM video_clip")
db.conn.execute("DELETE FROM final_video")
db.conn.execute("DELETE FROM storyboard_shot")
db.conn.execute("DELETE FROM script")
db.conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('script', 'storyboard_shot', 'video_clip', 'final_video')")
db.conn.commit()

# ── Load chapter ──
ch = db.conn.execute("SELECT id, raw_text FROM chapter WHERE id = 1").fetchone()
if not ch:
    print("ERROR: No chapter found")
    sys.exit(1)
chapter_id = ch["id"]
raw_text = ch["raw_text"]

print(f"Chapter {chapter_id}: {len(raw_text)} chars")
print()

# ── Step 1: Scriptwriter ──
print("=" * 60)
print("STEP 1: Scriptwriter (video-native beats)")
print("=" * 60)

agent_script = ScriptwriterAgent(llm_client=llm)
result = agent_script.execute({"chapter_id": chapter_id, "raw_text": raw_text}, db)

if not result.success:
    print(f"ERROR: Scriptwriter failed: {result.error}")
    sys.exit(1)

print(f"Result data keys: {list(result.data.keys()) if result.data else 'None'}")
print(f"Result data: {result.data}")
script_id = result.data.get("script_id")
if not script_id:
    print("ERROR: No script_id in result")
    sys.exit(1)
print(f"✓ Script #{script_id} created")
print(f"  Characters: {result.data['characters']}")
print(f"  Scenes: {result.data['scenes_list']}")
print(f"  Beats: {result.data['beat_count']}")

# ── Save script to file ──
script_row = db.conn.execute(
    "SELECT raw_json FROM script WHERE id = ?", (script_id,)
).fetchone()
script_json = json.loads(script_row["raw_json"])

out_dir = project_root / "data" / "debug"
out_dir.mkdir(parents=True, exist_ok=True)
with open(out_dir / "v013_script.json", "w", encoding="utf-8") as f:
    json.dump(script_json, f, ensure_ascii=False, indent=2)

# ── Human-readable script summary ──
lines = ["# AI漫剧 v0.13 剧本 (视频原生 Beat)", ""]
lines.append(f"## 基础信息")
lines.append(f"- 时代背景: {script_json.get('era_background', '?')}")
lines.append(f"- 角色: {script_json.get('characters', [])}")
lines.append(f"- 场景: {script_json.get('scenes_list', [])}")
lines.append("")

for scene in script_json.get("scenes", []):
    sn = scene.get("scene_name", "?")
    si = scene.get("scene_index", "?")
    atm = scene.get("atmosphere", "?")
    cues = scene.get("scene_sound_cues", [])
    lines.append(f"## 场景 #{si}: {sn}")
    lines.append(f"- 氛围: {atm}")
    lines.append(f"- 环境音: {cues}")
    lines.append("")
    for b in scene.get("beats", []):
        bn = b.get("beat_num", "?")
        action = b.get("action", "")
        vfx = b.get("visual_fx")
        sound = b.get("sound_cue", "")
        lines.append(f"### Beat {bn} (约8-10s)")
        lines.append(f"**画面**: {action}")
        if vfx:
            lines.append(f"**视觉特效**: {vfx}")
        lines.append(f"**音效**: {sound}")
        if b.get("expressions"):
            for char, expr in b["expressions"].items():
                lines.append(f"- 🎭 {char}: {expr}")
        if b.get("dialogue"):
            for d in b["dialogue"]:
                lines.append(f"- 💬 {d.get('speaker','?')}（{d.get('emotion','')}）: {d.get('line','')}")
        lines.append("")

script_text = "\n".join(lines)
with open(out_dir / "v013_script.md", "w", encoding="utf-8") as f:
    f.write(script_text)

print(f"\n✓ Script saved to data/debug/v013_script.json and .md")
print()

# ── Step 2: Storyboard ──
print("=" * 60)
print("STEP 2: StoryboardAgent (1:1 beat→shot)")
print("=" * 60)

agent_storyboard = ScreenwriterAgent(llm_client=llm)
result2 = agent_storyboard.execute(
    {"chapter_id": chapter_id, "script_id": script_id}, db
)

if not result2.success:
    print(f"ERROR: Storyboard failed: {result2.error}")
    sys.exit(1)

print(f"✓ Storyboard created: {result2.data['shots_created']} shots")
print()

# ── Save storyboard to file ──
shots = db.get_storyboard_shots(script_id)
sb_lines = ["# AI漫剧 v0.13 分镜", ""]
sb_lines.append(f"总镜头: {len(shots)}")
sb_lines.append("")

for s in shots:
    sd = dict(s)
    sn = sd.get("shot_num", "?")
    sb_lines.append(f"## Shot {sn}")
    sb_lines.append(f"- 镜头类型: {sd.get('shot_type', '?')}")
    sb_lines.append(f"- 运镜: {sd.get('camera_movement', '?')}")
    sb_lines.append(f"- 时长: {sd.get('duration_sec', 0)}s")
    sb_lines.append(f"- 场景: scene_id={sd.get('scene_id', '?')}")
    sb_lines.append(f"- 图像提示词: {str(sd.get('image_prompt', ''))[:80]}...")
    sb_lines.append("")
    prev = sd.get("prev_end_state", "")
    start = sd.get("start_state", "")
    vfx = sd.get("visual_fx", "")
    if prev:
        sb_lines.append(f"**上一镜结束**: {prev}")
    if start:
        sb_lines.append(f"**本镜起始**: {start}")
    if vfx:
        sb_lines.append(f"**视觉特效**: {vfx}")
    sb_lines.append("")
    sb_lines.append(f"**旁白**: {sd.get('narration', '')}")
    sb_lines.append(f"**对白**: {sd.get('dialogue', '')}")
    sb_lines.append("")

with open(out_dir / "v013_storyboard.md", "w", encoding="utf-8") as f:
    f.write("\n".join(sb_lines))

with open(out_dir / "v013_storyboard.json", "w", encoding="utf-8") as f:
    json.dump([dict(s) for s in shots], f, ensure_ascii=False, indent=2, default=str)

print(f"✓ Storyboard saved to data/debug/v013_storyboard.json and .md")

db.close()
print("\nDone! Review the files:")
print(f"  {out_dir / 'v013_script.md'}")
print(f"  {out_dir / 'v013_storyboard.md'}")
