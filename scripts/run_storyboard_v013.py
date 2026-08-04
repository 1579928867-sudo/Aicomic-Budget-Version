"""Re-run StoryboardAgent (ScreenwriterAgent) for chapter 1 to generate v0.13 segments_json.

Resets storyboard-agent status, deletes old shots, regenerates via DeepSeek LLM.
"""
import os, sys, json
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from aicomic.db.repository import Database
from aicomic.agents.screenwriter import ScreenwriterAgent
from aicomic.llm.deepseek import DeepSeekClient

db = Database(project_root / "data" / "aicomic.db")
db.connect()
db.migrate_schema()

CHAPTER_ID = 1
SCRIPT_ID = 1

# ── Check script exists ──
script_row = db.conn.execute(
    "SELECT id, raw_json FROM script WHERE id = ?", (SCRIPT_ID,)
).fetchone()
if not script_row:
    print(f"ERROR: script {SCRIPT_ID} not found!")
    db.close()
    sys.exit(1)

script_json = json.loads(script_row["raw_json"])
scenes = script_json.get("scenes", [])
total_beats = sum(len(s.get("beats", [])) for s in scenes)
print(f"Script {SCRIPT_ID}: {len(scenes)} scenes, {total_beats} total beats")

# ── Reset agent status so it re-runs ──
# Status is stored in task_log with event='status'
db.conn.execute(
    "DELETE FROM task_log WHERE agent_name = 'storyboard-agent' AND chapter_id = ?",
    (CHAPTER_ID,),
)
# Delete old shots + their outfit mappings
old_count = db.conn.execute(
    "SELECT COUNT(*) FROM storyboard_shot WHERE script_id = ?", (SCRIPT_ID,)
).fetchone()[0]
db.conn.execute(
    "DELETE FROM shot_character_outfit WHERE shot_id IN (SELECT id FROM storyboard_shot WHERE script_id = ?)",
    (SCRIPT_ID,),
)
db.conn.execute("DELETE FROM storyboard_shot WHERE script_id = ?", (SCRIPT_ID,))
# Also reset downstream agents
for name in ["shot-visualizer", "shot-video-generator"]:
    db.conn.execute(
        "DELETE FROM task_log WHERE agent_name = ? AND chapter_id = ?",
        (name, CHAPTER_ID),
    )
db.conn.commit()
print(f"Reset: deleted {old_count} old shots + agent task_log entries")

# ── Create LLM client ──
api_key = os.environ.get("DEEPSEEK_API_KEY")
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY not set!")
    db.close()
    sys.exit(1)

llm = DeepSeekClient(api_key=api_key)
print(f"LLM: DeepSeek (model={llm.model})")

# ── Run agent ──
agent = ScreenwriterAgent(llm_client=llm)
print("\nGenerating v0.13 storyboard with time-segmented format...")
print("(Each shot → 3 segments [0-3s][3-7s][7-10s] with camera/action/dialogue/sound/transition)")

result = agent.execute({"chapter_id": CHAPTER_ID, "script_id": SCRIPT_ID}, db)

if result.success:
    # ── Verify output ──
    shots = db.get_storyboard_shots(SCRIPT_ID)
    print(f"\n[OK] StoryboardAgent completed: {len(shots)} shots")

    for s in shots:
        sd = dict(s)
        seg_raw = sd.get("segments_json", "[]")
        try:
            segments = json.loads(seg_raw) if isinstance(seg_raw, str) else seg_raw
        except (json.JSONDecodeError, TypeError):
            segments = []

        n_segs = len(segments)
        has_narration = bool(sd.get("narration"))
        has_dialogue = bool(sd.get("dialogue"))
        print(f"  Shot {sd['shot_num']:>2}: camera={sd.get('camera_movement','?'):4s}  "
              f"segments={n_segs}  narration={has_narration}  dialogue={has_dialogue}")

        # Print first segment preview
        if segments:
            s0 = segments[0]
            print(f"         [0] {s0.get('time_range','?'):6s} | {s0.get('camera','?'):10s} | "
                  f"{(s0.get('action','') or '')[:60]}...")
    # Show full segments_json for Shot 1
    shot1 = shots[0] if shots else None
    if shot1:
        print(f"\n=== Shot 1 segments_json ===")
        segs = json.loads(shot1["segments_json"]) if isinstance(shot1["segments_json"], str) else shot1["segments_json"]
        print(json.dumps(segs, ensure_ascii=False, indent=2))
else:
    print(f"\n[FAIL] {result.error}")

db.close()
