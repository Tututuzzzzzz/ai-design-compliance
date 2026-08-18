"""Deterministic verdict engine.

The vision model produces evidence; this module produces the decision. Keeping
the decision in plain code (rather than asking the model for a verdict) means
the same evidence always yields the same verdict, and the reasoning we print is
the actual rule that fired.
"""

from __future__ import annotations

from ..models import Evidence, Finding, RiskCategory, Severity, Verdict
from .i18n import DEFAULT_LANG, Lang, t
from .i18n import category as category_label
from .i18n import severity as severity_label
from .i18n import verdict as verdict_label
from .rules import rank
from .trademark import TrademarkHit

# A live registration this similar to on-garment text is a decision, not a hint.
TM_BLOCK_SIMILARITY = 95.0
TM_RISK_SIMILARITY = 85.0

# Vision confidence below this is a lead for a human, never an auto-block.
BLOCK_MIN_CONFIDENCE = 0.75


def merge_trademark_hits(
    findings: list[Finding], hits: list[TrademarkHit], lang: Lang = DEFAULT_LANG
) -> list[Finding]:
    """Attach register evidence to text findings, and raise new ones for OCR text
    the model did not flag but the register matches."""
    remaining = list(hits)

    for f in findings:
        needle = (f.matched_text or f.title or "").strip().lower()
        if not needle:
            continue
        matched = [h for h in remaining if h.query.strip().lower() == needle]
        for hit in matched:
            remaining.remove(hit)
            f.evidence.append(_hit_evidence(hit, lang))
            if hit.similarity >= TM_BLOCK_SIMILARITY and rank(f.severity) < rank(Severity.HIGH):
                f.severity = Severity.HIGH
            f.confidence = max(f.confidence, min(0.99, hit.similarity / 100))
            if not f.rights_holder and hit.owner:
                f.rights_holder = hit.owner

    for hit in remaining:
        if hit.similarity < TM_RISK_SIMILARITY:
            continue
        severity = (
            Severity.HIGH if hit.similarity >= TM_BLOCK_SIMILARITY else Severity.MEDIUM
        )
        findings.append(
            Finding(
                category=RiskCategory.TRADEMARKED_PHRASE,
                title=t("tm.title", lang, query=hit.query, mark=hit.mark_text),
                description=t(
                    "tm.description",
                    lang,
                    query=hit.query,
                    mark=hit.mark_text,
                    similarity=hit.similarity,
                    owner=t("tm.owner_suffix", lang, owner=hit.owner) if hit.owner else "",
                    status=t("tm.status_suffix", lang, status=hit.status) if hit.status else "",
                ),
                severity=severity,
                confidence=min(0.99, hit.similarity / 100),
                rights_holder=hit.owner,
                matched_text=hit.query,
                location_hint=t("tm.location_hint", lang),
                evidence=[_hit_evidence(hit, lang)],
                remediation=t("tm.remediation", lang, query=hit.query),
            )
        )

    return findings


def _hit_evidence(hit: TrademarkHit, lang: Lang = DEFAULT_LANG) -> Evidence:
    bits = [t("hit.match", lang, mark=hit.mark_text, similarity=hit.similarity)]
    if hit.status:
        bits.append(t("hit.status", lang, status=hit.status))
    if hit.owner:
        bits.append(t("hit.owner", lang, owner=hit.owner))
    if hit.classes:
        bits.append(t("hit.classes", lang, classes=hit.classes))
    return Evidence(
        source="uspto_local_index" if hit.source == "uspto_local_index" else "uspto_live_api",
        detail="; ".join(bits),
        url=hit.url,
        reference_id=hit.registration_number or hit.serial_number,
    )


#: Register sources that can confirm a phrase really is registered.
_REGISTER_SOURCES = {"uspto_local_index", "uspto_live_api", "euipo_api"}


def cap_unverified_phrases(
    findings: list[Finding], lang: Lang = DEFAULT_LANG
) -> list[Finding]:
    """An unattributed phrase is a guess; an attributed one is a claim.

    Vision models will confidently label ordinary shirt text ("DOG MOM",
    "NURSE LIFE") as a registered slogan. For every other category the model is
    the right authority — it can see a Mickey silhouette — but a bare phrase
    carries no such visual proof.

    The discriminator is whether the model could name the owner. "Just Do It →
    Nike" and "Got Back Tour → Paul McCartney" are specific, checkable claims
    about a real rights holder, and blocking on them is correct. "DOG MOM" with
    no owner named is the model pattern-matching on capital letters, and must not
    reach a blocking severity on its own.

    So: cap at MEDIUM only when no register confirmed it AND no rights holder was
    named. Capping on register evidence alone would turn most genuine slogan
    infringements into RISKY whenever the index is not built.
    """
    for f in findings:
        if f.category is not RiskCategory.TRADEMARKED_PHRASE:
            continue
        if any(e.source in _REGISTER_SOURCES for e in f.evidence):
            continue
        if (f.rights_holder or "").strip():
            continue
        if rank(f.severity) <= rank(Severity.MEDIUM):
            continue

        f.severity = Severity.MEDIUM
        f.confidence = min(f.confidence, 0.6)
        f.description += t("cap.note", lang)
        f.evidence.append(Evidence(source="policy_rule", detail=t("cap.evidence", lang)))
    return findings


def decide(
    findings: list[Finding], lang: Lang = DEFAULT_LANG
) -> tuple[Verdict, int, str]:
    """Returns (verdict, confidence 0-100, reasoning)."""
    if not findings:
        return Verdict.SAFE, 88, t("reason.clean", lang)

    criticals = [f for f in findings if f.severity is Severity.CRITICAL]
    highs = [f for f in findings if f.severity is Severity.HIGH]
    mediums = [f for f in findings if f.severity is Severity.MEDIUM]
    lows = [f for f in findings if f.severity is Severity.LOW]

    confident_criticals = [f for f in criticals if f.confidence >= BLOCK_MIN_CONFIDENCE]
    confident_highs = [f for f in highs if f.confidence >= BLOCK_MIN_CONFIDENCE]

    if confident_criticals:
        top = max(confident_criticals, key=lambda f: f.confidence)
        return (
            Verdict.BLOCKED,
            _confidence(Verdict.BLOCKED, findings, top),
            _explain(
                Verdict.BLOCKED,
                t("headline.blocked.critical", lang, title=top.title),
                findings,
                lang,
            ),
        )

    if len(confident_highs) >= 2 or (confident_highs and mediums):
        top = max(confident_highs, key=lambda f: f.confidence)
        return (
            Verdict.BLOCKED,
            _confidence(Verdict.BLOCKED, findings, top),
            _explain(
                Verdict.BLOCKED,
                t("headline.blocked.multiple", lang, title=top.title),
                findings,
                lang,
            ),
        )

    if confident_highs:
        top = confident_highs[0]
        return (
            Verdict.BLOCKED,
            _confidence(Verdict.BLOCKED, findings, top),
            _explain(
                Verdict.BLOCKED,
                t("headline.blocked.single", lang, title=top.title),
                findings,
                lang,
            ),
        )

    if highs or criticals:
        top = max(highs + criticals, key=lambda f: f.confidence)
        return (
            Verdict.RISKY,
            _confidence(Verdict.RISKY, findings, top),
            _explain(
                Verdict.RISKY,
                t(
                    "headline.risky.low_confidence",
                    lang,
                    confidence=f"{top.confidence:.0%}",
                    title=top.title,
                ),
                findings,
                lang,
            ),
        )

    if mediums:
        top = max(mediums, key=lambda f: f.confidence)
        return (
            Verdict.RISKY,
            _confidence(Verdict.RISKY, findings, top),
            _explain(
                Verdict.RISKY,
                t("headline.risky.reviewable", lang, title=top.title),
                findings,
                lang,
            ),
        )

    top = lows[0]
    return (
        Verdict.SAFE,
        _confidence(Verdict.SAFE, findings, top),
        _explain(Verdict.SAFE, t("headline.safe.low_only", lang), findings, lang),
    )


def _confidence(verdict: Verdict, findings: list[Finding], top: Finding) -> int:
    base = {Verdict.BLOCKED: 78, Verdict.RISKY: 62, Verdict.SAFE: 80}[verdict]
    score = base + int(top.confidence * 18)

    # Register-backed evidence is objective; it earns a real bump.
    if any(
        e.source in ("uspto_local_index", "uspto_live_api", "euipo_api")
        for f in findings
        for e in f.evidence
    ):
        score += 8

    # Agreement between several findings raises confidence in the call.
    if verdict is Verdict.BLOCKED and len([f for f in findings if rank(f.severity) >= 2]) > 1:
        score += 4

    return max(35, min(99, score))


def _explain(
    verdict_value: Verdict, headline: str, findings: list[Finding], lang: Lang
) -> str:
    lines = [
        t("explain.header", lang, verdict=verdict_label(verdict_value.value, lang), headline=headline)
    ]
    lines.append(t("explain.count", lang, count=len(findings)))
    for f in sorted(findings, key=lambda x: -rank(x.severity)):
        where = f.location_hint or (
            t("explain.box_at", lang, x=f"{f.bbox.x:.2f}", y=f"{f.bbox.y:.2f}")
            if f.bbox
            else t("explain.no_location", lang)
        )
        holder = (
            t("explain.holder", lang, holder=f.rights_holder) if f.rights_holder else ""
        )
        cites = "; ".join(
            e.reference_id or e.detail for e in f.evidence if e.source != "vision_model"
        )
        cite = t("explain.cite", lang, cites=cites) if cites else ""
        lines.append(
            t(
                "explain.item",
                lang,
                severity=severity_label(f.severity.value, lang),
                category=category_label(f.category.value, lang),
                title=f.title,
                where=where,
                confidence=f"{f.confidence:.0%}",
                holder=holder,
                cite=cite,
                remediation=f.remediation,
            )
        )
    return "\n".join(lines)


def summarize(
    verdict_value: Verdict, findings: list[Finding], lang: Lang = DEFAULT_LANG
) -> str:
    if not findings:
        return t("summary.clean", lang)
    cats = sorted({category_label(f.category.value, lang) for f in findings})
    worst = max(findings, key=lambda f: rank(f.severity))
    return t(
        "summary.issues",
        lang,
        verdict=verdict_label(verdict_value.value, lang),
        count=len(findings),
        categories=", ".join(cats),
        title=worst.title,
    )
