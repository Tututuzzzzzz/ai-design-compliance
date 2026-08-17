"""Generate a synthetic evaluation set with known-correct verdicts.

These are deliberately crude line drawings, not real infringing artwork: the
point is to exercise every branch of the verdict engine (clear violation,
text-only trademark, prohibited goods, and — most importantly — clean originals
that must NOT be flagged) without shipping other people's IP in the repo.

Replace them with your own designs once you have them; `evaluate.py` reads any
manifest with the same columns.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 900


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _centered(d: ImageDraw.ImageDraw, text: str, y: int, size: int = 54) -> None:
    f = _font(size)
    w = d.textlength(text, font=f)
    d.text(((S - w) / 2, y), text, fill="black", font=f)


# --------------------------------------------------------------------------
# Cases: (filename, expected verdicts, expected categories, draw fn, note)
# --------------------------------------------------------------------------


def mickey(d):
    d.ellipse([300, 210, 600, 510], fill="black")
    d.ellipse([240, 150, 390, 300], fill="black")
    d.ellipse([510, 150, 660, 300], fill="black")
    _centered(d, "THE HAPPIEST", 600, 46)
    _centered(d, "PLACE ON EARTH", 660, 46)


def nike(d):
    _centered(d, "JUST DO IT", 400, 82)
    d.line([250, 520, 420, 570, 660, 430], fill="black", width=22)


def dog_mom(d):
    _centered(d, "DOG MOM", 380, 90)
    for cx in (330, 420, 510, 600):
        d.ellipse([cx, 500, cx + 55, 560], fill="black")
    d.ellipse([380, 570, 540, 690], fill="black")


def halloween(d):
    d.ellipse([250, 300, 650, 640], outline="black", width=14)
    d.polygon([(360, 400), (420, 400), (390, 460)], fill="black")
    d.polygon([(480, 400), (540, 400), (510, 460)], fill="black")
    d.arc([340, 470, 560, 580], 0, 180, fill="black", width=12)
    d.rectangle([430, 250, 470, 310], fill="black")
    _centered(d, "SPOOKY SEASON", 720, 52)


def nurse(d):
    d.rectangle([400, 250, 500, 560], fill="black")
    d.rectangle([295, 355, 605, 455], fill="black")
    _centered(d, "ICU NURSE", 640, 64)
    _centered(d, "EST. 2015", 710, 44)


def guns(d):
    d.ellipse([330, 220, 570, 460], outline="black", width=14)
    d.ellipse([385, 290, 425, 340], fill="black")
    d.ellipse([475, 290, 515, 340], fill="black")
    for x0, x1 in ((180, 400), (500, 720)):
        d.rectangle([x0, 540, x1, 590], fill="black")
        d.rectangle([x0 + 30, 590, x0 + 80, 660], fill="black")
    _centered(d, "COME AND TAKE IT", 720, 48)


def fishing(d):
    d.line([220, 640, 640, 220], fill="black", width=10)
    d.line([640, 220, 660, 420], fill="black", width=5)
    d.ellipse([600, 420, 720, 480], outline="black", width=8)
    d.polygon([(720, 425), (770, 450), (720, 475)], fill="black")
    _centered(d, "REEL COOL DAD", 720, 56)


def ny(d):
    _centered(d, "I", 330, 130)
    d.polygon(
        [(450, 400), (410, 350), (370, 390), (450, 480), (530, 390), (490, 350)], fill="black"
    )
    _centered(d, "NY", 520, 130)


CASES = [
    ("mickey_slogan.png", "BLOCKED", "copyrighted_character", mickey,
     "Registered character silhouette plus a brand slogan"),
    ("just_do_it.png", "RISKY|BLOCKED", "trademarked_phrase", nike,
     "Text-only registered slogan; RISKY without a register index, BLOCKED with one"),
    ("i_love_ny.png", "RISKY|BLOCKED", "trademarked_phrase", ny,
     "Registered mark rendered as a symbol"),
    ("guns_skull.png", "RISKY|BLOCKED", "prohibited_content", guns,
     "Firearms imagery — banned outright on Amazon Merch and TikTok Shop"),
    ("dog_mom.png", "SAFE", "", dog_mom, "Generic descriptive text — must not be flagged"),
    ("halloween.png", "SAFE", "", halloween, "Generic seasonal motif"),
    ("nurse_icu.png", "SAFE", "", nurse, "Occupation niche, no protected element"),
    ("fishing_dad.png", "SAFE", "", fishing, "Original pun, generic subject"),
]


NICHES = {
    "mickey_slogan.png": "Theme Park",
    "just_do_it.png": "Fitness",
    "i_love_ny.png": "Travel",
    "guns_skull.png": "Firearms",
    "dog_mom.png": "Dog",
    "halloween.png": "Halloween",
    "nurse_icu.png": "Nurse",
    "fishing_dad.png": "Fishing",
}


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, _v, _c, fn, _n in CASES:
        img = Image.new("RGB", (S, S), "white")
        fn(ImageDraw.Draw(img))
        img.save(out_dir / name)

    manifest = out_dir / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["filename", "expected", "expected_category", "expected_niche", "note"]
        )
        for name, verdicts, category, _fn, note in CASES:
            w.writerow([name, verdicts, category, NICHES.get(name, ""), note])

    return manifest


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.config import settings

    path = build(settings.data_dir / "evalset")
    print(f"Wrote {len(CASES)} designs + manifest -> {path}")
