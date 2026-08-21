"""Turn any supported design file into a flat RGB PNG the vision model can read.

Supported: PNG, JPG/JPEG, WEBP, BMP, TIFF, GIF, HEIC (required: PNG + JPG)
Bonus:     PSD (psd-tools), PDF / AI (pypdfium2 — .ai files are PDF-compatible)
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageOps

from ..config import settings

log = logging.getLogger(__name__)

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


def load_image(path: Path) -> tuple[Image.Image, tuple[int, int]]:
    """Returns (autocropped image with transparency intact, size as supplied).

    Deliberately does NOT flatten. `prepare` needs the alpha channel twice: once
    to composite the analysis render onto an ink-preserving background, and once
    to write a display render that still looks like the file that was uploaded.
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

    # exif_transpose copies the whole image, so only pay for it when there is an
    # orientation to correct. POD exports normally carry no EXIF at all.
    if (img.getexif().get(0x0112) or 1) != 1:
        img = ImageOps.exif_transpose(img)
    # Report the size as supplied, before autocrop trims the empty canvas — that
    # is what "how big is this design" means to whoever uploaded it.
    source_size = img.size
    img = _autocrop(img)
    # Normalise the mode here so `prepare` can tell "this had transparency" from
    # "this did not" with one check — _autocrop may hand back the original P-mode
    # or LA image untouched when it declines to crop.
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    return img.convert("RGBA" if has_alpha else "RGB"), source_size


#: Alpha above which a pixel counts as real artwork rather than a soft edge.
_OPAQUE = 32
#: Padding kept around the cropped artwork, as a share of its longest side.
_CROP_MARGIN = 0.03
#: Below this share of the frame, the artwork is small enough that cropping wins.
_CROP_WHEN_SMALLER_THAN = 0.7
#: Never crop away so much that what is left is tiny — that means the alpha
#: channel is not describing artwork the way we assume.
_CROP_MIN_SIDE_PX = 64
#: Luminance at or above this is white-ink artwork that a white background erases.
_NEAR_WHITE = 200
#: Luminance at or below this is dark artwork that a dark background erases.
_NEAR_DARK = 60
#: Share of the artwork a luminance band needs before erasing it loses real
#: content. This is a presence test, not a dominance test, and the difference is
#: the whole bug it replaces: at 0.15 a design had to be *mostly* white ink before
#: the white was protected. Measured over the 488-design sample, every design
#: whose white text the old gate destroyed carried between 2.6% and 14.5% white
#: ink — not one reached 0.15. Thirty-two of them lost brand names outright
#: (ADIDAS, LEVIS, METALLICA, KANYE WEST, THE BLACK CROWES) and four lost every
#: readable line, because a trademark is 100% of the compliance signal at any
#: pixel share.
_PRESENT_SHARE = 0.02
_DARK_BG = (26, 26, 26)
_LIGHT_BG = (255, 255, 255)
#: Neutral fallback for artwork that has substantial white AND dark ink — either
#: extreme would erase half of it, so sit between them.
_MID_BG = (128, 128, 128)


def _flatten(img: Image.Image) -> Image.Image:
    """Composite transparency onto a background the artwork stays visible against.

    This is the ANALYSIS render only. It is chosen to keep every ink band legible
    to the model and to OCR, not to look like the design — the display render
    keeps the original transparency for that.

    Print-on-demand art is supplied transparent so it can go on any garment, and a
    large share of it is white or near-white for dark shirts. Compositing that onto
    white erases the design completely — the model then sees a blank canvas and
    reports SAFE, which is the worst failure this tool can have. So pick the
    background from the artwork's own luminance instead of assuming one.
    """
    if not (img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)):
        return img.convert("RGB")

    img = img.convert("RGBA")
    bg = Image.new("RGBA", img.size, (*_background_for(img), 255))
    return Image.alpha_composite(bg, img).convert("RGB")


def _background_for(img: Image.Image) -> tuple[int, int, int]:
    """Choose a background that erases as little of the artwork as possible.

    The earlier test asked "is any of this dark enough to read on white?" using the
    5th percentile of luminance. That gets a white-ink logo with a small coloured
    accent badly wrong: a golf wordmark that was ~75% pure-white lettering plus a
    mint icon scored 177 at the 5th percentile, passed the "visible on white" test,
    and had its entire wordmark composited into invisibility. The model then saw a
    near-blank canvas and returned SAFE — a miss on a real trademark.

    So ask the opposite question: how much of the artwork would each background
    destroy? Measure the share sitting in the near-white and near-dark bands and
    pick the background that erases neither.
    """
    alpha = img.getchannel("A")
    mask = alpha.point(lambda a: 255 if a > _OPAQUE else 0)

    histogram = img.convert("L").histogram(mask)
    opaque = sum(histogram)
    if opaque == 0:
        return _LIGHT_BG  # fully transparent; nothing to lose either way

    near_white = sum(histogram[_NEAR_WHITE:]) / opaque
    near_dark = sum(histogram[: _NEAR_DARK + 1]) / opaque

    white_ink = near_white >= _PRESENT_SHARE
    dark_ink = near_dark >= _PRESENT_SHARE

    if white_ink and dark_ink:
        # Two-tone art (white outline + black fill is common). Neither extreme
        # works, so use mid grey and keep both readable.
        return _MID_BG
    if white_ink:
        return _DARK_BG
    return _LIGHT_BG


def _autocrop(img: Image.Image) -> Image.Image:
    """Trim transparent margin so the artwork fills the frame it is judged in.

    POD source files are print-sized canvases with the art sitting in one corner
    or floating in the middle — the golf logo that triggered this occupied 1.6% of
    a 4200x4800 file. Everything downstream then works against that 1.6%: the
    render is capped at RENDER_MAX_EDGE, so a small logo shrinks by the canvas
    ratio rather than its own, and thin lettering can dissolve before the model or
    OCR ever sees it.

    Cropping is deliberately conservative. It only runs on genuinely transparent
    input, only when the art is meaningfully smaller than its canvas, and it
    refuses to produce a tiny result — an alpha channel that does not describe
    artwork the way we assume should leave the image untouched, not shredded.
    """
    if not settings.autocrop_transparent:
        return img
    if not (img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)):
        return img

    rgba = img.convert("RGBA")
    mask = rgba.getchannel("A").point(lambda a: 255 if a > _OPAQUE else 0)
    box = mask.getbbox()
    if not box:
        return img  # nothing opaque at all; leave it for _flatten to handle

    left, top, right, bottom = box
    art_w, art_h = right - left, bottom - top
    frame_w, frame_h = rgba.size

    # Already fills the frame — cropping would only shave the soft edge.
    if art_w > frame_w * _CROP_WHEN_SMALLER_THAN and art_h > frame_h * _CROP_WHEN_SMALLER_THAN:
        return img

    margin = round(max(art_w, art_h) * _CROP_MARGIN)
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(frame_w, right + margin)
    bottom = min(frame_h, bottom + margin)

    if (right - left) < _CROP_MIN_SIDE_PX or (bottom - top) < _CROP_MIN_SIDE_PX:
        return img

    log.debug(
        "autocrop %sx%s -> %sx%s (artwork was %.1f%% of frame)",
        frame_w, frame_h, right - left, bottom - top,
        art_w * art_h / (frame_w * frame_h) * 100,
    )
    return rgba.crop((left, top, right, bottom))


class Render(NamedTuple):
    """A prepared render plus both coordinate spaces it can be measured in.

    `width`/`height` describe the design as supplied — what a person means by
    "how big is this file". `render_width`/`render_height` describe the PNG that
    actually reached the model, after autocrop and the RENDER_MAX_EDGE cap.

    Anything converting pixels found *in the render* into normalised coordinates
    must divide by the render size. Using the source size instead silently scales
    every box by the crop-and-resize ratio.
    """

    #: Flattened onto an ink-preserving background — what the model and OCR read.
    path: Path
    #: Transparency intact — what the UI shows. Equal to `path` when the source
    #: had no alpha channel, because then nothing was composited either way.
    display_path: Path
    width: int
    height: int
    render_width: int
    render_height: int


def _downscale(img: Image.Image, max_edge: int) -> Image.Image:
    """Shrink to fit `max_edge`, cheaply.

    A print canvas is typically 3x larger than the render, and LANCZOS over that
    whole area is one of the pipeline's bigger costs. An integer box-reduce first
    does most of the work for a fraction of the time — measured 370 ms against
    590 ms for a straight LANCZOS on 4500x5100, with a mean per-pixel difference
    of 0.7/255. (Pillow's own `reducing_gap` was tried and is *slower* here.)
    Bilinear would be marginally faster still, but it aliases thin lettering,
    which is exactly the content this pipeline cannot afford to lose.
    """
    long_edge = max(img.size)
    if long_edge <= max_edge:
        return img
    ratio = max_edge / long_edge
    target = (round(img.width * ratio), round(img.height * ratio))
    step = max(1, min(img.width // target[0], img.height // target[1]))
    if step > 1:
        img = img.reduce(step)
    return img.resize(target, Image.LANCZOS)


def prepare(path: Path) -> Render:
    """Write the two renders the pipeline needs, under renders/.

    They are separate on purpose. The analysis render is flattened onto whatever
    background keeps the ink readable, so white-on-transparent artwork lands on
    dark and the trademark in it actually reaches the model. The display render
    keeps the file's own transparency, because the preview has to show the design
    as supplied — pasting the analysis background into the UI would show the
    operator a picture they never uploaded.

    One autocrop and one resize feed both, so a box measured in the analysis
    render lands in the same place on the display render.
    """
    img, (width, height) = load_image(path)

    img = _downscale(img, settings.render_max_edge)

    stem = uuid.uuid4().hex
    analysis_path = settings.renders_dir / f"{stem}.png"
    # Fastest compression on purpose. optimize=True cost 1143 ms here and the
    # default level 665 ms, to save ~200 KB on a file that is uploaded once to a
    # request that already takes ~14 s. Encoder time is real; those bytes are not.
    _flatten(img).save(analysis_path, format="PNG", compress_level=1)

    if img.mode == "RGBA":
        display_path = settings.renders_dir / f"view_{stem}.png"
        # Served over localhost only, so trade size for speed outright:
        # optimize=True took 2155 ms here against 116 ms at compress_level=1.
        img.save(display_path, format="PNG", compress_level=1)
    else:
        display_path = analysis_path  # opaque source: nothing was composited

    return Render(analysis_path, display_path, width, height, img.width, img.height)
