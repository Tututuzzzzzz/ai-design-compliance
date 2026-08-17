"""Pydantic schemas — these double as the JSON contract for the vision model."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Verdict(str, Enum):
    SAFE = "SAFE"
    RISKY = "RISKY"
    BLOCKED = "BLOCKED"


class RiskCategory(str, Enum):
    """The seven risk families required by the brief."""

    COPYRIGHTED_CHARACTER = "copyrighted_character"
    BRAND_LOGO = "brand_logo"
    TRADEMARKED_PHRASE = "trademarked_phrase"
    PUBLIC_FIGURE = "public_figure"
    COPYRIGHTED_ARTWORK = "copyrighted_artwork"
    LICENSED_FONT = "licensed_font"
    PROHIBITED_CONTENT = "prohibited_content"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


class BBox(BaseModel):
    """Box with origin at top-left.

    The contract with the model is normalised 0..1, but models do not reliably
    honour it — Gemini natively emits a 0..1000 grid and some models return raw
    pixels. Constraints are therefore deliberately absent here: a mis-scaled box
    is repaired by `rescale()` during the pipeline rather than throwing away an
    otherwise-valid analysis of the whole design.
    """

    x: float
    y: float
    w: float
    h: float

    def rescale(self, render_w: int, render_h: int) -> "BBox | None":
        """Coerce to true 0..1 and clamp. Returns None if the box is unusable."""
        values = (self.x, self.y, self.w, self.h)
        if any(v != v for v in values):  # NaN
            return None

        peak = max(values)
        if peak <= 1.0:
            divx = divy = 1.0
        elif peak > max(render_w, render_h):
            # Larger than the image itself: a normalised grid, almost always 0..1000.
            divx = divy = 1000.0
        else:
            divx, divy = float(render_w or 1), float(render_h or 1)

        x, y = self.x / divx, self.y / divy
        w, h = self.w / divx, self.h / divy

        # Clamp into frame, keeping at least a sliver of area.
        x, y = min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)
        w, h = min(w, 1.0 - x), min(h, 1.0 - y)
        if w <= 0.001 or h <= 0.001:
            return None

        return BBox(x=x, y=y, w=w, h=h)

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            int(self.x * width),
            int(self.y * height),
            max(1, int(self.w * width)),
            max(1, int(self.h * height)),
        )


# --------------------------------------------------------------------------
# Niche
# --------------------------------------------------------------------------


class Niche(BaseModel):
    primary: str = Field(description="Main niche, e.g. 'Christmas', 'Dog Lovers', 'Nurse'")
    sub_niche: str | None = Field(
        default=None, description="Specific audience, e.g. 'Golden Retriever mom', 'ICU Nurse'"
    )
    audience: str | None = Field(default=None, description="Who would buy this")
    style: list[str] = Field(
        default_factory=list, description="e.g. vintage, minimalist, cartoon, retro 90s"
    )
    motifs: list[str] = Field(
        default_factory=list, description="Secondary motifs: skulls, flowers, guns, religious symbols"
    )
    confidence: float = Field(default=0.0, ge=0, le=1)


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


class Evidence(BaseModel):
    """Where a claim came from. Never fabricated — always a real source."""

    source: Literal[
        "vision_model",
        "ocr",
        "uspto_local_index",
        "uspto_live_api",
        "euipo_api",
        "policy_rule",
    ]
    detail: str
    url: str | None = None
    reference_id: str | None = Field(
        default=None, description="e.g. USPTO serial number / registration number"
    )


class Finding(BaseModel):
    category: RiskCategory
    title: str = Field(description="What was detected, e.g. 'Mickey Mouse silhouette'")
    description: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    rights_holder: str | None = None
    matched_text: str | None = Field(default=None, description="OCR text that triggered the match")
    bbox: BBox | None = None
    location_hint: str | None = Field(
        default=None, description="Human description of where, e.g. 'top-left chest print'"
    )
    evidence: list[Evidence] = Field(default_factory=list)
    remediation: str = Field(description="Concrete suggestion to make the design safe")


# --------------------------------------------------------------------------
# Vision model output contract
# --------------------------------------------------------------------------


class OCRLine(BaseModel):
    text: str
    bbox: BBox | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)


class VisionAnalysis(BaseModel):
    """Exactly what we ask the vision LLM to return."""

    description: str
    niche: Niche
    ocr_lines: list[OCRLine] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    notes: str | None = None


# --------------------------------------------------------------------------
# Final report
# --------------------------------------------------------------------------


class DesignMetadata(BaseModel):
    markets: list[str] = Field(default_factory=lambda: ["US"])
    platforms: list[str] = Field(default_factory=lambda: ["etsy"])
    title: str | None = None
    notes: str | None = None


class ComplianceReport(BaseModel):
    design_id: str
    filename: str
    source: str = Field(description="upload | csv | link | folder")
    source_ref: str | None = None
    metadata: DesignMetadata

    verdict: Verdict
    confidence: int = Field(ge=0, le=100)
    reasoning: str
    summary: str

    niche: Niche
    findings: list[Finding] = Field(default_factory=list)
    ocr_text: str = ""
    trademark_hits: list[dict] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)

    image_width: int = 0
    image_height: int = 0
    preview_url: str | None = None
    annotated_url: str | None = None

    duration_ms: int = 0
    provider: str = ""
    error: str | None = None
