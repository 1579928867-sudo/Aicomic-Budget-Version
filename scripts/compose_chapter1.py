"""Quick compose — stitch chapter 1 clips into final video."""
import os
import sys
import hashlib
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from aicomic.db.repository import Database
from moviepy import VideoFileClip, concatenate_videoclips
from moviepy.video.fx import FadeIn, FadeOut

db = Database(project_root / "data" / "aicomic.db")
db.connect()

# Load clips in shot order
shots = db.get_storyboard_shots(1)
clip_paths = []
for s in shots:
    s = dict(s)
    clip = db.conn.execute(
        "SELECT file_path FROM video_clip WHERE shot_id = ?", (s["id"],)
    ).fetchone()
    if clip:
        p = Path(clip["file_path"])
        if p.exists():
            clip_paths.append(str(p))
            print(f"Shot {s['shot_num']:2d}: {p.name}")
        else:
            print(f"Shot {s['shot_num']:2d}: MISSING {clip['file_path']}")
    else:
        print(f"Shot {s['shot_num']:2d}: NO CLIP")

print(f"\nLoading {len(clip_paths)} clips...")

video_clips = []
for fp in clip_paths:
    vc = VideoFileClip(fp)
    print(f"  {Path(fp).name}: {vc.duration:.1f}s {vc.w}x{vc.h}")
    video_clips.append(vc)

# Apply fade in/out
processed = []
for clip in video_clips:
    clip = clip.with_effects([FadeIn(0.3), FadeOut(0.3)])
    processed.append(clip)

print(f"\nComposing with fade transitions...")
final = concatenate_videoclips(processed)

output_path = str(project_root / "data" / "videos" / "final_1.mp4")
# Remove any stale empty file first
Path(output_path).unlink(missing_ok=True)

final.write_videofile(
    output_path,
    codec="libx264",
    audio_codec="aac",
    fps=24,
    logger=None,
)

# ── Verify immediately BEFORE closing anything ──
output_file = Path(output_path)
if not output_file.exists() or output_file.stat().st_size == 0:
    raise RuntimeError(f"Output file is empty or missing after write_videofile: {output_path}")

# Force OS-level flush
with open(output_path, 'rb') as vf:
    _ = vf.read(4096)  # trigger OS cache read
size_mb = output_file.stat().st_size / (1024 * 1024)
md5 = hashlib.md5(output_file.read_bytes()).hexdigest()

# ── Now safe to close source clips ──
for c in video_clips:
    try:
        c.close()
    except Exception:
        pass
try:
    final.close()
except Exception:
    pass

# ── Verify file survived close ──
size_after = output_file.stat().st_size / (1024 * 1024)
if size_after == 0:
    raise RuntimeError(f"Output file was truncated after close(): {output_path}")

total_dur = sum(c.duration for c in video_clips)
print(f"\nDone! {output_path}")
print(f"  Duration: {total_dur:.1f}s, Size: {size_mb:.1f}MB, MD5: {md5[:16]}, Clips: {len(video_clips)}")

# Save to final_video table (create if needed)
db.conn.execute("""
    CREATE TABLE IF NOT EXISTS final_video (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter_id INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
db.conn.execute(
    "INSERT INTO final_video (chapter_id, file_path) VALUES (?, ?)",
    (1, output_path),
)
db.conn.commit()
print("  Saved to DB.")

db.close()
