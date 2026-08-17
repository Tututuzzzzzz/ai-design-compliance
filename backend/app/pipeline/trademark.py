"""Trademark cross-reference against real registers.

Primary source is a local SQLite/FTS5 index built from USPTO bulk data
(`python -m data.build_uspto_index`). Live USPTO and EUIPO lookups are
best-effort supplements — if either is unreachable the pipeline degrades to the
local index and says so in the report rather than inventing a result.

Nothing in this module ever synthesises a serial number, owner, or status.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache

import httpx
from rapidfuzz import fuzz

from ..config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()

# Phrases too generic to be worth checking — every design has some of these.
STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "are", "was", "not", "but",
    "this", "that", "from", "have", "has", "all", "one", "out", "day", "life",
    "love", "mom", "dad", "shirt", "tee", "gift", "est", "since", "vintage",
    "classic", "original", "best", "team", "club", "crew", "squad", "vibes",
}

# A registered mark is only a real hit if the registration is alive.
LIVE_STATUSES = {"live", "registered", "published", "pending"}


@dataclass
class TrademarkHit:
    query: str
    mark_text: str
    similarity: float
    source: str
    serial_number: str | None = None
    registration_number: str | None = None
    owner: str | None = None
    status: str | None = None
    filing_date: str | None = None
    classes: str | None = None
    url: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Local index
# --------------------------------------------------------------------------


def index_available() -> bool:
    """True only when the index actually holds marks.

    A zero-row database file is worse than none: it makes the UI claim offline
    matching is on while every lookup silently misses.
    """
    return index_stats()["marks"] > 0


@lru_cache(maxsize=1)
def _index_conn() -> sqlite3.Connection | None:
    if not (settings.uspto_db_path.exists() and settings.uspto_db_path.stat().st_size > 0):
        log.warning(
            "USPTO index missing at %s — run `python -m data.build_uspto_index` "
            "to enable offline trademark matching.",
            settings.uspto_db_path,
        )
        return None
    conn = sqlite3.connect(settings.uspto_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def index_stats() -> dict:
    conn = _index_conn()
    if conn is None:
        return {"available": False, "marks": 0}
    try:
        with _lock:
            row = conn.execute("SELECT COUNT(*) c FROM marks").fetchone()
    except sqlite3.Error:  # file exists but was never populated
        return {"available": False, "marks": 0}
    marks = row["c"] if row else 0
    return {"available": marks > 0, "marks": marks}


def normalize(text: str) -> str:
    text = text.upper()
    text = text.replace("❤", " HEART ").replace("♥", " HEART ").replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fts_query(norm: str) -> str:
    tokens = [t for t in norm.split() if len(t) > 1]
    return " OR ".join(f'"{t}"' for t in tokens)


def search_local(phrase: str, *, min_similarity: float = 82.0, limit: int = 5) -> list[TrademarkHit]:
    conn = _index_conn()
    if conn is None:
        return []

    norm = normalize(phrase)
    if not _is_checkable(norm):
        return []

    query = _fts_query(norm)
    if not query:
        return []

    try:
        with _lock:
            rows = conn.execute(
                "SELECT m.serial_number, m.registration_number, m.mark_text, m.mark_norm,"
                "       m.owner, m.status, m.filing_date, m.classes"
                " FROM marks_fts f JOIN marks m ON m.rowid = f.rowid"
                " WHERE marks_fts MATCH ? LIMIT 400",
                (query,),
            ).fetchall()
    except sqlite3.OperationalError as exc:
        log.warning("Trademark FTS query failed for %r: %s", phrase, exc)
        return []

    hits: list[TrademarkHit] = []
    for row in rows:
        score = fuzz.token_sort_ratio(norm, row["mark_norm"] or "")
        if score < min_similarity:
            continue
        status = (row["status"] or "").lower()
        if status and not any(s in status for s in LIVE_STATUSES):
            continue
        serial = row["serial_number"]
        hits.append(
            TrademarkHit(
                query=phrase,
                mark_text=row["mark_text"],
                similarity=round(score, 1),
                source="uspto_local_index",
                serial_number=serial,
                registration_number=row["registration_number"],
                owner=row["owner"],
                status=row["status"],
                filing_date=row["filing_date"],
                classes=row["classes"],
                url=(
                    f"https://tsdr.uspto.gov/#caseNumber={serial}"
                    "&caseType=SERIAL_NO&searchType=statusSearch"
                    if serial
                    else None
                ),
            )
        )

    hits.sort(key=lambda h: h.similarity, reverse=True)
    return hits[:limit]


def _is_checkable(norm: str) -> bool:
    """Filter out phrases that would only produce noise."""
    if len(norm) < 3:
        return False
    words = norm.split()
    if len(words) > 8:
        return False
    if all(w.lower() in STOPWORDS for w in words):
        return False
    if len(words) == 1 and len(words[0]) < 4:
        return False
    return True


# --------------------------------------------------------------------------
# Live USPTO (best effort)
# --------------------------------------------------------------------------


class LiveLookupError(RuntimeError):
    """The live register could not be reached or returned an unusable response."""


def search_live(phrase: str, limit: int = 3) -> list[TrademarkHit]:
    """Never-raising wrapper — an unreachable register yields no hits."""
    try:
        return _search_live_raw(phrase, limit)
    except LiveLookupError as exc:
        log.info("Live USPTO lookup unavailable for %r: %s", phrase, exc)
        return []


def _search_live_raw(phrase: str, limit: int = 3) -> list[TrademarkHit]:
    """Raises LiveLookupError on transport failure; returns [] for a clean miss."""
    if not settings.uspto_live_lookup:
        return []
    if not settings.uspto_api_key:
        raise LiveLookupError(
            "USPTO Open Data Portal needs an API key — set USPTO_API_KEY "
            "(free: https://data.uspto.gov/apis/getting-started)"
        )
    norm = normalize(phrase)
    if not _is_checkable(norm):
        return []

    url = f"{settings.uspto_api_base}/trademark/search"
    try:
        with httpx.Client(timeout=12) as client:
            resp = client.post(
                url,
                json={"query": norm, "rows": limit, "start": 0},
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": settings.uspto_api_key,
                },
            )
            if resp.status_code in (401, 403):
                raise LiveLookupError(f"USPTO rejected the API key (HTTP {resp.status_code})")
            if resp.status_code != 200:
                raise LiveLookupError(f"HTTP {resp.status_code} from {url}")
            payload = resp.json()
    except LiveLookupError:
        raise
    except Exception as exc:  # network error / malformed JSON
        raise LiveLookupError(str(exc)) from exc

    hits: list[TrademarkHit] = []
    for item in _iter_live_records(payload)[:limit]:
        mark = _first(item, "markIdentification", "wordmark", "mark_identification")
        if not mark:
            continue
        serial = _first(item, "serialNumber", "serial_number")
        hits.append(
            TrademarkHit(
                query=phrase,
                mark_text=mark,
                similarity=round(fuzz.token_sort_ratio(norm, normalize(mark)), 1),
                source="uspto_live_api",
                serial_number=str(serial) if serial else None,
                registration_number=_str_or_none(
                    _first(item, "registrationNumber", "registration_number")
                ),
                owner=_first(item, "ownerName", "owner", "current_owner"),
                status=_first(item, "statusLabel", "status", "liveDead"),
                filing_date=_first(item, "filingDate", "filing_date"),
                url=(
                    f"https://tsdr.uspto.gov/#caseNumber={serial}"
                    "&caseType=SERIAL_NO&searchType=statusSearch"
                    if serial
                    else None
                ),
            )
        )
    return hits


def _iter_live_records(payload) -> list[dict]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("results", "hits", "docs", "response", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, dict)]
        if isinstance(value, dict):
            return _iter_live_records(value)
    return []


def _first(item: dict, *keys: str):
    for key in keys:
        value = item.get(key)
        if isinstance(value, list) and value:
            value = value[0]
        if value not in (None, ""):
            return value
    return None


def _str_or_none(value) -> str | None:
    return str(value) if value not in (None, "") else None


# --------------------------------------------------------------------------
# Facade
# --------------------------------------------------------------------------


#: Live lookups are one HTTP round-trip each, so a 100-phrase design would take
#: minutes. The local index has no such cost and stays uncapped.
MAX_LIVE_LOOKUPS = 12
#: After this many consecutive live failures, stop trying for the rest of the design.
LIVE_FAILURE_BUDGET = 3


def check(phrases: list[str], *, markets: list[str]) -> list[TrademarkHit]:
    """Check candidate phrases against every configured register. Deduped."""
    seen: set[tuple[str, str]] = set()
    out: list[TrademarkHit] = []

    use_live = settings.uspto_live_lookup and "US" in markets
    live_calls = 0
    live_errors = 0

    for phrase in dict.fromkeys(p.strip() for p in phrases if p and p.strip()):
        found = search_local(phrase)

        if (
            not found
            and use_live
            and live_calls < MAX_LIVE_LOOKUPS
            and live_errors < LIVE_FAILURE_BUDGET
        ):
            live_calls += 1
            try:
                found = _search_live_raw(phrase)
            except LiveLookupError as exc:
                # An empty result is a legitimate "no such mark"; only transport
                # failures count against the budget.
                live_errors += 1
                log.info("Live USPTO lookup failed for %r: %s", phrase, exc)
                found = []

        for hit in found:
            key = (normalize(hit.query), hit.serial_number or hit.mark_text)
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)

    out.sort(key=lambda h: h.similarity, reverse=True)
    return out
