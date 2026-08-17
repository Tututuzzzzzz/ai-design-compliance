"""Market and platform policy layer.

The vision model judges the artwork; this module judges the *listing context*.
The same skull design is fine on Shopify and rejected on Amazon Merch, and a
parody that survives US fair-use analysis has no equivalent defence in the EU.
Each rule cites the published policy it comes from so reviewers can verify it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Finding, RiskCategory, Severity

_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def escalate(severity: Severity, steps: int = 1) -> Severity:
    idx = min(len(_ORDER) - 1, _ORDER.index(severity) + steps)
    return _ORDER[idx]


def rank(severity: Severity) -> int:
    return _ORDER.index(severity)


@dataclass(frozen=True)
class PlatformPolicy:
    key: str
    name: str
    source: str
    # Categories the platform is unusually strict about → escalate one step.
    strict_categories: tuple[RiskCategory, ...] = ()
    # Keywords in a prohibited-content finding that this platform outright bans.
    banned_keywords: tuple[str, ...] = ()
    note: str = ""


PLATFORMS: dict[str, PlatformPolicy] = {
    "etsy": PlatformPolicy(
        key="etsy",
        name="Etsy",
        source="https://www.etsy.com/legal/prohibited/",
        strict_categories=(
            RiskCategory.COPYRIGHTED_CHARACTER,
            RiskCategory.BRAND_LOGO,
            RiskCategory.TRADEMARKED_PHRASE,
        ),
        banned_keywords=("firearm", "gun", "weapon", "drug", "hate", "explicit"),
        note="Etsy runs an active IP takedown programme; repeat notices close shops.",
    ),
    "amazon_merch": PlatformPolicy(
        key="amazon_merch",
        name="Amazon Merch on Demand",
        source="https://merch.amazon.com/resource/201858630",
        strict_categories=(
            RiskCategory.COPYRIGHTED_CHARACTER,
            RiskCategory.BRAND_LOGO,
            RiskCategory.TRADEMARKED_PHRASE,
            RiskCategory.PUBLIC_FIGURE,
            RiskCategory.PROHIBITED_CONTENT,
        ),
        banned_keywords=(
            "firearm", "gun", "weapon", "knife", "drug", "cannabis", "alcohol",
            "tobacco", "hate", "explicit", "nudity", "violence",
        ),
        note="Merch on Demand suspends accounts on a single confirmed IP violation.",
    ),
    "tiktok_shop": PlatformPolicy(
        key="tiktok_shop",
        name="TikTok Shop",
        source="https://seller-us.tiktok.com/university/essay?knowledge_id=10004142",
        strict_categories=(
            RiskCategory.BRAND_LOGO,
            RiskCategory.PUBLIC_FIGURE,
            RiskCategory.PROHIBITED_CONTENT,
        ),
        banned_keywords=(
            "firearm", "gun", "weapon", "knife", "drug", "cannabis", "tobacco",
            "alcohol", "explicit", "nudity", "hate", "self-harm",
        ),
        note="TikTok Shop enforces weapons and regulated-goods policies automatically.",
    ),
    "shopify": PlatformPolicy(
        key="shopify",
        name="Shopify",
        source="https://www.shopify.com/legal/aup",
        strict_categories=(),
        banned_keywords=("hate", "explicit", "self-harm"),
        note="Shopify is the seller's own storefront: liability sits with the merchant, "
        "not a marketplace reviewer.",
    ),
    "redbubble": PlatformPolicy(
        key="redbubble",
        name="Redbubble",
        source="https://help.redbubble.com/hc/en-us/articles/201579195",
        strict_categories=(
            RiskCategory.COPYRIGHTED_CHARACTER,
            RiskCategory.BRAND_LOGO,
            RiskCategory.TRADEMARKED_PHRASE,
        ),
        banned_keywords=("hate", "explicit"),
        note="Redbubble auto-removes listings on rights-holder keyword matches.",
    ),
}


@dataclass(frozen=True)
class MarketPolicy:
    key: str
    name: str
    source: str
    note: str
    strict_categories: tuple[RiskCategory, ...] = ()


MARKETS: dict[str, MarketPolicy] = {
    "US": MarketPolicy(
        key="US",
        name="United States",
        source="https://www.uspto.gov/trademarks",
        note="US recognises fair use and parody defences, and publicity rights vary by state.",
    ),
    "EU": MarketPolicy(
        key="EU",
        name="European Union",
        source="https://euipo.europa.eu/",
        note="No general parody/fair-use defence for merchandise; EUIPO marks cover all "
        "member states at once.",
        strict_categories=(
            RiskCategory.COPYRIGHTED_CHARACTER,
            RiskCategory.BRAND_LOGO,
            RiskCategory.COPYRIGHTED_ARTWORK,
        ),
    ),
    "UK": MarketPolicy(
        key="UK",
        name="United Kingdom",
        source="https://www.gov.uk/topic/intellectual-property/trade-marks",
        note="Post-Brexit UK marks are separate from EUIPO; parody is narrowly defined.",
        strict_categories=(RiskCategory.BRAND_LOGO,),
    ),
    "JP": MarketPolicy(
        key="JP",
        name="Japan",
        source="https://www.jpo.go.jp/e/",
        note="Anime and manga rights are aggressively enforced by Japanese rights holders.",
        strict_categories=(
            RiskCategory.COPYRIGHTED_CHARACTER,
            RiskCategory.COPYRIGHTED_ARTWORK,
        ),
    ),
}


def resolve_platforms(keys: list[str]) -> list[PlatformPolicy]:
    return [PLATFORMS[k.lower()] for k in keys if k.lower() in PLATFORMS]


def resolve_markets(keys: list[str]) -> list[MarketPolicy]:
    return [MARKETS[k.upper()] for k in keys if k.upper() in MARKETS]


def apply(
    findings: list[Finding], platforms: list[str], markets: list[str]
) -> tuple[list[Finding], list[str]]:
    """Escalate severities per policy. Returns (adjusted findings, notes)."""
    plats = resolve_platforms(platforms)
    mkts = resolve_markets(markets)
    notes: list[str] = []

    for f in findings:
        # Escalate ONCE per axis, not once per selected platform. Selling on both
        # Etsy and Amazon Merch does not make a design twice as infringing — it
        # means the strictest of the two governs. Compounding here would turn a
        # medium finding into a critical one purely by ticking more checkboxes.
        strict_plats = [
            p
            for p in plats
            if f.category in p.strict_categories and rank(f.severity) >= rank(Severity.MEDIUM)
        ]
        if strict_plats:
            old = f.severity
            f.severity = escalate(f.severity)
            if f.severity != old:
                names = ", ".join(p.name for p in strict_plats)
                notes.append(
                    f"{names} treat {f.category.value.replace('_', ' ')} as a "
                    f"zero-tolerance category — severity raised {old.value} → "
                    f"{f.severity.value}. Policy: {strict_plats[0].source}"
                )

        if f.category is RiskCategory.PROHIBITED_CONTENT:
            haystack = f"{f.title} {f.description}".lower()
            banning = {
                p.name: sorted({k for k in p.banned_keywords if k in haystack}) for p in plats
            }
            banning = {name: kws for name, kws in banning.items() if kws}
            if banning:
                old = f.severity
                f.severity = escalate(f.severity)
                summary = "; ".join(f"{n} ({', '.join(k)})" for n, k in banning.items())
                notes.append(
                    f"Prohibited-goods policy hit — {summary}. "
                    f"Severity raised {old.value} → {f.severity.value}."
                )

        strict_mkts = [
            m
            for m in mkts
            if f.category in m.strict_categories and rank(f.severity) >= rank(Severity.MEDIUM)
        ]
        if strict_mkts:
            old = f.severity
            f.severity = escalate(f.severity)
            if f.severity != old:
                notes.append(
                    f"{', '.join(m.name for m in strict_mkts)}: {strict_mkts[0].note} "
                    f"Severity raised {old.value} → {f.severity.value}."
                )

    for p in plats:
        if p.note:
            notes.append(f"{p.name}: {p.note}")

    # Preserve order, drop duplicates.
    return findings, list(dict.fromkeys(notes))
