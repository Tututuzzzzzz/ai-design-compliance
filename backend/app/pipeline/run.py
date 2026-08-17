"""End-to-end analysis of one design."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from ..models import (
    ComplianceReport,
    DesignMetadata,
    Evidence,
    Finding,
    OCRLine,
    Verdict,
    VisionAnalysis,
)
from . import annotate, loader, ocr, rules, trademark, verdict, vision

log = logging.getLogger(__name__)


def analyze_design(
    design_id: str,
    path: Path,
    filename: str,
    source: str,
    source_ref: str | None,
    meta: DesignMetadata,
) -> ComplianceReport:
    started = time.perf_counter()

    # 1. Normalise any supported format into a flat PNG.
    render_path, width, height = loader.prepare(path)

    # 2. Local OCR first — its boxes are pixel-accurate where the model's are
    #    estimates. If the engine is not installed we use the model's OCR instead.
    ocr_lines = ocr.extract(render_path, width, height)
    used_local_ocr = bool(ocr_lines)

    # 3. Vision analysis: niche + risk findings (+ OCR when local OCR is absent).
    analysis, provider = vision.analyze(render_path, meta)
    _repair_boxes(analysis, render_path)
    if not used_local_ocr:
        ocr_lines = analysis.ocr_lines

    findings = list(analysis.findings)
    for f in findings:
        # Discard whatever the model put in `evidence` and stamp our own.
        # Models will happily cite "uspto_local_index" for a lookup that never
        # happened, which would both fabricate a source and bypass the
        # register-verification cap applied below. Evidence is attached by this
        # pipeline only — the model's contribution is the finding itself.
        f.evidence = [
            Evidence(
                source="vision_model",
                detail=f"Identified by {provider} from the artwork itself.",
            )
        ]

    # 4. Cross-reference every text candidate against the real trademark register.
    candidates = _tm_candidates(ocr_lines, findings)
    hits = trademark.check(candidates, markets=meta.markets)
    findings = verdict.merge_trademark_hits(findings, hits)

    # 5. Apply platform / market policy.
    findings, policy_notes = rules.apply(findings, meta.platforms, meta.markets)

    # 5b. A phrase no register could confirm is a lead, not a violation — and the
    #     cap is applied AFTER policy so escalation can never push an unverified
    #     claim up to a blocking severity. Evidence quality bounds consequence.
    findings = verdict.cap_unverified_phrases(findings)
    if not trademark.index_available():
        policy_notes.append(
            "Local USPTO index not built — text was checked against the live USPTO "
            "search only. Run `python -m data.build_uspto_index` for offline coverage."
        )

    # 6. Decide.
    final_verdict, confidence, reasoning = verdict.decide(findings)

    annotated = annotate.render(render_path, findings)

    return ComplianceReport(
        design_id=design_id,
        filename=filename,
        source=source,
        source_ref=source_ref,
        metadata=meta,
        verdict=final_verdict,
        confidence=confidence,
        reasoning=reasoning,
        summary=verdict.summarize(final_verdict, findings),
        niche=analysis.niche,
        findings=findings,
        ocr_text="\n".join(line.text for line in ocr_lines),
        trademark_hits=[h.as_dict() for h in hits],
        policy_notes=policy_notes,
        image_width=width,
        image_height=height,
        preview_url=f"/api/files/{render_path.name}",
        annotated_url=f"/api/files/{annotated.name}" if annotated else None,
        duration_ms=int((time.perf_counter() - started) * 1000),
        provider=f"{provider} + {'rapidocr' if used_local_ocr else 'vision-ocr'}",
    )


def _repair_boxes(analysis: VisionAnalysis, render_path: Path) -> None:
    """Coerce model-supplied boxes to true 0..1 against the image it actually saw.

    Models routinely ignore the "normalised 0..1" instruction — Gemini emits a
    0..1000 grid, others emit pixels. A bad box should cost us the box, never the
    finding, so an unrepairable one is dropped and the finding keeps its
    `location_hint`.
    """
    from PIL import Image  # local import: only needed on this path

    with Image.open(render_path) as img:
        rw, rh = img.size

    for item in (*analysis.findings, *analysis.ocr_lines):
        if item.bbox is not None:
            item.bbox = item.bbox.rescale(rw, rh)


def _tm_candidates(ocr_lines: list[OCRLine], findings: list[Finding]) -> list[str]:
    """Build the phrase list to check against the register.

    Whole OCR lines plus 2–4 word n-grams: registered slogans are usually a
    fragment of a longer line of shirt text, so line-level checking alone misses
    them.
    """
    out: list[str] = []

    for f in findings:
        if f.matched_text:
            out.append(f.matched_text)

    for line in ocr_lines:
        text = line.text.strip()
        if not text:
            continue
        out.append(text)

        words = [w for w in re.split(r"\s+", trademark.normalize(text)) if w]
        for n in (4, 3, 2):
            if len(words) <= n:
                continue
            for i in range(len(words) - n + 1):
                out.append(" ".join(words[i : i + n]))

    # Preserve order, drop duplicates, keep the list bounded.
    return list(dict.fromkeys(out))[:120]


def failed_report(
    design_id: str,
    filename: str,
    source: str,
    source_ref: str | None,
    meta: DesignMetadata,
    error: str,
) -> ComplianceReport:
    from ..models import Niche  # local import to avoid a cycle at module load

    return ComplianceReport(
        design_id=design_id,
        filename=filename,
        source=source,
        source_ref=source_ref,
        metadata=meta,
        verdict=Verdict.RISKY,
        confidence=0,
        reasoning=(
            f"This design could not be analysed automatically: {error}. "
            "It is reported as RISKY rather than SAFE so it is never listed on the "
            "strength of a failed check — review it manually."
        ),
        summary=f"Analysis failed: {error}",
        niche=Niche(primary="unknown", confidence=0.0),
        error=error,
    )
