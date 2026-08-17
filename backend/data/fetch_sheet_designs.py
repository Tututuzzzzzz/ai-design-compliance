"""Pull the design images out of a Google Sheet and build an eval manifest.

Images inserted *over* cells in Google Sheets cannot be right-click-saved, are
absent from the CSV and XLSX exports, and are not exposed by the Sheets API to
API-key auth. They *are* present in the zipped web-page export, as `<img>` tags
pointing at public googleusercontent URLs — which is what this script uses.

    python -m data.fetch_sheet_designs <spreadsheet-id-or-url> --gid 256492005

Writes designs to <out>/1.png, 2.png, ... in sheet row order, plus manifest.csv
ready for `python -m data.evaluate --manifest ...`.

The sheet must be shared as "anyone with the link can view".
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from data.import_sheet import map_category, map_platform  # noqa: E402

EXPORT = "https://docs.google.com/spreadsheets/d/{sid}/export"

_IMG = re.compile(r"<img[^>]*?src=[\"']([^\"']+)[\"']", re.I)
_ID = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")

_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def sheet_id(raw: str) -> str:
    m = _ID.search(raw)
    return m.group(1) if m else raw.strip()


def _get(client: httpx.Client, sid: str, **params) -> httpx.Response:
    resp = client.get(EXPORT.format(sid=sid), params=params)
    resp.raise_for_status()
    return resp


def image_urls(client: httpx.Client, sid: str) -> list[str]:
    """Read the zipped web-page export and pull out the over-cell image URLs.

    Note: no `gid` here — passing one makes this export 400. The zip covers the
    whole spreadsheet, and the images appear in sheet order.
    """
    resp = _get(client, sid, format="zip")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        pages = [n for n in zf.namelist() if n.lower().endswith((".html", ".htm"))]
        if not pages:
            raise RuntimeError("Web-page export contained no HTML — is the sheet link-shared?")
        html = zf.read(pages[0]).decode("utf-8", "ignore")

    return [_full_size(u) for u in _IMG.findall(html) if u.startswith("http")]


def _full_size(url: str) -> str:
    """Drop googleusercontent's size suffix to get the stored image.

    The export embeds thumbnails (`...=s145-w145-h144`, ~108x144) — far too small
    to read text or identify a logo from. Removing the suffix returns the full
    stored resolution. Appending a bigger size instead of replacing produces a
    double suffix and a 400.
    """
    head, sep, tail = url.rpartition("=")
    if sep and re.fullmatch(r"[swhcdp\d-]+", tail):
        return head
    return url


def rows(client: httpx.Client, sid: str, gid: str | None) -> list[dict]:
    params = {"format": "csv"}
    if gid:
        params["gid"] = gid
    text = _get(client, sid, **params).content.decode("utf-8-sig", "ignore")

    import csv  # noqa: PLC0415

    return [
        r
        for r in csv.DictReader(io.StringIO(text))
        if any((v or "").strip() for v in r.values())
    ]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("sheet", help="spreadsheet id or full URL")
    ap.add_argument("--gid", help="tab gid holding the metadata rows")
    ap.add_argument("--out", type=Path, default=settings.data_dir / "designs")
    args = ap.parse_args()

    sid = sheet_id(args.sheet)
    args.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=120, follow_redirects=True) as client:
        print("Reading sheet metadata...")
        meta = rows(client, sid, args.gid)
        print(f"  {len(meta)} row(s)")

        print("Reading web-page export for image URLs...")
        urls = image_urls(client, sid)
        print(f"  {len(urls)} image(s)")

        if len(urls) != len(meta):
            print(
                f"\n! {len(urls)} images vs {len(meta)} metadata rows. Pairing is positional,"
                " so a mismatch means some rows will be mislabelled. Check the sheet for"
                " blank rows or images outside the table before trusting the manifest."
            )

        saved: list[tuple[str, dict]] = []
        for i, (url, row) in enumerate(zip(urls, meta), start=1):
            no = (row.get("no") or str(i)).strip()
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"  row {no}: download failed ({exc})")
                continue

            ext = _EXT.get(resp.headers.get("content-type", "").split(";")[0].strip(), ".png")
            name = f"{no}{ext}"
            (args.out / name).write_bytes(resp.content)
            saved.append((name, row))
            print(f"  row {no}: {name} ({len(resp.content) / 1024:.0f} KB)")

    manifest = args.out / "manifest.csv"
    import csv  # noqa: PLC0415

    with manifest.open("w", newline="", encoding="utf-8") as fh:
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
        for name, row in saved:
            w.writerow(
                [
                    name,
                    (row.get("expected_verdict") or "").strip().upper(),
                    map_category(row.get("expected_violation_type") or ""),
                    (row.get("expected_niche") or "").strip(),
                    (row.get("expected_sub_niche") or "").strip(),
                    (row.get("target_market") or "US").strip(),
                    map_platform(row.get("platform") or ""),
                    (row.get("expected_violation_detail") or row.get("notes") or "").strip(),
                ]
            )

    print(f"\nSaved {len(saved)} design(s) + manifest -> {manifest}")
    print(f"Next:  python -m data.evaluate --manifest {manifest}")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
