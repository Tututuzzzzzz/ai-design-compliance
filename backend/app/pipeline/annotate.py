"""Draw the violation boxes onto a copy of the design."""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import settings
from ..models import Finding, Severity

COLORS = {
    Severity.CRITICAL: (220, 38, 38),
    Severity.HIGH: (234, 88, 12),
    Severity.MEDIUM: (202, 138, 4),
    Severity.LOW: (37, 99, 235),
}


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(render_path: Path, findings: list[Finding]) -> Path | None:
    """Draw the boxes on `render_path`, keeping its transparency.

    It is handed the DISPLAY render, so it must not flatten: the annotated view is
    still a preview of the uploaded design, and converting straight to RGB would
    silently paint transparent areas whatever the file happens to store in its
    unused colour channels.
    """
    boxed = [f for f in findings if f.bbox is not None]
    if not boxed:
        return None

    img = Image.open(render_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    w, h = img.size
    stroke = max(2, round(min(w, h) * 0.005))
    font = _font(max(13, round(min(w, h) * 0.028)))

    for i, f in enumerate(boxed, start=1):
        color = COLORS[f.severity]
        x, y, bw, bh = f.bbox.to_pixels(w, h)
        x2, y2 = min(w, x + bw), min(h, y + bh)

        draw.rectangle([x, y, x2, y2], outline=(*color, 255), width=stroke)
        draw.rectangle([x, y, x2, y2], fill=(*color, 38))

        label = f"{i}. {f.severity.value.upper()}"
        tw = draw.textlength(label, font=font)
        th = font.size + 6
        ly = y - th if y - th >= 0 else y
        draw.rectangle([x, ly, x + tw + 10, ly + th], fill=(*color, 235))
        draw.text((x + 5, ly + 3), label, fill=(255, 255, 255), font=font)

    out = settings.renders_dir / f"annot_{uuid.uuid4().hex}.png"
    Image.alpha_composite(img, overlay).save(out, "PNG")
    return out
