"""Turn any supported design file into the two PNGs the pipeline needs.

Supported: PNG, JPG/JPEG, WEBP, BMP, TIFF, GIF, HEIC (required: PNG + JPG)
Bonus:     PSD (psd-tools), PDF / AI (pypdfium2 — .ai files are PDF-compatible)
"""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

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
    """Decode any supported format, orientation-corrected, **alpha intact**.

    Flattening is deliberately not done here: the vision render needs a
    high-contrast backing so the model can see light artwork, while the preview
    the user looks at must stay faithful to the file they supplied. One function
    cannot serve both, so each caller composites for itself.
    """
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

    return ImageOps.exif_transpose(img)


#: Alpha above which a pixel counts as real artwork rather than a soft edge.
_OPAQUE = 32
#: Luminance distance below which artwork stops reading against the background.
_MIN_CONTRAST = 28
#: Flat tones we may composite onto, light to dark. Must keep both 255 and 26 —
#: they are what the old threshold rule could pick, which is what makes the
#: choice below unable to hide more artwork than that rule did.
_BG_CANDIDATES = (255, 190, 128, 64, 26)
#: The background is one global decision, so make it on a small copy: morphology
#: on a 20 MP image costs seconds and buys no accuracy.
_DECIDE_MAX_EDGE = 900


def flatten(img: Image.Image) -> Image.Image:
    """Composite transparency onto a background the artwork stays visible against.

    Print-on-demand art is supplied transparent so it can go on any garment, and
    a large share of it is white or near-white for dark shirts. Compositing that
    onto white erases the design — the model then sees nothing there and reports
    SAFE, which is the worst failure this tool can have.
    """
    if not (img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)):
        return img.convert("RGB")

    img = img.convert("RGBA")
    level = _pick_background(img)
    bg = Image.new("RGBA", img.size, (level, level, level, 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _pick_background(img: Image.Image) -> int:
    """Choose the flat tone that hides the least artwork. Returns a grey level.

    Only artwork *bordering transparency* competes with the background. A
    mid-grey region inside a photograph is framed by other tones and reads fine
    whatever sits behind it; a white wordmark floating on transparency does not.
    So the decision is made on the silhouette region alone.

    Deciding on the whole image instead — which is what a percentile over all
    opaque pixels does — reads the interior and erases the border: a design with
    a dark illustration and a white logo has its 5th percentile dragged down by
    the illustration, picks white, and loses the logo. That is a real miss, not
    a hypothetical: an adidas design came back SAFE with zero findings because
    the three-stripe mark and wordmark were white-on-white by the time the model
    saw them.
    """
    small = _downscale(img, _DECIDE_MAX_EDGE)
    alpha = small.getchannel("A")
    opaque = alpha.point(lambda a: 255 if a > _OPAQUE else 0)
    transparent = alpha.point(lambda a: 255 if a <= _OPAQUE else 0)
    # Grow the transparent region so its border overlaps the artwork beside it.
    bordering = ImageChops.multiply(
        opaque, transparent.filter(ImageFilter.MaxFilter(11))
    )

    histogram = small.convert("L").histogram(bordering)
    if not sum(histogram):
        # Nothing borders transparency (fully opaque, or fully transparent):
        # the background cannot hide anything, so any tone will do.
        return _BG_CANDIDATES[0]

    def hidden(level: int) -> int:
        lo = max(0, level - _MIN_CONTRAST)
        hi = min(256, level + _MIN_CONTRAST + 1)
        return sum(histogram[lo:hi])

    return min(_BG_CANDIDATES, key=hidden)


def _downscale(img: Image.Image, max_edge: int) -> Image.Image:
    """Shrink so the long edge fits `max_edge`. Never upscales — enlarging adds
    cost and no detail, and a 310px sheet export blown up to 1200 just wastes
    tokens."""
    long_edge = max(img.size)
    if long_edge <= max_edge:
        return img
    ratio = max_edge / long_edge
    return img.resize((round(img.width * ratio), round(img.height * ratio)), Image.LANCZOS)


def prepare(path: Path) -> tuple[Path, Path, int, int]:
    """Normalise `path` into two PNGs under renders/.

    Returns `(render_path, preview_path, original_w, original_h)`:

    - **render** — sized for the vision model (`RENDER_MAX_EDGE`). Analysis
      deletes it when it is done; nothing may reference it in a stored report.
    - **preview** — the small derivative the UI serves (`PREVIEW_MAX_EDGE`), and
      the canvas the annotated overlay is drawn on. Kept.

    The width/height returned are the *original* file's, which is what the report
    states — neither derivative's size.
    """
    img = load_image(path)
    width, height = img.size

    # The model's copy: composited onto whichever flat tone hides the least
    # artwork, because a light logo on white is invisible to it.
    render = _downscale(flatten(img), settings.render_max_edge)
    render_path = settings.renders_dir / f"{uuid.uuid4().hex}.png"
    render.save(render_path, format="PNG", optimize=True)

    # The user's copy: transparency preserved, so the dashboard shows the design
    # as supplied rather than the grey backing the model needed. Compositing here
    # too would show every seller a background that is not in their file.
    preview = _downscale(img, settings.preview_max_edge)
    preview_path = settings.renders_dir / f"prev_{uuid.uuid4().hex}.png"
    preview.save(preview_path, format="PNG", optimize=True)

    return render_path, preview_path, width, height
