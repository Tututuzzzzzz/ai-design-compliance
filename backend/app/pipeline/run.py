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
from . import annotate, i18n, loader, ocr, rules, trademark, verdict, vision

log = logging.getLogger(__name__)


class AnalysisFailed(RuntimeError):
    """A pipeline failure that happened *after* the render existed.

    Carries the render so the UI can still show the design next to the error —
    a failed row with no image looks like the upload itself was lost.
    """

    def __init__(self, cause: Exception, render_path: Path | None = None) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.render_path = render_path


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
    render = loader.prepare(path)

    try:
        return _analyze_rendered(
            design_id, render, filename, source, source_ref, meta, started
        )
    except Exception as exc:
        # Attach the render so the caller can still show the design with the error.
        raise AnalysisFailed(exc, render.display_path) from exc


def _analyze_rendered(
    design_id: str,
    render: loader.Render,
    filename: str,
    source: str,
    source_ref: str | None,
    meta: DesignMetadata,
    started: float,
) -> ComplianceReport:
    lang = i18n.normalize(meta.language)
    render_path = render.path

    # 2. Local OCR first — its boxes are pixel-accurate where the model's are
    #    estimates. If the engine is not installed we use the model's OCR instead.
    #    Normalise against the RENDER size: OCR reads the rendered PNG, so dividing
    #    by the source size would scale every box by the crop-and-resize ratio.
    ocr_lines = ocr.extract(render_path, render.render_width, render.render_height)
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
                detail=i18n.t("evidence.vision", lang, provider=provider),
            )
        ]

    # 4. Cross-reference every text candidate against the real trademark register.
    candidates = _tm_candidates(ocr_lines, findings)
    hits = trademark.check(candidates, markets=meta.markets)
    findings = verdict.merge_trademark_hits(findings, hits, lang)

    # 5. Apply platform / market policy.
    findings, policy_notes = rules.apply(findings, meta.platforms, meta.markets, lang)

    # 5b. A phrase no register could confirm is a lead, not a violation — and the
    #     cap is applied AFTER policy so escalation can never push an unverified
    #     claim up to a blocking severity. Evidence quality bounds consequence.
    findings = verdict.cap_unverified_phrases(findings, lang)

    # 6. Decide.
    final_verdict, confidence, reasoning = verdict.decide(findings, lang)

    annotated = annotate.render(render.display_path, findings)

    return ComplianceReport(
        design_id=design_id,
        filename=filename,
        source=source,
        source_ref=source_ref,
        metadata=meta,
        verdict=final_verdict,
        confidence=confidence,
        reasoning=reasoning,
        summary=verdict.summarize(final_verdict, findings, lang),
        niche=analysis.niche,
        findings=findings,
        ocr_text="\n".join(line.text for line in ocr_lines),
        trademark_hits=[h.as_dict() for h in hits],
        policy_notes=policy_notes,
        image_width=render.width,
        image_height=render.height,
        preview_url=f"/api/files/{render.display_path.name}",
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
        # 3 words minimum. A two-word window is too small a unit to carry brand
        # meaning out of context, and a complete register holds a live mark for
        # very nearly every pair of common words — checking 2-grams against one
        # turns "JUST DON'T DO IT." into registered hits for "JUST DON",
        # "DON T", "T DO" and "DO IT", each an exact match to somebody, none of
        # them what the shirt says. A genuinely two-word mark ("GOT MILK") is
        # the whole line on a shirt, and the whole line is already a candidate.
        for n in (4, 3):
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
    render_path: Path | None = None,
) -> ComplianceReport:
    from ..models import Niche  # local import to avoid a cycle at module load

    lang = i18n.normalize(meta.language)
    return ComplianceReport(
        preview_url=f"/api/files/{render_path.name}" if render_path else None,
        design_id=design_id,
        filename=filename,
        source=source,
        source_ref=source_ref,
        metadata=meta,
        verdict=Verdict.RISKY,
        confidence=0,
        reasoning=i18n.t("failed.reasoning", lang, error=error),
        summary=i18n.t("failed.summary", lang, error=error),
        niche=Niche(primary=i18n.t("failed.niche", lang), confidence=0.0),
        error=error,
    )
