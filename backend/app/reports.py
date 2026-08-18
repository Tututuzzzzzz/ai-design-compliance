"""Batch report export — CSV and Excel."""

from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .pipeline import i18n
from .pipeline.i18n import DEFAULT_LANG, Lang

#: Column order. Headers are looked up per language at export time.
COLUMN_KEYS = [
    "filename",
    "verdict",
    "confidence",
    "niche",
    "sub_niche",
    "style",
    "motifs",
    "risk_categories",
    "finding_count",
    "top_severity",
    "rights_holders",
    "trademark_matches",
    "regions",
    "remediation",
    "markets",
    "platforms",
    "ocr_text",
    "source",
    "source_ref",
    "reasoning",
    "error",
]


def columns(lang: Lang) -> list[tuple[str, str]]:
    return [(key, i18n.export(key, lang)) for key in COLUMN_KEYS]

_SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

FILLS = {
    "SAFE": PatternFill("solid", fgColor="D1FAE5"),
    "RISKY": PatternFill("solid", fgColor="FEF3C7"),
    "BLOCKED": PatternFill("solid", fgColor="FEE2E2"),
}


def flatten(design: dict[str, Any], lang: Lang = DEFAULT_LANG) -> dict[str, Any]:
    report = design.get("report") or {}
    niche = report.get("niche") or {}
    findings = report.get("findings") or []
    hits = report.get("trademark_hits") or []
    meta = report.get("metadata") or {}

    top_sev = ""
    if findings:
        top_sev = max(findings, key=lambda f: _SEV_ORDER.get(f.get("severity", "low"), 0))[
            "severity"
        ]

    verdict_value = report.get("verdict") or design.get("verdict")
    return {
        "filename": design.get("filename", ""),
        "verdict": (
            i18n.verdict(verdict_value, lang) if verdict_value else i18n.export("failed", lang)
        ),
        "confidence": report.get("confidence", 0),
        "niche": niche.get("primary", ""),
        "sub_niche": niche.get("sub_niche") or "",
        "style": ", ".join(niche.get("style") or []),
        "motifs": ", ".join(niche.get("motifs") or []),
        "risk_categories": ", ".join(
            sorted({i18n.category(f.get("category", ""), lang) for f in findings})
        ),
        "finding_count": len(findings),
        "top_severity": i18n.severity_inline(top_sev, lang) if top_sev else "",
        "rights_holders": ", ".join(
            sorted({f["rights_holder"] for f in findings if f.get("rights_holder")})
        ),
        "trademark_matches": " | ".join(
            f"{h.get('mark_text')} ({h.get('similarity')}%"
            + (f", #{h['serial_number']}" if h.get("serial_number") else "")
            + ")"
            for h in hits
        ),
        "regions": " | ".join(_region(f) for f in findings if f.get("bbox") or f.get("location_hint")),
        "remediation": " | ".join(f.get("remediation", "") for f in findings),
        "markets": ", ".join(meta.get("markets") or []),
        "platforms": ", ".join(meta.get("platforms") or []),
        "ocr_text": (report.get("ocr_text") or "").replace("\n", " / "),
        "source": design.get("source", ""),
        "source_ref": design.get("source_ref") or "",
        "reasoning": report.get("reasoning", ""),
        "error": design.get("error") or report.get("error") or "",
    }


def _region(f: dict[str, Any]) -> str:
    box = f.get("bbox")
    hint = f.get("location_hint") or f.get("title", "")
    if not box:
        return hint
    return (
        f"{hint} [x={box['x']:.2f} y={box['y']:.2f} w={box['w']:.2f} h={box['h']:.2f}]"
    )


def to_csv(designs: list[dict[str, Any]], lang: Lang = DEFAULT_LANG) -> bytes:
    cols = columns(lang)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[k for k, _ in cols], extrasaction="ignore")
    writer.writerow({k: label for k, label in cols})
    for d in designs:
        writer.writerow(flatten(d, lang))
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens UTF-8 correctly


def to_xlsx(
    designs: list[dict[str, Any]], stats: dict[str, int], lang: Lang = DEFAULT_LANG
) -> bytes:
    cols = columns(lang)
    wb = Workbook()

    ws = wb.active
    ws.title = i18n.export("sheet.summary", lang)
    ws.append([i18n.export("metric", lang), i18n.export("count", lang)])
    ws["A1"].font = ws["B1"].font = Font(bold=True)
    total = sum(stats.values())
    for key in ("SAFE", "RISKY", "BLOCKED", "FAILED"):
        label = i18n.verdict(key, lang) if key in FILLS else i18n.export("failed", lang)
        ws.append([label, stats.get(key, 0)])
        if key in FILLS:
            ws.cell(row=ws.max_row, column=1).fill = FILLS[key]
    ws.append([i18n.export("total", lang), total])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 10

    det = wb.create_sheet(i18n.export("sheet.designs", lang))
    det.append([label for _, label in cols])
    for cell in det[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center")
    det.freeze_panes = "A2"

    for d in designs:
        row = flatten(d, lang)
        det.append([row[k] for k, _ in cols])
        # Colour by the raw verdict, not the translated label.
        raw_verdict = (d.get("report") or {}).get("verdict") or d.get("verdict")
        fill = FILLS.get(str(raw_verdict))
        if fill:
            det.cell(row=det.max_row, column=2).fill = fill

    det.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{det.max_row}"
    widths = {"filename": 34, "reasoning": 70, "remediation": 60, "ocr_text": 40}
    for i, (key, _) in enumerate(cols, start=1):
        det.column_dimensions[get_column_letter(i)].width = widths.get(key, 18)

    fnd = wb.create_sheet(i18n.export("sheet.findings", lang))
    fnd.append([
        i18n.export("filename", lang),
        i18n.export("category", lang),
        i18n.export("severity", lang),
        i18n.export("confidence", lang),
        i18n.export("title", lang),
        i18n.export("rights_holder", lang),
        i18n.export("matched_text", lang),
        i18n.export("location", lang),
        i18n.export("evidence", lang),
        i18n.export("remediation", lang),
    ])
    for cell in fnd[1]:
        cell.font = Font(bold=True)
    for d in designs:
        report = d.get("report") or {}
        for f in report.get("findings") or []:
            fnd.append([
                d.get("filename", ""),
                i18n.category(f.get("category", ""), lang),
                i18n.severity_inline(f.get("severity", ""), lang),
                f"{float(f.get('confidence') or 0):.0%}",
                f.get("title", ""),
                f.get("rights_holder") or "",
                f.get("matched_text") or "",
                _region(f),
                " ; ".join(
                    (e.get("reference_id") or e.get("detail") or "")
                    for e in (f.get("evidence") or [])
                ),
                f.get("remediation", ""),
            ])
    for i, w in enumerate([30, 24, 12, 12, 46, 24, 24, 34, 44, 56], start=1):
        fnd.column_dimensions[get_column_letter(i)].width = w

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
