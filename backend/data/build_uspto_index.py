"""Build the local trademark index from **real** USPTO data.

Two sources, both official — nothing in this script invents a record:

  1. `--zip FILE`  Parse a USPTO trademark bulk zip you downloaded. This is the
                   primary route and needs no API key: browse to
                   https://data.uspto.gov/bulkdata/datasets/trademark
                   and download a "Trademark applications daily/annual XML" file.
                   Annual files are the full register — the right choice for a
                   serious offline index. Daily files are small and quick to test
                   the pipeline with.

  2. `--resolve F` Take a newline-delimited list of mark texts and look each one
                   up against the live USPTO Open Data Portal API, storing only
                   what the register actually returns. Needs USPTO_API_KEY
                   (free: https://data.uspto.gov/apis/getting-started).

Usage:
    python -m data.build_uspto_index --zip ~/Downloads/apc250801.zip
    python -m data.build_uspto_index --resolve data/watchlist.txt

Re-running is additive and idempotent (upsert by serial number).

NOTE: the old `bulkdata.uspto.gov` host was retired by USPTO and no longer
resolves; automatic daily download was removed with it. Downloading a zip from
the portal above is the supported replacement.
"""

from __future__ import annotations

import argparse
import io
import logging
import sqlite3
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.pipeline import trademark  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("uspto-index")

SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (
    serial_number       TEXT PRIMARY KEY,
    registration_number TEXT,
    mark_text           TEXT NOT NULL,
    mark_norm           TEXT NOT NULL,
    owner               TEXT,
    status              TEXT,
    filing_date         TEXT,
    classes             TEXT,
    source              TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS marks_fts
    USING fts5(mark_norm, content='marks', content_rowid='rowid');
"""

# USPTO status codes: 6xx = registered & live, 7xx = pending/published.
# Full list: https://www.uspto.gov/sites/default/files/documents/tmstatuscodes.pdf
LIVE_PREFIXES = ("6", "7")


def connect() -> sqlite3.Connection:
    settings.uspto_db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.uspto_db_path)
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    cur = conn.cursor()
    written = 0
    for r in rows:
        norm = trademark.normalize(r["mark_text"])
        if not norm:
            continue
        cur.execute(
            "INSERT INTO marks (serial_number, registration_number, mark_text, mark_norm,"
            " owner, status, filing_date, classes, source) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(serial_number) DO UPDATE SET"
            " registration_number=excluded.registration_number,"
            " mark_text=excluded.mark_text, mark_norm=excluded.mark_norm,"
            " owner=excluded.owner, status=excluded.status,"
            " filing_date=excluded.filing_date, classes=excluded.classes,"
            " source=excluded.source",
            (
                r["serial_number"],
                r.get("registration_number"),
                r["mark_text"],
                norm,
                r.get("owner"),
                r.get("status"),
                r.get("filing_date"),
                r.get("classes"),
                r["source"],
            ),
        )
        written += 1
    conn.commit()
    return written


def rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO marks_fts(marks_fts) VALUES('rebuild')")
    conn.commit()


# --------------------------------------------------------------------------
# Bulk XML parsing
# --------------------------------------------------------------------------


def _tag(elem: ET.Element) -> str:
    return elem.tag.rsplit("}", 1)[-1]


def _text(parent: ET.Element, name: str) -> str | None:
    for child in parent.iter():
        if _tag(child) == name and (child.text or "").strip():
            return child.text.strip()
    return None


def parse_case_files(stream: io.BufferedReader, source: str) -> list[dict]:
    rows: list[dict] = []
    for _event, elem in ET.iterparse(stream, events=("end",)):
        if _tag(elem) != "case-file":
            continue
        try:
            serial = _text(elem, "serial-number")
            mark = _text(elem, "mark-identification")
            if not serial or not mark:
                continue

            status = _text(elem, "status-code")
            if status and not status.startswith(LIVE_PREFIXES):
                continue  # dead / abandoned — not enforceable

            owner = None
            for child in elem.iter():
                if _tag(child) == "case-file-owner":
                    owner = _text(child, "party-name")
                    if owner:
                        break

            classes = sorted(
                {
                    (c.text or "").strip()
                    for c in elem.iter()
                    if _tag(c) == "international-code" and (c.text or "").strip()
                }
            )

            rows.append(
                {
                    "serial_number": serial,
                    "registration_number": _text(elem, "registration-number"),
                    "mark_text": mark,
                    "owner": owner,
                    "status": f"live ({status})" if status else "live",
                    "filing_date": _text(elem, "filing-date"),
                    "classes": ",".join(classes) or None,
                    "source": source,
                }
            )
        finally:
            elem.clear()
    return rows


def ingest_zip(conn: sqlite3.Connection, zip_path: Path) -> int:
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".xml"):
                continue
            log.info("Parsing %s :: %s", zip_path.name, name)
            with zf.open(name) as fh:
                rows = parse_case_files(fh, f"uspto_bulk:{zip_path.name}")
            total += upsert(conn, rows)
            log.info("  +%d live marks (running total %d)", len(rows), total)
    return total


# --------------------------------------------------------------------------
# Watchlist resolution via the live register
# --------------------------------------------------------------------------


def resolve_watchlist(conn: sqlite3.Connection, path: Path) -> int:
    phrases = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    log.info("Resolving %d watchlist phrases against the live USPTO register", len(phrases))

    rows: list[dict] = []
    misses: list[str] = []
    for phrase in phrases:
        hits = trademark.search_live(phrase, limit=3)
        if not hits:
            misses.append(phrase)
            continue
        for h in hits:
            if not h.serial_number:
                continue
            rows.append(
                {
                    "serial_number": h.serial_number,
                    "registration_number": h.registration_number,
                    "mark_text": h.mark_text,
                    "owner": h.owner,
                    "status": h.status or "live",
                    "filing_date": h.filing_date,
                    "classes": h.classes,
                    "source": "uspto_live_api",
                }
            )

    if misses:
        log.warning(
            "No live-register result for %d phrase(s) — they are NOT added to the index: %s",
            len(misses),
            ", ".join(misses[:10]) + ("..." if len(misses) > 10 else ""),
        )
    return upsert(conn, rows)


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", type=Path, nargs="*", default=[], help="parse local USPTO bulk zip(s)")
    ap.add_argument("--resolve", type=Path, help="newline-delimited phrases to resolve live")
    args = ap.parse_args()

    if not (args.zip or args.resolve):
        ap.error("pick at least one source: --zip or --resolve")

    conn = connect()
    total = 0

    for zip_path in args.zip:
        if not zip_path.exists():
            log.error("Not found: %s", zip_path)
            continue
        total += ingest_zip(conn, zip_path)

    if args.resolve:
        total += resolve_watchlist(conn, args.resolve)

    rebuild_fts(conn)
    count = conn.execute("SELECT COUNT(*) FROM marks").fetchone()[0]
    conn.close()

    log.info("Index written to %s — %d marks total (%d touched this run)",
             settings.uspto_db_path, count, total)
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
