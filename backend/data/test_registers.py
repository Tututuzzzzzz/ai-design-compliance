"""Offline checks for the live trademark registers (USPTO + EUIPO).

The register code cannot be exercised for real without credentials, and a live
call would be non-deterministic anyway. So the HTTP layer is stubbed and what
gets asserted is the part that is ours: RSQL construction, response parsing,
status filtering, token caching, market gating, per-register budgets, and the
provenance stamped onto the resulting evidence.

    python -m data.test_registers

No API key and no network required.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    Finding,
    RiskCategory,
    Severity,
)
from app.pipeline import trademark, verdict  # noqa: E402

FAILURES: list[str] = []


def check(label: str, actual, expected) -> None:
    ok = actual == expected
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        print(f"       expected {expected!r}\n       actual   {actual!r}")
        FAILURES.append(label)


def check_true(label: str, value) -> None:
    check(label, bool(value), True)


# ---------------------------------------------------------------------------
# HTTP stub
# ---------------------------------------------------------------------------


class StubClient:
    """Stands in for httpx.Client, recording calls and replaying canned responses."""

    calls: list[tuple[str, str, dict]] = []
    token_responses: list[tuple[int, dict]] = []
    search_responses: list[tuple[int, dict]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.token_responses = []
        cls.search_responses = []

    def _respond(self, queue: list[tuple[int, dict]], url: str) -> httpx.Response:
        status, payload = queue.pop(0) if queue else (200, {})
        return httpx.Response(
            status_code=status,
            json=payload,
            request=httpx.Request("GET", url),
        )

    def post(self, url, **kwargs):
        type(self).calls.append(("POST", url, kwargs))
        return self._respond(type(self).token_responses, url)

    def get(self, url, **kwargs):
        type(self).calls.append(("GET", url, kwargs))
        return self._respond(type(self).search_responses, url)


TOKEN_OK = (200, {"access_token": "tok-abc", "expires_in": 7200})

# Shape modelled on the documented EUIPO search response: rows under
# "trademarks", wordmark nested in wordMarkSpecification, applicants as a list.
EUIPO_PAGE = (
    200,
    {
        "trademarks": [
            {
                "applicationNumber": "018123456",
                "status": "REGISTERED",
                "wordMarkSpecification": {"verbalElement": "JUST DO IT"},
                "applicants": [{"name": "Nike Innovate C.V."}],
                "applicationDate": "2019-11-04",
                "niceClasses": [18, 25, 28],
            },
            {
                # Dead mark: must be filtered out even though the text matches.
                "applicationNumber": "018999999",
                "status": "CANCELLED",
                "wordMarkSpecification": {"verbalElement": "JUST DO IT"},
                "applicants": [{"name": "Someone Else"}],
            },
            {
                # Unrelated text: must fall below the similarity threshold.
                "applicationNumber": "018777777",
                "status": "REGISTERED",
                "wordMarkSpecification": {"verbalElement": "GARDEN HOSE REEL"},
            },
        ]
    },
)


def with_euipo_credentials() -> None:
    settings.euipo_live_lookup = True
    settings.euipo_client_id = "client-123"
    settings.euipo_client_secret = "secret-456"
    trademark._euipo_invalidate_token()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_normalize_folds_accents_but_not_status_symbols() -> None:
    print("\nText normalisation")
    n = trademark.normalize

    # Accents must fold to the base letter. Before this, "STÜSSY" normalised to
    # "ST SSY" and scored 50 against the registered "STUSSY" — under the 82.0
    # threshold, so a real streetwear mark was silently missed.
    check("umlaut folds", n("Stüssy"), "STUSSY")
    check("acute folds", n("Pokémon"), "POKEMON")
    check("cedilla folds", n("Marithé + François Girbaud"), "MARITHE FRANCOIS GIRBAUD")

    # ...but the NFKD fold expands ™ into the letters "TM", so status symbols
    # have to be removed first or "LEVI'S™" becomes "LEVI STM".
    check("trademark symbol dropped, not expanded", n("Levi's™"), "LEVI S")
    check("service mark symbol dropped", n("Supreme℠"), "SUPREME")
    check("registered symbol dropped", n("Nike®"), "NIKE")
    check("copyright symbol dropped", n("Disney©"), "DISNEY")

    # Existing behaviour that must not regress.
    check("heart becomes a word", n("I ❤ NY"), "I HEART NY")
    check("ampersand becomes AND", n("Ben & Jerry's"), "BEN AND JERRY S")
    check("punctuation splits tokens", n("AC/DC"), "AC DC")


def test_rsql_is_built_from_normalised_text() -> None:
    print("\nRSQL construction")
    check(
        "wildcard + normalised text",
        trademark._euipo_rsql(trademark.normalize("Just Do It")),
        "wordMarkSpecification.verbalElement=='*JUST DO IT*'",
    )
    check(
        "ampersand and heart normalise before the query is built",
        trademark._euipo_rsql(trademark.normalize("I ❤ NY & Co.")),
        "wordMarkSpecification.verbalElement=='*I HEART NY AND CO*'",
    )
    # normalize() strips everything outside [A-Z0-9 ], so a quote cannot escape
    # the RSQL string literal.
    check(
        "quote characters cannot break out of the literal",
        "'" in trademark._euipo_rsql(trademark.normalize("O'Neill's \"brand\""))[:-1].replace(
            "wordMarkSpecification.verbalElement=='", ""
        ),
        False,
    )


def test_euipo_parses_and_filters() -> None:
    print("\nEUIPO response parsing")
    with_euipo_credentials()
    StubClient.reset()
    StubClient.token_responses = [TOKEN_OK]
    StubClient.search_responses = [EUIPO_PAGE]

    hits = trademark._search_euipo_raw("Just Do It")

    check("one live match survives filtering", len(hits), 1)
    if not hits:
        return
    hit = hits[0]
    check("mark text from nested wordMarkSpecification", hit.mark_text, "JUST DO IT")
    check("source is euipo_api", hit.source, "euipo_api")
    check("owner from applicants list", hit.owner, "Nike Innovate C.V.")
    check("application number as identifier", hit.serial_number, "018123456")
    check("nice classes joined", hit.classes, "18, 25, 28")
    check("filing date", hit.filing_date, "2019-11-04")
    check(
        "eSearch URL is citable",
        hit.url,
        "https://euipo.europa.eu/eSearch/#details/trademarks/018123456",
    )
    check("similarity is 100 for an exact match", hit.similarity, 100.0)

    search_calls = [c for c in StubClient.calls if c[0] == "GET"]
    check("exactly one search request", len(search_calls), 1)
    if search_calls:
        params = search_calls[0][2]["params"]
        headers = search_calls[0][2]["headers"]
        check(
            "RSQL sent as query param",
            params["query"],
            "wordMarkSpecification.verbalElement=='*JUST DO IT*'",
        )
        check_true("over-fetches rows to give rapidfuzz candidates", params["size"] >= 10)
        check("bearer token attached", headers["Authorization"], "Bearer tok-abc")
        check("client id travels as X-IBM-Client-Id", headers["X-IBM-Client-Id"], "client-123")


def test_token_is_cached_then_invalidated_on_401() -> None:
    print("\nToken lifecycle")
    with_euipo_credentials()
    StubClient.reset()
    StubClient.token_responses = [TOKEN_OK]
    StubClient.search_responses = [EUIPO_PAGE, EUIPO_PAGE]

    trademark._search_euipo_raw("Just Do It")
    trademark._search_euipo_raw("Just Do It")
    token_calls = [c for c in StubClient.calls if c[0] == "POST"]
    check("second lookup reuses the cached token", len(token_calls), 1)

    # A 401 mid-flight must drop the cached token so the next call re-authenticates.
    StubClient.reset()
    StubClient.token_responses = [TOKEN_OK]
    StubClient.search_responses = [(401, {})]
    raised = False
    try:
        trademark._search_euipo_raw("Just Do It")
    except trademark.LiveLookupError:
        raised = True
    check("401 surfaces as LiveLookupError", raised, True)
    check("cached token was dropped", trademark._euipo_token, None)


def test_transport_failure_degrades_not_raises() -> None:
    print("\nFailure handling")
    with_euipo_credentials()
    StubClient.reset()
    StubClient.token_responses = [TOKEN_OK]
    StubClient.search_responses = [(500, {})]
    check("search_euipo swallows a 5xx", trademark.search_euipo("Just Do It"), [])

    settings.euipo_client_id = None
    settings.euipo_client_secret = None
    trademark._euipo_invalidate_token()
    StubClient.reset()
    check("missing credentials yield no hits, not a crash", trademark.search_euipo("Just Do It"), [])
    check("no HTTP call attempted without credentials", StubClient.calls, [])


def test_market_gating() -> None:
    print("\nMarket gating")
    with_euipo_credentials()
    settings.uspto_live_lookup = True
    settings.uspto_tmsearch_lookup = True

    names = lambda markets: [n for n, _ in trademark._live_registers(markets)]  # noqa: E731
    # The keyless public search comes first: it needs no credential and returns
    # the Nice classes the keyed endpoint omits.
    check("US market uses the USPTO registers only", names(["US"]), ["USPTO-public", "USPTO"])
    check("EU market uses EUIPO only", names(["EU"]), ["EUIPO"])
    check("US+EU uses all three", names(["US", "EU"]), ["USPTO-public", "USPTO", "EUIPO"])
    check("JP market uses neither (no register wired up)", names(["JP"]), [])
    # Post-Brexit UK marks are not on the EU register, so an EUIPO hit is not
    # authority for a UK listing.
    check("UK does not silently borrow the EU register", names(["UK"]), [])

    settings.euipo_client_id = None
    trademark._euipo_invalidate_token()
    check(
        "EUIPO drops out when unconfigured",
        names(["US", "EU"]),
        ["USPTO-public", "USPTO"],
    )

    settings.uspto_tmsearch_lookup = False
    check("public USPTO search drops out when disabled", names(["US"]), ["USPTO"])
    settings.uspto_live_lookup = False
    check("no US register left when both are off", names(["US"]), [])
    settings.uspto_tmsearch_lookup = True
    settings.uspto_live_lookup = True


def test_per_register_budget_is_independent() -> None:
    print("\nPer-register budgets")
    with_euipo_credentials()
    settings.uspto_live_lookup = True
    settings.uspto_api_key = "uspto-key"

    calls = {"USPTO": 0, "EUIPO": 0}

    def failing_uspto(phrase, *_a, **_k):
        calls["USPTO"] += 1
        raise trademark.LiveLookupError("simulated USPTO outage")

    def working_euipo(phrase, *_a, **_k):
        calls["EUIPO"] += 1
        return [
            trademark.TrademarkHit(
                query=phrase,
                mark_text=phrase.upper(),
                similarity=100.0,
                source="euipo_api",
                serial_number=f"018{calls['EUIPO']:06d}",
            )
        ]

    original = trademark._live_registers
    trademark._live_registers = lambda markets: [
        ("USPTO", failing_uspto),
        ("EUIPO", working_euipo),
    ]
    try:
        phrases = [f"phrase number {i}" for i in range(8)]
        hits = trademark.check(phrases, markets=["US", "EU"])
    finally:
        trademark._live_registers = original

    # USPTO stops after its failure budget; EUIPO must still be consulted for
    # every phrase rather than being starved by the other register's outage.
    check("USPTO stops at its failure budget", calls["USPTO"], trademark.LIVE_FAILURE_BUDGET)
    check("EUIPO still checked for every phrase", calls["EUIPO"], len(phrases))
    check("all EUIPO hits returned", len(hits), len(phrases))


def test_evidence_records_the_real_register() -> None:
    print("\nEvidence provenance")
    euipo_hit = trademark.TrademarkHit(
        query="JUST DO IT",
        mark_text="JUST DO IT",
        similarity=100.0,
        source="euipo_api",
        serial_number="018123456",
        owner="Nike Innovate C.V.",
        status="REGISTERED",
    )
    check("EUIPO hit is labelled euipo_api", verdict._hit_evidence(euipo_hit).source, "euipo_api")

    public_hit = trademark.TrademarkHit(
        query="JUST DO IT",
        mark_text="JUST DO IT",
        similarity=100.0,
        source="uspto_tmsearch",
        classes="018,025",
    )
    public_evidence = verdict._hit_evidence(public_hit)
    check("public USPTO hit keeps its label", public_evidence.source, "uspto_tmsearch")
    check("on-class hit is flagged as covering these goods", public_evidence.covers_goods, True)

    off_class_hit = trademark.TrademarkHit(
        query="SUPREME", mark_text="SUPREME", similarity=100.0, source="uspto_tmsearch",
        classes="012",
    )
    check(
        "off-class hit is flagged as not covering these goods",
        verdict._hit_evidence(off_class_hit).covers_goods,
        False,
    )

    no_class_hit = trademark.TrademarkHit(
        query="SUPREME", mark_text="SUPREME", similarity=100.0, source="uspto_live_api"
    )
    check(
        "a register that returns no classes stays unknown, not off-class",
        verdict._hit_evidence(no_class_hit).covers_goods,
        None,
    )

    live_hit = trademark.TrademarkHit(
        query="JUST DO IT", mark_text="JUST DO IT", similarity=100.0, source="uspto_live_api"
    )
    check(
        "live USPTO hit keeps its label",
        verdict._hit_evidence(live_hit).source,
        "uspto_live_api",
    )

    # An EUIPO hit must satisfy the register requirement in cap_unverified_phrases,
    # otherwise a confirmed EU mark would be capped at MEDIUM as if unverified.
    finding = Finding(
        category=RiskCategory.TRADEMARKED_PHRASE,
        title="JUST DO IT",
        description="registered slogan",
        severity=Severity.HIGH,
        confidence=0.95,
        remediation="remove the slogan",
        evidence=[verdict._hit_evidence(euipo_hit)],
    )
    capped = verdict.cap_unverified_phrases([finding])
    check("EUIPO evidence counts as register confirmation", capped[0].severity, Severity.HIGH)


def main() -> int:
    real_client = httpx.Client
    httpx.Client = StubClient  # type: ignore[assignment]
    try:
        test_normalize_folds_accents_but_not_status_symbols()
        test_rsql_is_built_from_normalised_text()
        test_euipo_parses_and_filters()
        test_token_is_cached_then_invalidated_on_401()
        test_transport_failure_degrades_not_raises()
        test_market_gating()
        test_per_register_budget_is_independent()
        test_evidence_records_the_real_register()
    finally:
        httpx.Client = real_client  # type: ignore[assignment]
        trademark._euipo_invalidate_token()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print("all register checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
