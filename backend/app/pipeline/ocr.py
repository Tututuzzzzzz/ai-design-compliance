"""Local OCR with bounding boxes.

RapidOCR (ONNX, ~80 MB, offline) when installed; otherwise we return nothing and
let the vision model's own OCR carry the text extraction. Both paths produce the
same `OCRLine` shape, so downstream code doesn't care which ran.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from ..models import BBox, OCRLine

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415

        return RapidOCR()
    except Exception as exc:  # pragma: no cover - optional dependency
        log.info("Local OCR unavailable (%s); falling back to vision-model OCR.", exc)
        return None


def available() -> bool:
    return _engine() is not None


def extract(image_path: Path, width: int, height: int) -> list[OCRLine]:
    engine = _engine()
    if engine is None:
        return []

    try:
        result, _ = engine(str(image_path))
    except Exception as exc:  # pragma: no cover
        log.warning("OCR failed on %s: %s", image_path.name, exc)
        return []

    if not result:
        return []

    lines: list[OCRLine] = []
    for box, text, score in result:
        text = (text or "").strip()
        if not text:
            continue
        lines.append(
            OCRLine(text=text, bbox=_to_bbox(box, width, height), confidence=float(score or 0.0))
        )
    return lines


def _to_bbox(quad, width: int, height: int) -> BBox | None:
    """RapidOCR returns a 4-point polygon in pixels; convert to a normalised rect."""
    if not quad or width <= 0 or height <= 0:
        return None
    try:
        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
    except (TypeError, IndexError, ValueError):
        return None

    x0, x1 = max(0.0, min(xs)), min(float(width), max(xs))
    y0, y1 = max(0.0, min(ys)), min(float(height), max(ys))
    if x1 <= x0 or y1 <= y0:
        return None

    return BBox(x=x0 / width, y=y0 / height, w=(x1 - x0) / width, h=(y1 - y0) / height)
