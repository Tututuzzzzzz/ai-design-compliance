"""Score the agent against a manifest of designs with known-correct verdicts.

Use it to pick a vision model on evidence rather than on latency, and to produce
the accuracy numbers for a submission.

    # build + score the built-in synthetic set with the configured model
    python -m data.evaluate

    # compare candidate models head to head
    python -m data.evaluate --models gemini-3.5-flash gemini-3.1-flash-lite

    # score your own designs
    python -m data.evaluate --manifest /path/to/manifest.csv

Manifest columns: filename, expected (pipe-separated acceptable verdicts),
expected_category (optional), note (optional).

Two error classes are reported separately because they are not equally bad:
  MISS       — something infringing came back SAFE. This is what gets a seller
               banned, and the metric to minimise first.
  FALSE ALARM— a clean original came back BLOCKED. This makes the tool unusable
               because users stop trusting it.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models import DesignMetadata  # noqa: E402
from app.pipeline import run  # noqa: E402


@dataclass
class Row:
    filename: str
    expected: set[str]
    categories: set[str]
    note: str
    niche: str = ""
    sub_niche: str = ""
    markets: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)


@dataclass
class Result:
    model: str
    correct: int = 0
    misses: list[str] = field(default_factory=list)
    false_alarms: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    category_hits: int = 0
    category_total: int = 0
    niche_hits: int = 0
    niche_total: int = 0
    category_misses: list[str] = field(default_factory=list)
    niche_misses: list[str] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    total: int = 0


def _split(raw: str | None, default: list[str]) -> list[str]:
    parts = [p.strip() for p in (raw or "").replace(";", ",").replace("|", ",").split(",")]
    return [p for p in parts if p] or list(default)


def load_manifest(path: Path, markets: list[str], platforms: list[str]) -> list[Row]:
    rows = []
    with path.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            name = (r.get("filename") or "").strip()
            if not name:
                continue
            rows.append(
                Row(
                    filename=name,
                    expected={
                        v.strip().upper() for v in (r.get("expected") or "").split("|") if v.strip()
                    },
                    categories={
                        c.strip()
                        for c in (r.get("expected_category") or "").split("|")
                        if c.strip()
                    },
                    note=(r.get("note") or "").strip(),
                    niche=(r.get("expected_niche") or "").strip(),
                    sub_niche=(r.get("expected_sub_niche") or "").strip(),
                    markets=_split(r.get("markets"), markets),
                    platforms=_split(r.get("platforms"), platforms),
                )
            )
    return rows


def _niche_match(expected: str, sub_expected: str, report) -> bool:
    """Loose containment match on significant words.

    Niche labels are free text — "Music Fan" vs "Classic Rock / Band Merch" are
    the same answer written differently, so exact-string comparison would score
    a correct detection as wrong. We require one meaningful word in common
    between the expected label and anything the agent produced.
    """
    actual = " ".join(
        [
            report.niche.primary or "",
            report.niche.sub_niche or "",
            report.niche.audience or "",
            " ".join(report.niche.motifs or []),
        ]
    ).lower()

    stop = {"fan", "lover", "lovers", "and", "the", "of", "design", "themed", "art", "shirt"}
    wanted = {
        w
        for w in re.split(r"[^a-z0-9]+", f"{expected} {sub_expected}".lower())
        if len(w) > 2 and w not in stop
    }
    return bool(wanted) and any(w in actual for w in wanted)


def score(rows: list[Row], base: Path, model: str) -> Result:
    res = Result(model=model, total=len(rows))

    for row in rows:
        path = base / row.filename
        if not path.exists():
            res.errors.append(f"{row.filename}: file not found")
            continue

        started = time.perf_counter()
        try:
            report = run.analyze_design(
                design_id=row.filename,
                path=path,
                filename=row.filename,
                source="eval",
                source_ref=None,
                meta=DesignMetadata(markets=row.markets, platforms=row.platforms),
            )
        except Exception as exc:
            res.errors.append(f"{row.filename}: {type(exc).__name__}: {str(exc)[:90]}")
            continue

        res.latencies.append(time.perf_counter() - started)
        actual = report.verdict.value

        if actual in row.expected:
            res.correct += 1
        elif actual == "SAFE":
            res.misses.append(f"{row.filename}: expected {'/'.join(sorted(row.expected))}, got SAFE")
        elif "SAFE" in row.expected:
            res.false_alarms.append(f"{row.filename}: expected SAFE, got {actual}")
        else:
            res.other.append(
                f"{row.filename}: expected {'/'.join(sorted(row.expected))}, got {actual}"
            )

        if row.categories:
            res.category_total += 1
            if any(f.category.value in row.categories for f in report.findings):
                res.category_hits += 1
            else:
                res.category_misses.append(
                    f"{row.filename}: expected one of {'/'.join(sorted(row.categories))}, "
                    f"got {sorted({f.category.value for f in report.findings}) or 'nothing'}"
                )

        if row.niche:
            res.niche_total += 1
            if _niche_match(row.niche, row.sub_niche, report):
                res.niche_hits += 1
            else:
                res.niche_misses.append(
                    f"{row.filename}: expected {row.niche!r}"
                    f"{'/' + row.sub_niche if row.sub_niche else ''}, "
                    f"got {report.niche.primary!r}/{report.niche.sub_niche!r}"
                )

    return res


def report(res: Result) -> None:
    scored = res.total - len(res.errors)
    acc = (res.correct / scored * 100) if scored else 0.0
    lat = statistics.median(res.latencies) if res.latencies else 0.0

    print(f"\n{'=' * 74}")
    print(f"{res.model}")
    print(f"{'=' * 74}")
    print(f"  Verdict accuracy   {res.correct}/{scored}  ({acc:.0f}%)")
    if res.category_total:
        print(
            f"  Risk category hit  {res.category_hits}/{res.category_total}"
            f"  ({res.category_hits / res.category_total * 100:.0f}%)"
        )
    if res.niche_total:
        print(
            f"  Niche accuracy     {res.niche_hits}/{res.niche_total}"
            f"  ({res.niche_hits / res.niche_total * 100:.0f}%)"
        )
    print(f"  Median latency     {lat:.1f}s")
    print(f"  MISSES (danger)    {len(res.misses)}")
    for m in res.misses:
        print(f"      ! {m}")
    print(f"  FALSE ALARMS       {len(res.false_alarms)}")
    for m in res.false_alarms:
        print(f"      ~ {m}")
    if res.other:
        print(f"  Wrong tier         {len(res.other)}")
        for m in res.other:
            print(f"      · {m}")
    if res.category_misses:
        print(f"  Category mismatches {len(res.category_misses)}")
        for m in res.category_misses[:8]:
            print(f"      # {m}")
    if res.niche_misses:
        print(f"  Niche mismatches   {len(res.niche_misses)}")
        for m in res.niche_misses[:8]:
            print(f"      ? {m}")
    if res.errors:
        print(f"  ERRORS             {len(res.errors)}")
        for m in res.errors:
            print(f"      x {m}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, help="CSV manifest; default builds the synthetic set")
    ap.add_argument("--models", nargs="*", help="model ids to compare (default: configured model)")
    ap.add_argument("--markets", nargs="*", default=["US"])
    ap.add_argument("--platforms", nargs="*", default=["etsy", "amazon_merch"])
    args = ap.parse_args()

    if args.manifest:
        manifest = args.manifest
    else:
        from data.evalset import build  # noqa: PLC0415

        manifest = build(settings.data_dir / "evalset")
        print(f"Built synthetic eval set at {manifest.parent}")

    rows = load_manifest(manifest, list(args.markets), list(args.platforms))
    if not rows:
        print("Manifest has no usable rows.")
        return 1

    provider = settings.vision_provider
    models = args.models or [
        settings.gemini_model if provider == "gemini" else settings.anthropic_model
    ]

    print(
        f"\nScoring {len(rows)} design(s) · provider={provider} · "
        f"defaults markets={args.markets} platforms={args.platforms} "
        "(per-row values in the manifest win)"
    )

    results = []
    for model in models:
        if provider == "gemini":
            settings.gemini_model = model
        else:
            settings.anthropic_model = model
        results.append(score(rows, manifest.parent, model))
        report(results[-1])

    if len(results) > 1:
        print(f"\n{'=' * 74}\nSUMMARY (sorted by misses, then accuracy)\n{'=' * 74}")
        print(f"{'model':34} {'acc':>6} {'miss':>5} {'false':>6} {'p50':>7}")
        ranked = sorted(
            results,
            key=lambda r: (len(r.misses), len(r.false_alarms), -r.correct),
        )
        for r in ranked:
            scored = r.total - len(r.errors)
            acc = (r.correct / scored * 100) if scored else 0
            lat = statistics.median(r.latencies) if r.latencies else 0
            print(
                f"{r.model:34} {acc:5.0f}% {len(r.misses):5} "
                f"{len(r.false_alarms):6} {lat:6.1f}s"
            )
        print(f"\nRecommended: {ranked[0].model}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
