"""A/B the autocrop setting on real designs, N runs per arm.

Autocrop makes small artwork sharper, but it also changes *what* the model is
looking at: a tight crop is a logo on its own, while the uncropped file is a
print canvas with the logo somewhere on it. Those can read differently to a
vision model, and the direction is not obvious from the pixels. One run per arm
cannot tell a real effect from model variance, so measure both arms repeatedly.

    python -m data.ab_crop <design.png> [more.png ...] --runs 3
    python -m data.ab_crop --dir /srv/samples/designs --pick 4 --runs 3

Needs a working vision provider — this calls the real model.
"""

from __future__ import annotations

import argparse
import collections
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import DesignMetadata  # noqa: E402
from app.pipeline import loader, run  # noqa: E402


def crop_gain(path: Path) -> float:
    """How much the long edge shrinks under autocrop. 1.0 means no change.

    Forces the setting on while measuring: this is a property of the image, and
    reporting 1.00x for every design just because the feature is currently off
    would hide exactly the signal this script exists to show.
    """
    was = settings.autocrop_transparent
    settings.autocrop_transparent = True
    try:
        img = Image.open(path)
        before = max(img.size)
        after = max(loader._autocrop(Image.open(path)).size)
        return before / after if after else 1.0
    except Exception:
        return 1.0
    finally:
        settings.autocrop_transparent = was


def run_once(path: Path, meta: DesignMetadata) -> tuple[str, int, list[str]]:
    report = run.analyze_design(
        design_id=uuid.uuid4().hex[:12],
        path=path,
        filename=path.name,
        source="upload",
        source_ref=None,
        meta=meta,
    )
    labels = [f"{f.severity.value}:{f.category.value}" for f in report.findings]
    return report.verdict.value, report.confidence, labels


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("designs", nargs="*", type=Path)
    ap.add_argument("--dir", type=Path, help="pick designs from this folder")
    ap.add_argument("--pick", type=int, default=4, help="how many to pick from --dir")
    ap.add_argument("--runs", type=int, default=3, help="runs per arm")
    ap.add_argument("--markets", default="US")
    ap.add_argument("--platforms", default="etsy")
    args = ap.parse_args()

    designs = list(args.designs)
    if args.dir:
        # Prefer designs autocrop actually changes — those carry the signal.
        candidates = sorted(args.dir.glob("*.png"))
        random.seed(3)
        scored = []
        for p in random.sample(candidates, min(len(candidates), 80)):
            g = crop_gain(p)
            if g > 1.5:
                scored.append((g, p))
        scored.sort(reverse=True)
        designs += [p for _, p in scored[: args.pick]]

    if not designs:
        print("no designs given")
        return 2

    meta = DesignMetadata(
        markets=[m.strip() for m in args.markets.split(",") if m.strip()],
        platforms=[p.strip() for p in args.platforms.split(",") if p.strip()],
    )

    print(f"{len(designs)} design x {args.runs} run x 2 arm = {len(designs)*args.runs*2} calls\n")

    results: dict[tuple[str, bool], list[tuple[str, int, list[str]]]] = collections.defaultdict(list)
    for path in designs:
        gain = crop_gain(path)
        print(f"{path.name}  (crop gain {gain:.2f}x)")
        for crop in (False, True):
            settings.autocrop_transparent = crop
            arm = "crop ON " if crop else "crop OFF"
            for _ in range(args.runs):
                try:
                    verdict, conf, labels = run_once(path, meta)
                except Exception as exc:  # noqa: BLE001
                    verdict, conf, labels = f"ERROR({type(exc).__name__})", 0, []
                results[(path.name, crop)].append((verdict, conf, labels))
            got = results[(path.name, crop)]
            summary = collections.Counter(v for v, _, _ in got)
            finds = sum(len(l) for _, _, l in got) / len(got)
            print(f"  {arm}: {dict(summary)}  findings/run={finds:.1f}")
        print()

    settings.autocrop_transparent = True

    print("=" * 62)
    off = collections.Counter()
    on = collections.Counter()
    for (name, crop), rows in results.items():
        for verdict, _, _ in rows:
            (on if crop else off)[verdict] += 1
    print(f"crop OFF: {dict(off)}")
    print(f"crop ON : {dict(on)}")

    flipped = []
    for path in designs:
        a = collections.Counter(v for v, _, _ in results[(path.name, False)]).most_common(1)
        b = collections.Counter(v for v, _, _ in results[(path.name, True)]).most_common(1)
        if a and b and a[0][0] != b[0][0]:
            flipped.append((path.name, a[0][0], b[0][0]))
    if flipped:
        print("\nverdict doi chieu (theo da so):")
        for name, a, b in flipped:
            print(f"  {name[:44]:46} {a} -> {b}")
    else:
        print("\nkhong design nao doi verdict giua hai arm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
