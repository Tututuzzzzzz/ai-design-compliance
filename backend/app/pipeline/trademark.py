"""Trademark cross-reference against real registers.

Every source is live and market-gated: the public USPTO search (no credential,
current register, and it returns the Nice classes), the keyed USPTO Open Data
Portal API as a fallback behind it, and EUIPO for EU markets. All are
best-effort — if one is unreachable the report carries fewer hits rather than an
invented result.

There is deliberately no local bulk snapshot. An index is only as current as the
day it was built, and a stale one is worse than none: a 2010 dump answered ROXY
with class 036 owned by "Quiksilver, Inc" while the live register had the same
mark in class 025 under Boardriders — and because the snapshot was consulted
first, it hid the correct answer instead of supplementing it.

Nothing in this module ever synthesises a serial number, owner, or status.
"""

from __future__ import annotations

import logging
import concurrent.futures
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass

import httpx
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from ..config import settings

log = logging.getLogger(__name__)

# Phrases too generic to be worth checking — every design has some of these.
STOPWORDS = {
    "the", "and", "for", "with", "you", "your", "are", "was", "not", "but",
    "this", "that", "from", "have", "has", "all", "one", "out", "day", "life",
    "love", "mom", "dad", "shirt", "tee", "gift", "est", "since", "vintage",
    "classic", "original", "best", "team", "club", "crew", "squad", "vibes",
}

# EUIPO's own status vocabulary. A filed-but-not-yet-registered EUTM already
# creates real exposure, so "filed" counts here even though it has no equivalent
# in the USPTO liveness flag.
EUIPO_LIVE_STATUSES = {
    "registered",
    "filed",
    "published",
    "pending",
    "opposition",
    "appeal",
}


# --------------------------------------------------------------------------
# What a registration actually reaches
# --------------------------------------------------------------------------

#: Nice classes covering the goods a print-on-demand design gets printed on.
#: A live registration outside this set is real, but it is authority over other
#: goods: Ford's class-012 "SUPREME" (vehicles) and SLI's class-011 "SUPREME"
#: (lighting) say nothing about a t-shirt. Such hits are kept and still reported
#: with full evidence — they only lose the power to escalate severity or name a
#: rights holder. Dropping them would hide real register data; treating them as
#: equal lets any dictionary word registered by anyone block a listing.
POD_CLASSES = frozenset({9, 14, 16, 18, 20, 21, 24, 25, 26, 28})


def parse_classes(classes: str | None) -> set[int]:
    """Registers disagree on formatting — USPTO bulk gives "016,021", EUIPO gives
    "25, 35". Compare as integers so "025" and "25" are the same class."""
    if not classes:
        return set()
    return {int(part) for part in re.split(r"[^0-9]+", classes) if part}


def covers_pod_goods(classes: str | None) -> bool | None:
    """True/False when the register told us the classes, None when it did not.

    Unknown is not the same as irrelevant. The live USPTO endpoint returns no
    class data at all, so defaulting a missing value to False would silently
    demote every live hit to a footnote.
    """
    parsed = parse_classes(classes)
    if not parsed:
        return None
    return bool(parsed & POD_CLASSES)


#: OCR damage scales with how much text there is, so the tolerance must too. A
#: similarity ratio does the opposite: it is relative, so on a short string one
#: wrong letter still scores high — "DO IT" vs "DOT IT" is 90.9 and clears an 85
#: threshold, which is how a packaging company's mark attached itself to a parody
#: slogan. Same for "LOVE"/"LOVER" (88.9) and "MOM LIFE"/"MOM LIFT" (87.5), while
#: the genuinely related "BEST DAD"/"BEST DAD EVER" only scores 76.2.
#: One edit per 10 characters keeps real OCR damage matchable
#: ("BLADK SABBATH" -> "BLACK SABBATH", 13 chars, 1 edit) and makes short marks
#: exact-match only.
CHARS_PER_ALLOWED_EDIT = 10


def _token_key(norm: str) -> str:
    """Token-sorted form, so the edit budget keeps the word-order tolerance that
    token_sort_ratio already grants ("SABBATH BLACK" == "BLACK SABBATH")."""
    return " ".join(sorted(norm.split()))


def within_edit_budget(query_norm: str, mark_norm: str) -> bool:
    """Absolute guard on top of the relative similarity score."""
    a, b = _token_key(query_norm), _token_key(mark_norm)
    budget = min(len(a), len(b)) // CHARS_PER_ALLOWED_EDIT
    return Levenshtein.distance(a, b) <= budget


def _rank_key(hit: "TrademarkHit") -> tuple:
    """Ordering for the limited result slots: on-class first, then similarity.

    Without the class term a prolific mark fills every slot with whichever
    registration the register happened to rank first. STUSSY has 37 live exact
    matches across 20-odd classes; taking the top 3 by similarity alone returned
    classes 011, 004 and 035, so the pipeline reported "registered for other
    goods" while seven class-025 registrations sat just outside the cut. Every
    exact match scores 100, so similarity cannot break that tie — relevance to
    the goods has to.
    """
    return (hit.covers_goods is True, hit.similarity)


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
    #: Whether this registration's classes cover print-on-demand goods.
    #: None means the register returned no classes, not that they are irrelevant.
    covers_goods: bool | None = None

    def __post_init__(self) -> None:
        # Derived in one place so every construction site — local index, live
        # USPTO, EUIPO, tests — agrees, and none can forget to set it.
        if self.covers_goods is None:
            self.covers_goods = covers_pod_goods(self.classes)

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Phrase normalisation
# --------------------------------------------------------------------------


def normalize(text: str) -> str:
    text = text.upper()
    text = text.replace("❤", " HEART ").replace("♥", " HEART ").replace("&", " AND ")
    # Drop status symbols before the NFKD fold below. NFKD expands them into
    # letters — ™ becomes "TM", ℠ becomes "SM" — so "LEVI'S™" would normalise to
    # "LEVI STM" and stop matching the registered "LEVI'S". These marks are
    # everywhere on branded apparel, so getting this wrong is not an edge case.
    text = re.sub(r"[™®©℠℗]", " ", text)
    # Fold diacritics to their base letter BEFORE stripping non-ASCII, or the
    # accent turns into a space and splits the word in two: "STÜSSY" became
    # "ST SSY", which scores 50 against the registered "STUSSY" and is dropped
    # by the 82.0 threshold. Same for "POKÉMON" (42.9) and "MOTÖRHEAD".
    # NFKD separates the combining mark, then Mn (nonspacing mark) is discarded.
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if unicodedata.category(ch) != "Mn"
    )
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
        mark_norm = normalize(mark)
        if not within_edit_budget(norm, mark_norm):
            continue
        serial = _first(item, "serialNumber", "serial_number")
        hits.append(
            TrademarkHit(
                query=phrase,
                mark_text=mark,
                similarity=round(fuzz.token_sort_ratio(norm, mark_norm), 1),
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
    # USPTO keys first so its parsing is unchanged; EUIPO wraps rows in
    # "trademarks" and Spring-style gateways use "content".
    for key in ("results", "hits", "docs", "response", "data", "items",
                "trademarks", "content"):
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


def _dig(item: dict, *paths: str, keep_list: bool = False):
    """First non-empty value at any dotted path, list-tolerant.

    EUIPO nests the wordmark under `wordMarkSpecification.verbalElement` and
    returns applicants as a list, so the flat `_first` used for USPTO is not
    enough. Every intermediate hop tolerates a list by taking its first element.

    `keep_list` controls the final hop only. Off (the default) it unwraps, which
    is what "applicants[0].name" needs. On, the list is returned intact — needed
    for fields where the list *is* the value, like `niceClasses: [18, 25, 28]`;
    unwrapping there would report a mark as covering class 18 alone and quietly
    lose the apparel class that actually matters for POD.
    """
    for path in paths:
        cur = item
        for part in path.split("."):
            if isinstance(cur, list) and cur:
                cur = cur[0]
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(part)
        if isinstance(cur, list) and cur and not keep_list:
            cur = cur[0]
        if cur not in (None, "", [], {}):
            return cur
    return None


# --------------------------------------------------------------------------
# Public USPTO trademark search (no credential)
# --------------------------------------------------------------------------

#: Only the fields the pipeline reads. A bare query returns 78 per hit, mostly null.
_TMSEARCH_FIELDS = [
    "wordmark",
    "ownerName",
    "internationalClass",
    "statusDescription",
    "filedDate",
    "registrationId",
]

#: A class the register has already struck out, e.g. "(CANCELLED) IC 018".
#: Counting it would let a dead class stand in for a live one.
_STRUCK_CLASS = re.compile(r"CANCELLED|ABANDONED|EXPIRED", re.I)


def tmsearch_configured() -> bool:
    """No credential to check — only whether the operator left it enabled."""
    return bool(settings.uspto_tmsearch_lookup)


def _tmsearch_classes(values) -> str | None:
    """Normalise the register's mixed class notation to "018,025".

    One list carries both international ("IC 018") and legacy US ("030.")
    notation and marks struck-out classes inline, so neither a plain join nor a
    digit scrape over the raw value is safe.
    """
    if not isinstance(values, (list, tuple)):
        values = [values] if values else []
    found: set[int] = set()
    for raw in values:
        text = str(raw or "")
        if _STRUCK_CLASS.search(text):
            continue
        found |= parse_classes(text)
    return ",".join(f"{c:03d}" for c in sorted(found)) or None


def _tmsearch_records(payload) -> list[dict]:
    """Elasticsearch response shape. The serial number is the document id and
    lives outside `source`, so it has to be folded back in."""
    raw = ((payload or {}).get("hits") or {}).get("hits") or []
    out: list[dict] = []
    for hit in raw:
        if not isinstance(hit, dict):
            continue
        src = hit.get("source") or hit.get("_source") or {}
        if isinstance(src, dict):
            out.append({**src, "id": src.get("id") or hit.get("id") or hit.get("_id")})
    return out


def search_tmsearch(phrase: str, limit: int = 3) -> list[TrademarkHit]:
    """Never-raising wrapper — an unreachable register yields no hits."""
    try:
        return _search_tmsearch_raw(phrase, limit)
    except LiveLookupError as exc:
        log.info("Public USPTO search unavailable for %r: %s", phrase, exc)
        return []


def _search_tmsearch_raw(
    phrase: str, limit: int = 3, *, min_similarity: float = 82.0
) -> list[TrademarkHit]:
    """Raises LiveLookupError on transport failure; returns [] for a clean miss."""
    if not tmsearch_configured():
        return []
    norm = normalize(phrase)
    if not _is_checkable(norm):
        return []

    # `alive` is the register's own liveness flag, so filtering server-side beats
    # matching status strings after the fact. Over-fetch deliberately: a phrase
    # query ranks partial marks highly ("NIKE UNIVERSA" for "NIKE"), and those
    # have to be dropped by similarity here, not by the register.
    body = {
        "query": {
            "bool": {
                "must": [
                    {
                        "bool": {
                            "should": [
                                {"match_phrase": {"WM": {"query": norm, "boost": 5}}},
                                {"match_phrase": {"PM": {"query": norm, "boost": 2}}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                    {"term": {"alive": True}},
                ]
            }
        },
        # The register's own UI asks for 100. A prolific mark has dozens of live
        # registrations, and an on-class one has to be inside this window to be
        # picked at all — 30 was small enough to hide every class-025 STUSSY.
        "size": 100,
        "from": 0,
        # Must be true: the gateway answers 502 to track_total_hits=false, so
        # skipping the count to save work is not an option here.
        "track_total_hits": True,
        "_source": _TMSEARCH_FIELDS,
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                settings.uspto_tmsearch_url,
                json=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                raise LiveLookupError(
                    f"HTTP {resp.status_code} from {settings.uspto_tmsearch_url}"
                )
            payload = resp.json()
    except LiveLookupError:
        raise
    except Exception as exc:  # network error / malformed JSON
        raise LiveLookupError(str(exc)) from exc

    hits: list[TrademarkHit] = []
    for item in _tmsearch_records(payload):
        mark = item.get("wordmark")
        if not isinstance(mark, str) or not mark.strip():
            continue
        mark_norm = normalize(mark)
        score = fuzz.token_sort_ratio(norm, mark_norm)
        if score < min_similarity:
            continue
        if not within_edit_budget(norm, mark_norm):
            continue

        owners = item.get("ownerName")
        owner = owners[0] if isinstance(owners, list) and owners else owners
        serial = _str_or_none(item.get("id"))
        hits.append(
            TrademarkHit(
                query=phrase,
                mark_text=mark,
                similarity=round(score, 1),
                source="uspto_tmsearch",
                serial_number=serial,
                registration_number=_str_or_none(item.get("registrationId")),
                owner=_str_or_none(owner),
                status=_str_or_none(item.get("statusDescription")),
                filing_date=_str_or_none(item.get("filedDate")),
                classes=_tmsearch_classes(item.get("internationalClass")),
                url=(
                    f"https://tsdr.uspto.gov/#caseNumber={serial}"
                    "&caseType=SERIAL_NO&searchType=statusSearch"
                    if serial
                    else None
                ),
            )
        )

    hits.sort(key=_rank_key, reverse=True)
    return hits[:limit]


# --------------------------------------------------------------------------
# Live EUIPO (best effort)
# --------------------------------------------------------------------------

#: Tokens live 7200s. Refresh a minute early so a call cannot race the expiry.
_EUIPO_TOKEN_SKEW_S = 60.0

_euipo_token_lock = threading.Lock()
#: (access_token, monotonic deadline) — shared by every worker thread.
_euipo_token: tuple[str, float] | None = None


def euipo_configured() -> bool:
    return bool(
        settings.euipo_live_lookup
        and settings.euipo_client_id
        and settings.euipo_client_secret
    )


def _euipo_credentials() -> tuple[str, str]:
    cid, secret = settings.euipo_client_id, settings.euipo_client_secret
    if not (cid and secret):
        raise LiveLookupError(
            "EUIPO needs client credentials — set EUIPO_CLIENT_ID and "
            "EUIPO_CLIENT_SECRET (free: https://dev.euipo.europa.eu)"
        )
    return cid, secret


def _euipo_invalidate_token() -> None:
    global _euipo_token
    with _euipo_token_lock:
        _euipo_token = None


def _euipo_access_token() -> str:
    """OAuth2 client_credentials token, cached until shortly before expiry."""
    global _euipo_token
    cid, secret = _euipo_credentials()
    with _euipo_token_lock:
        now = time.monotonic()
        if _euipo_token and _euipo_token[1] > now:
            return _euipo_token[0]
        try:
            with httpx.Client(timeout=12) as client:
                resp = client.post(
                    settings.euipo_token_url,
                    data={"grant_type": "client_credentials", "scope": "uid"},
                    auth=(cid, secret),
                )
        except Exception as exc:  # network / DNS / TLS
            raise LiveLookupError(f"EUIPO token endpoint unreachable: {exc}") from exc

        if resp.status_code in (400, 401, 403):
            raise LiveLookupError(
                f"EUIPO rejected the credentials (HTTP {resp.status_code})"
            )
        if resp.status_code != 200:
            raise LiveLookupError(f"HTTP {resp.status_code} from EUIPO token endpoint")
        try:
            payload = resp.json()
        except Exception as exc:
            raise LiveLookupError(f"EUIPO token response was not JSON: {exc}") from exc

        token = payload.get("access_token")
        if not token:
            raise LiveLookupError("EUIPO token response carried no access_token")
        ttl = float(payload.get("expires_in") or 7200)
        _euipo_token = (token, now + max(ttl - _EUIPO_TOKEN_SKEW_S, 30.0))
        return token


def _euipo_rsql(norm: str) -> str:
    """RSQL filter for the search endpoint.

    `normalize()` has already stripped everything outside [A-Z0-9 ], so the only
    RSQL metacharacter present is the wildcard we add deliberately — there is no
    injection surface left to escape.
    """
    return f"wordMarkSpecification.verbalElement=='*{norm}*'"


def search_euipo(phrase: str, limit: int = 3) -> list[TrademarkHit]:
    """Never-raising wrapper — an unreachable register yields no hits."""
    try:
        return _search_euipo_raw(phrase, limit)
    except LiveLookupError as exc:
        log.info("Live EUIPO lookup unavailable for %r: %s", phrase, exc)
        return []


def _search_euipo_raw(
    phrase: str, limit: int = 3, *, min_similarity: float = 82.0
) -> list[TrademarkHit]:
    """Raises LiveLookupError on transport failure; returns [] for a clean miss."""
    if not settings.euipo_live_lookup:
        return []
    norm = normalize(phrase)
    if not _is_checkable(norm):
        return []

    cid, _ = _euipo_credentials()
    token = _euipo_access_token()
    url = f"{settings.euipo_api_base.rstrip('/')}/trademarks"
    # Ask for more rows than we keep: the gateway orders by its own relevance,
    # not by string similarity, so rapidfuzz needs candidates to rerank. Same
    # trade-off as the FTS `LIMIT 400` — a very common word can still push the
    # best match past the window.
    params = {"query": _euipo_rsql(norm), "size": max(limit * 5, 10)}
    headers = {
        "Authorization": f"Bearer {token}",
        "X-IBM-Client-Id": cid,
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=12) as client:
            resp = client.get(url, params=params, headers=headers)
        if resp.status_code == 401:
            # Token died mid-flight; drop it so the next design re-authenticates.
            _euipo_invalidate_token()
            raise LiveLookupError("EUIPO returned 401 — token rejected")
        if resp.status_code == 403:
            raise LiveLookupError("EUIPO returned 403 — app not subscribed to the search API")
        if resp.status_code == 404:
            raise LiveLookupError(
                f"HTTP 404 from {url} — check EUIPO_API_BASE, the gateway path has moved before"
            )
        if resp.status_code == 429:
            raise LiveLookupError("EUIPO rate limit reached (HTTP 429)")
        if resp.status_code != 200:
            raise LiveLookupError(f"HTTP {resp.status_code} from {url}")
        payload = resp.json()
    except LiveLookupError:
        raise
    except Exception as exc:  # network error / malformed JSON
        raise LiveLookupError(str(exc)) from exc

    hits: list[TrademarkHit] = []
    for item in _iter_live_records(payload):
        mark = _dig(item, "wordMarkSpecification.verbalElement", "verbalElement", "markName")
        if not isinstance(mark, str) or not mark.strip():
            continue
        mark_norm = normalize(mark)
        score = fuzz.token_sort_ratio(norm, mark_norm)
        if score < min_similarity:
            continue
        if not within_edit_budget(norm, mark_norm):
            continue

        status = _str_or_none(_dig(item, "status", "markStatus")) or ""
        if status and not any(s in status.lower() for s in EUIPO_LIVE_STATUSES):
            continue

        app_no = _str_or_none(_dig(item, "applicationNumber", "applicationNo", "id"))
        classes = _dig(
            item, "niceClasses", "classDescriptionDetails.classNumber", keep_list=True
        )
        if isinstance(classes, (list, tuple)):
            classes = ", ".join(str(c) for c in classes)

        hits.append(
            TrademarkHit(
                query=phrase,
                mark_text=mark,
                similarity=round(score, 1),
                source="euipo_api",
                # EUIPO has no serial/registration split like USPTO: the
                # application number is the citable identifier throughout.
                serial_number=app_no,
                registration_number=_str_or_none(_dig(item, "registrationNumber")),
                owner=_str_or_none(
                    _dig(item, "applicants.name", "applicants.fullName", "applicantName", "owner")
                ),
                status=status or None,
                filing_date=_str_or_none(
                    _dig(item, "applicationDate", "filingDate", "receivedDate")
                ),
                classes=_str_or_none(classes),
                url=(
                    f"https://euipo.europa.eu/eSearch/#details/trademarks/{app_no}"
                    if app_no
                    else None
                ),
            )
        )

    hits.sort(key=_rank_key, reverse=True)
    return hits[:limit]


# --------------------------------------------------------------------------
# Facade
# --------------------------------------------------------------------------


#: Live lookups are one HTTP round-trip each, so a 100-phrase design would take
#: minutes. The local index has no such cost and stays uncapped.
MAX_LIVE_LOOKUPS = 12
#: After this many consecutive live failures, stop trying for the rest of the design.
LIVE_FAILURE_BUDGET = 3
#: Phrases checked at once. The lookups are pure network waits — measured at
#: ~1.2 s each, so five candidates cost 6.1 s in series and about 1.3 s at this
#: width. Kept small on purpose: these are free public registers and there is no
#: reason to open a dozen sockets at a register to save a fraction of a second.
LOOKUP_CONCURRENCY = 6


def _live_registers(markets: list[str]) -> list[tuple[str, object]]:
    """Which live registers apply to this design's markets.

    Market-gated on purpose: USPTO cannot speak for the EU register and EUIPO
    cannot speak for the US one, so calling both for every design would spend
    quota to produce evidence that does not apply to where the design sells.

    UK is deliberately absent. Post-Brexit UK marks left the EU register, so an
    EUIPO hit is not authority for a UK listing — that needs UKIPO, which is not
    wired up yet.
    """
    registers: list[tuple[str, object]] = []
    if "US" in markets:
        # Keyless first: it needs no credential and returns the Nice classes the
        # keyed Open Data Portal endpoint omits, so its hits can be class-checked
        # instead of being taken at face value.
        if tmsearch_configured():
            registers.append(("USPTO-public", _search_tmsearch_raw))
        if settings.uspto_live_lookup:
            registers.append(("USPTO", _search_live_raw))
    if euipo_configured() and "EU" in markets:
        registers.append(("EUIPO", _search_euipo_raw))
    return registers


def check(phrases: list[str], *, markets: list[str]) -> list[TrademarkHit]:
    """Check candidate phrases against every configured register. Deduped.

    Phrases are checked concurrently: each lookup is a network wait, so doing
    them one after another made the register step the second-largest cost in the
    pipeline. The per-register budgets stay shared and lock-guarded, so a wide
    fan-out still cannot spend more of a register's allowance than the serial
    version would have.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[TrademarkHit] = []

    registers = _live_registers(markets)
    if not registers:
        return out

    # Per-register budgets: one register being down must not consume the other's
    # allowance, or a USPTO outage would silently disable the EU check too.
    calls: dict[str, int] = {name: 0 for name, _ in registers}
    errors: dict[str, int] = {name: 0 for name, _ in registers}
    budget_lock = threading.Lock()

    def _claim(name: str) -> bool:
        """Reserve one call against a register, or refuse if it is spent."""
        with budget_lock:
            if calls[name] >= MAX_LIVE_LOOKUPS or errors[name] >= LIVE_FAILURE_BUDGET:
                return False
            calls[name] += 1
            return True

    def _for_phrase(phrase: str) -> list[TrademarkHit]:
        for name, lookup in registers:
            if not _claim(name):
                continue
            try:
                live = lookup(phrase)
            except LiveLookupError as exc:
                # An empty result is a legitimate "no such mark"; only transport
                # failures count against the budget.
                with budget_lock:
                    errors[name] += 1
                log.info("Live %s lookup failed for %r: %s", name, phrase, exc)
                continue
            if live:
                return live
        return []

    unique = list(dict.fromkeys(p.strip() for p in phrases if p and p.strip()))
    width = min(LOOKUP_CONCURRENCY, len(unique)) or 1
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=width, thread_name_prefix="tm-lookup"
    ) as pool:
        # Keep the submission order so dedup and the final ordering stay stable.
        results = list(pool.map(_for_phrase, unique))

    for found in results:
        for hit in found:
            # Source is part of the key: a USPTO serial and an EUIPO application
            # number are numbered independently, so a bare number could collide
            # across registers and silently drop a real second-register hit.
            key = (hit.source, normalize(hit.query), hit.serial_number or hit.mark_text)
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)

    out.sort(key=_rank_key, reverse=True)
    return out
