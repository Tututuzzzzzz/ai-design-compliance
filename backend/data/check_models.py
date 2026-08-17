"""Show which vision models the configured key can actually reach.

Model availability changes without notice and varies per key/tier, so a hardcoded
default will eventually 404. Run this to pick a working model:

    docker compose exec api python -m data.check_models
    docker compose exec api python -m data.check_models --probe   # also send a real image
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.models import DesignMetadata  # noqa: E402


def _test_image() -> Path:
    from PIL import Image, ImageDraw  # noqa: PLC0415

    out = settings.data_dir / "model_probe.png"
    img = Image.new("RGB", (640, 640), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse([180, 120, 460, 400], outline="black", width=10)
    draw.text((150, 500), "SAMPLE DESIGN TEXT", fill="black")
    img.save(out)
    return out


def _probe(model: str) -> str:
    from app.pipeline import vision  # noqa: PLC0415

    previous = settings.gemini_model, settings.anthropic_model
    if settings.vision_provider == "gemini":
        settings.gemini_model = model
    else:
        settings.anthropic_model = model

    started = time.perf_counter()
    try:
        analysis, _ = vision.analyze(
            _test_image(), DesignMetadata(markets=["US"], platforms=["etsy"])
        )
        return (
            f"OK  {time.perf_counter() - started:5.1f}s  "
            f"niche={analysis.niche.primary!r} findings={len(analysis.findings)} "
            f"ocr={len(analysis.ocr_lines)}"
        )
    except Exception as exc:
        return f"FAIL {type(exc).__name__}: {str(exc)[:110]}"
    finally:
        settings.gemini_model, settings.anthropic_model = previous


def list_gemini() -> list[str]:
    from google import genai  # noqa: PLC0415

    client = genai.Client(api_key=settings.google_api_key)
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if actions and "generateContent" not in actions:
            continue
        name = m.name.replace("models/", "")
        if "gemini" in name and not any(x in name for x in ("embed", "tts", "image")):
            names.append(name)
    return names


def list_anthropic() -> list[str]:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return [m.id for m in client.models.list()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", action="store_true", help="send a real image to each model")
    ap.add_argument("--only", nargs="*", help="probe just these model ids")
    args = ap.parse_args()

    provider = settings.vision_provider
    print(f"Provider: {provider}\n")

    try:
        models = args.only or (list_gemini() if provider == "gemini" else list_anthropic())
    except Exception as exc:
        print(f"Could not list models: {type(exc).__name__}: {exc}")
        print("Check that the key for this provider is set in .env.")
        return 1

    if not args.probe:
        for name in models:
            print(" ", name)
        print(f"\n{len(models)} model(s). Re-run with --probe to test them against a real image.")
        return 0

    for name in models:
        print(f"{name:34} {_probe(name)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
