"""Offline end-to-end check of the pipeline with a stubbed vision provider.

Exercises: format loading → verdict engine → policy escalation → annotation →
CSV/XLSX export. No API key and no network required.

    python -m data.smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import (  # noqa: E402
    BBox,
    DesignMetadata,
    Finding,
    Niche,
    OCRLine,
    RiskCategory,
    Severity,
    VisionAnalysis,
)
from app.pipeline import run, vision  # noqa: E402
from app import reports  # noqa: E402

CASES = {
    "safe_dog_mom.png": VisionAnalysis(
        description="Hand-lettered 'Dog Mom' with a paw print.",
        niche=Niche(
            primary="Dog Lovers",
            sub_niche="Golden Retriever mom",
            audience="Women 25-45 with dogs",
            style=["minimalist", "hand-lettered"],
            motifs=["paw print"],
            confidence=0.9,
        ),
        ocr_lines=[OCRLine(text="DOG MOM", confidence=0.98)],
        findings=[],
    ),
    "blocked_mouse.png": VisionAnalysis(
        description="Three-circle mouse silhouette in Disney style.",
        niche=Niche(primary="Theme Park", sub_niche="Family trip", style=["cartoon"], confidence=0.8),
        ocr_lines=[OCRLine(text="THE HAPPIEST PLACE ON EARTH", confidence=0.95)],
        findings=[
            Finding(
                category=RiskCategory.COPYRIGHTED_CHARACTER,
                title="Mickey Mouse head silhouette",
                description="The three-circle silhouette is the registered Mickey Mouse shape.",
                severity=Severity.CRITICAL,
                confidence=0.93,
                rights_holder="Disney Enterprises, Inc.",
                bbox=BBox(x=0.28, y=0.14, w=0.44, h=0.42),
                location_hint="centre chest",
                remediation="Remove the silhouette entirely; a generic mouse shape is not a "
                "substitute because the proportions are what is protected.",
            )
        ],
    ),
    "risky_font.png": VisionAnalysis(
        description="Nurse design set in a commercial script face.",
        niche=Niche(primary="Nurse", sub_niche="ICU Nurse", style=["script"], confidence=0.85),
        ocr_lines=[OCRLine(text="ICU NURSE LIFE", confidence=0.9)],
        findings=[
            Finding(
                category=RiskCategory.LICENSED_FONT,
                title="Possible commercially licensed script typeface",
                description="The script face resembles a commercial font that needs a print licence.",
                severity=Severity.MEDIUM,
                confidence=0.55,
                bbox=BBox(x=0.1, y=0.4, w=0.8, h=0.2),
                location_hint="main headline",
                remediation="Confirm the font licence covers merchandise, or reset the headline "
                "in an SIL Open Font Licence face.",
            )
        ],
    ),
}


def make_png(path: Path, label: str) -> None:
    img = Image.new("RGB", (900, 900), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse([300, 200, 600, 500], outline="black", width=8)
    draw.text((80, 700), label, fill="black")
    img.save(path)


def main() -> int:
    tmp = Path(__file__).resolve().parent.parent / "var" / "smoke"
    tmp.mkdir(parents=True, exist_ok=True)

    original = vision.analyze
    designs = []

    try:
        for name, analysis in CASES.items():
            src = tmp / name
            make_png(src, name)

            vision.analyze = lambda _p, _m, a=analysis: (a, "stub:offline")  # type: ignore[assignment]
            report = run.analyze_design(
                design_id=name.split(".")[0],
                path=src,
                filename=name,
                source="upload",
                source_ref=None,
                meta=DesignMetadata(markets=["US", "EU"], platforms=["amazon_merch"]),
            )
            designs.append({"filename": name, "source": "upload", "report": report.model_dump(mode="json")})

            print(f"\n{name}")
            print(f"  verdict     {report.verdict.value} ({report.confidence}%)")
            print(f"  niche       {report.niche.primary} / {report.niche.sub_niche}")
            print(f"  findings    {len(report.findings)}")
            for f in report.findings:
                print(f"    - [{f.severity.value}] {f.category.value}: {f.title}")
            print(f"  annotated   {report.annotated_url or 'n/a'}")
            print(f"  policy      {len(report.policy_notes)} note(s)")
    finally:
        vision.analyze = original  # type: ignore[assignment]

    csv_bytes = reports.to_csv(designs)
    xlsx_bytes = reports.to_xlsx(designs, {"SAFE": 1, "RISKY": 1, "BLOCKED": 1, "FAILED": 0})
    (tmp / "report.csv").write_bytes(csv_bytes)
    (tmp / "report.xlsx").write_bytes(xlsx_bytes)
    print(f"\nExports: {len(csv_bytes)} B CSV, {len(xlsx_bytes)} B XLSX → {tmp}")

    verdicts = [d["report"]["verdict"] for d in designs]
    expected = ["SAFE", "BLOCKED", "RISKY"]
    if verdicts != expected:
        print(f"\nFAIL: expected {expected}, got {verdicts}")
        return 1
    print("\nOK — verdict engine, policy layer, annotation and exports all behaved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
