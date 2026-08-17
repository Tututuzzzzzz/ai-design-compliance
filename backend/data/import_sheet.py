"""Convert the organisers' sample spreadsheet into an evaluation manifest.

    # export the sheet tab as CSV first (File > Download > CSV, or:)
    curl -L "https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>" -o sheet.csv

    python -m data.import_sheet sheet.csv --designs ./designs -o manifest.csv

The sheet's `design` column holds images inserted over the cells. Those are not
included in any Google export (CSV, XLSX and HTML all come back without them) and
the Sheets API does not expose them to API-key auth, so the image files have to be
saved from the browser and dropped into --designs. Files are matched to rows by
row number: `1.png`, `2.png`, ... or any name starting with the row number.

Their `expected_violation_type` vocabulary is mapped onto our risk categories:

    Character            -> copyrighted_character
    Logo, Brand Name     -> brand_logo
    Text/Band Name       -> trademarked_phrase
    Celebrity Likeness   -> public_figure
    Artwork/Copyright    -> copyrighted_artwork
    Font                 -> licensed_font
    Sensitive/Prohibited -> prohibited_content
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The sheet's vocabulary is coarser than our seven categories, so each label maps
# to the SET of our categories that would be a correct answer.
#
# "Text/Band Name" is the clearest case: a band name on a shirt is simultaneously
# a registered wordmark and the band's brand identity, and the artwork around it
# is usually a logo or mascot. Insisting on `trademarked_phrase` alone would score
# a correct detection as wrong just because we filed it under a different heading.
CATEGORY_MAP = {
    "character": "copyrighted_character",
    "logo": "brand_logo",
    "brand name": "brand_logo|trademarked_phrase",
    "brand": "brand_logo|trademarked_phrase",
    "text/band name": "trademarked_phrase|brand_logo|copyrighted_character",
    "band name": "trademarked_phrase|brand_logo|copyrighted_character",
    "text": "trademarked_phrase",
    "slogan": "trademarked_phrase",
    "trademark": "trademarked_phrase|brand_logo",
    "celebrity likeness": "public_figure",
    "celebrity": "public_figure",
    "likeness": "public_figure",
    "artwork/copyright": "copyrighted_artwork|copyrighted_character",
    "artwork": "copyrighted_artwork|copyrighted_character",
    "copyright": "copyrighted_artwork|copyrighted_character",
    "font": "licensed_font",
    "sensitive": "prohibited_content",
    "prohibited": "prohibited_content",
    "weapon": "prohibited_content",
}

PLATFORM_MAP = {
    "etsy": "etsy",
    "amazon merch": "amazon_merch",
    "amazon": "amazon_merch",
    "merch by amazon": "amazon_merch",
    "tiktok shop": "tiktok_shop",
    "tiktok": "tiktok_shop",
    "shopify": "shopify",
    "redbubble": "redbubble",
}


def map_category(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key:
        return ""
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    for needle, value in CATEGORY_MAP.items():
        if needle in key:
            return value
    return ""


def map_platform(raw: str) -> str:
    key = (raw or "").strip().lower()
    return PLATFORM_MAP.get(key, next((v for k, v in PLATFORM_MAP.items() if k in key), "etsy"))


def find_design(designs_dir: Path, row_no: str, given: str) -> str:
    """Match a sheet row to a file on disk."""
    if given:
        candidate = designs_dir / Path(given).name
        if candidate.exists():
            return candidate.name

    for path in sorted(designs_dir.iterdir()):
        if not path.is_file() or path.name.lower() == "manifest.csv":
            continue
        # Leading row number, optionally zero-padded, not followed by another
        # digit — so "3.png", "03.png" and "03_olympics.png" all match row 3,
        # while "30.png" does not. A \b here would fail on "03_olympics" because
        # underscore counts as a word character.
        if re.match(rf"^0*{re.escape(row_no)}(?![0-9])", path.stem):
            return path.name
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("sheet", type=Path, help="CSV exported from the organisers' spreadsheet")
    ap.add_argument("--designs", type=Path, required=True, help="folder holding the design files")
    ap.add_argument("-o", "--out", type=Path, help="manifest path (default: <designs>/manifest.csv)")
    args = ap.parse_args()

    if not args.designs.is_dir():
        print(f"Designs folder not found: {args.designs}")
        return 1

    out = args.out or (args.designs / "manifest.csv")
    rows_in = [
        r
        for r in csv.DictReader(args.sheet.open(encoding="utf-8-sig"))
        if any((v or "").strip() for v in r.values())
    ]

    written, missing = 0, []
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "filename",
                "expected",
                "expected_category",
                "expected_niche",
                "expected_sub_niche",
                "markets",
                "platforms",
                "note",
            ]
        )
        for r in rows_in:
            no = (r.get("no") or "").strip()
            filename = find_design(args.designs, no, (r.get("design") or "").strip())
            if not filename:
                missing.append(no or "?")
                continue

            w.writerow(
                [
                    filename,
                    (r.get("expected_verdict") or "").strip().upper(),
                    map_category(r.get("expected_violation_type") or ""),
                    (r.get("expected_niche") or "").strip(),
                    (r.get("expected_sub_niche") or "").strip(),
                    (r.get("target_market") or "US").strip(),
                    map_platform(r.get("platform") or ""),
                    (r.get("expected_violation_detail") or r.get("notes") or "").strip(),
                ]
            )
            written += 1

    print(f"Wrote {written} row(s) -> {out}")
    if missing:
        print(
            f"\n{len(missing)} sheet row(s) had no matching design file "
            f"(rows: {', '.join(missing)})."
        )
        print(
            f"Save each design from the spreadsheet into {args.designs} named by its row "
            "number — 1.png, 2.png, ... — then re-run."
        )
    unmapped = {
        (r.get("expected_violation_type") or "").strip()
        for r in rows_in
        if (r.get("expected_violation_type") or "").strip()
        and not map_category(r.get("expected_violation_type") or "")
    }
    if unmapped:
        print(f"\nUnmapped violation types (add to CATEGORY_MAP): {', '.join(sorted(unmapped))}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
