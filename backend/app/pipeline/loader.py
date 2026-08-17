"""Turn any supported design file into a flat RGB PNG the vision model can read.

Supported: PNG, JPG/JPEG, WEBP, BMP, TIFF, GIF, HEIC (required: PNG + JPG)
Bonus:     PSD (psd-tools), PDF / AI (pypdfium2 — .ai files are PDF-compatible)
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, ImageOps

from ..config import settings

Image.MAX_IMAGE_PIXELS = 400_000_000

RASTER_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
PSD_EXT = {".psd", ".psb"}
VECTOR_EXT = {".pdf", ".ai", ".eps"}
SUPPORTED_EXT = RASTER_EXT | PSD_EXT | VECTOR_EXT | {".heic", ".heif"}


class UnsupportedFormat(RuntimeError):
    pass


def _register_heif() -> None:
    try:
        import pillow_heif  # noqa: PLC0415

        pillow_heif.register_heif_opener()
    except Exception:  # pragma: no cover - optional dependency
        pass


_register_heif()


def _open_psd(path: Path) -> Image.Image:
    from psd_tools import PSDImage  # noqa: PLC0415

    psd = PSDImage.open(path)
    img = psd.composite()
    if img is None:
        raise UnsupportedFormat(f"PSD has no composite layer: {path.name}")
    return img


def _open_vector(path: Path) -> Image.Image:
    import pypdfium2 as pdfium  # noqa: PLC0415

    doc = pdfium.PdfDocument(str(path))
    try:
        if len(doc) == 0:
            raise UnsupportedFormat(f"Empty document: {path.name}")
        page = doc[0]
        # scale=3 ≈ 216 DPI, enough for small print text to survive OCR.
        return page.render(scale=3).to_pil()
    finally:
        doc.close()


def load_image(path: Path) -> Image.Image:
    ext = path.suffix.lower()
    if ext in PSD_EXT:
        img = _open_psd(path)
    elif ext in VECTOR_EXT:
        img = _open_vector(path)
    elif ext in RASTER_EXT or ext in {".heic", ".heif"}:
        img = Image.open(path)
    else:
        # Last resort: let Pillow sniff the content (handles wrong extensions).
        try:
            img = Image.open(path)
        except Exception as exc:  # pragma: no cover
            raise UnsupportedFormat(f"Unsupported design format '{ext}'") from exc

    img = ImageOps.exif_transpose(img)
    return _flatten(img)


#: Alpha above which a pixel counts as real artwork rather than a soft edge.
_OPAQUE = 32
#: If the darkest 5% of the artwork is still this light, white would erase it.
_TOO_LIGHT = 200
_DARK_BG = (26, 26, 26)
_LIGHT_BG = (255, 255, 255)


def _flatten(img: Image.Image) -> Image.Image:
    """Composite transparency onto a background the artwork stays visible against.

    Print-on-demand art is supplied transparent so it can go on any garment, and a
    large share of it is white or near-white for dark shirts. Compositing that onto
    white erases the design completely — the model then sees a blank canvas and
    reports SAFE, which is the worst failure this tool can have. So pick the
    background from the artwork's own luminance instead of assuming one.
    """
    if not (img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)):
        return img.convert("RGB")

    img = img.convert("RGBA")
    background = _LIGHT_BG if _visible_on_white(img) else _DARK_BG
    bg = Image.new("RGBA", img.size, (*background, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _visible_on_white(img: Image.Image) -> bool:
    """True when the opaque artwork has enough dark content to read on white."""
    alpha = img.getchannel("A")
    mask = alpha.point(lambda a: 255 if a > _OPAQUE else 0)

    histogram = img.convert("L").histogram(mask)
    opaque = sum(histogram)
    if opaque == 0:
        return True  # fully transparent; nothing to lose either way

    # 5th percentile of luminance over the artwork itself.
    cutoff = opaque * 0.05
    running = 0
    for level, count in enumerate(histogram):
        running += count
        if running >= cutoff:
            return level < _TOO_LIGHT
    return True


def prepare(path: Path) -> tuple[Path, int, int]:
    """Normalise `path` into a PNG under renders/. Returns (render_path, w, h)."""
    img = load_image(path)
    width, height = img.size

    long_edge = max(img.size)
    if long_edge > settings.render_max_edge:
        ratio = settings.render_max_edge / long_edge
        img = img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)

    out = settings.renders_dir / f"{uuid.uuid4().hex}.png"
    img.save(out, format="PNG", optimize=True)
    return out, width, height
