"""Face grid overlay — bypasses Doubao's "real face detection" for character design sheets.

Applies a visible grid pattern using cool gray-blue lines at ~43% opacity with
8px spacing. Lines are individually visible against warm skin tones, creating
enough visual disruption to interfere with face detection while preserving
reference quality for video generation.

Strategy: character design sheets place faces in the upper portions of the
image (main character at left 45% top, three-views at right 45%). We apply a
grid to the upper 90%, leaving the bottom equipment/artifact strip untouched.

Key parameters (tuned from real-world testing):
- 8px spacing: ~48 lines on a 384px image — each line clearly visible
- 43% opacity (110/255): visible without destroying reference detail
- Cool gray-blue (180,190,210): contrast against warm skin tones
- No diagonals: per-cell cross-hatching at tighter spacing creates a solid
  gray wash instead of visible grid lines
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


def apply_face_grid(
    image_path: str,
    output_dir: Path | None = None,
    grid_spacing: int = 8,
    grid_opacity: int = 110,
) -> str:
    """Overlay a visible grid on the face region of a character design sheet.

    The grid is applied to the upper 90% of the image where all faces are
    located in the standard game-card design sheet layout. The lower 10%
    (equipment/artifact section) is left untouched since it contains no faces.

    Uses cool gray-blue lines at ~43% opacity with 8px spacing. Each line is
    individually visible against warm skin tones — the spacing is wide enough
    that the grid pattern is distinct, not a solid gray wash.

    Args:
        image_path: Path to the original character design sheet (PNG/JPG).
        output_dir: Directory for the modified temp image. Default: data/temp/.
        grid_spacing: Pixel spacing between grid lines. Default 8px.
        grid_opacity: Alpha value for grid lines (0-255). Default 110 (~43%).

    Returns:
        Path to the modified temp image (PNG). Original file is NEVER modified.
    """
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size

    # ── Cover upper 90% — multi-character four-view sheets have faces
    #     distributed across the top 80%+. ──
    face_region_bottom = int(h * 0.90)

    # Create overlay with grid lines
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Cool gray-blue grid — visible contrast against warm skin tones.
    # Wide enough spacing (8px) so each line is distinct, not a solid wash.
    grid_color = (180, 190, 210, grid_opacity)

    # Horizontal grid lines (face region only)
    for y in range(0, face_region_bottom, grid_spacing):
        draw.line([(0, y), (w, y)], fill=grid_color, width=1)

    # Vertical grid lines (face region only)
    for x in range(0, w, grid_spacing):
        draw.line([(x, 0), (x, face_region_bottom)], fill=grid_color, width=1)

    # Composite
    result = Image.alpha_composite(img, overlay)

    # ── Save temp file, preserve original ──
    import uuid
    out_dir = output_dir or Path("data/temp")
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_path = str(out_dir / f"face_grid_{uuid.uuid4().hex[:8]}.png")
    result.convert("RGB").save(temp_path, "PNG")

    return temp_path
