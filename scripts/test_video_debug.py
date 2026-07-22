"""Quick video generation test — uses existing images to debug _find_video_urls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aicomic.doubao.browser import DoubaoBrowserClient

# Use existing images
img_dir = Path("data/images")
images = sorted(img_dir.glob("doubao_*.jpg"))
print(f"Reference images: {[p.name for p in images]}")

# Short, simple prompt to test video detection
prompt = (
    "这是我用AI生成的图片，我有版权，请帮我根据提示词生成视频。"
    "生成视频，5s，"
    "一个年轻男子在古风婚房中醒来，缓缓睁开眼睛看向四周。"
    "镜头缓慢推进，画面由远及近。"
    "高质量AI视频，流畅运镜，电影级画面。"
    "原比例。"
)

client = DoubaoBrowserClient(
    headless=False,
    output_dir="data/",
    timeout_sec=300,
)

try:
    result = client.generate_video_from_images(
        prompt=prompt,
        reference_images=[str(p) for p in images[:2]],  # Just 2 ref images
        duration_sec=5.0,
    )
    print(f"\nResult: success={result.success}")
    if result.success:
        print(f"Video paths: {result.file_paths}")
    else:
        print(f"Error: {result.error}")
        # Check debug files
        debug_dir = Path("data/debug")
        for f in sorted(debug_dir.glob("doubao_video_timeout_*")):
            print(f"  Debug: {f.name} ({f.stat().st_size} bytes)")
finally:
    client.close()
