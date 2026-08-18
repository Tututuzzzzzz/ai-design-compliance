"""Provider-agnostic vision analysis.

Every provider returns the same `VisionAnalysis` object, so the verdict engine
downstream never learns which model ran. Claude is the default; Gemini and a
local Ollama VLM are drop-in alternatives selected by VISION_PROVIDER.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import threading
import time
from pathlib import Path

from pydantic import ValidationError

from ..config import settings
from ..models import DesignMetadata, VisionAnalysis
from . import i18n

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a print-on-demand IP compliance analyst. You review artwork before it is \
listed for sale and report what you can actually see in the image.

Your job has two halves.

1. NICHE — identify the commercial niche, the specific sub-niche/audience, the \
visual style, and any secondary motifs.

2. RISK — report every element that could create a copyright, trademark, \
publicity-rights, or platform-policy problem, in these categories:
  - copyrighted_character: cartoon/anime/comic/film characters (Mickey Mouse, \
Pikachu, Batman, Spider-Man, Disney princesses, Studio Ghibli, ...). Include \
recognisable silhouettes, stylised redraws, and "inspired by" derivatives — a \
redraw is still a derivative work.
  - brand_logo: company marks, wordmarks, monograms, sports team logos, \
university marks, product trade dress (Nike swoosh, Apple logo, LV monogram, \
Supreme box logo, ...).
  - trademarked_phrase: ONLY a slogan you can name the owner of — a specific \
registered mark belonging to a specific brand ("Just Do It" → Nike, "I ❤ NY" → \
NY State, "The Happiest Place on Earth" → Disney). Report the phrase verbatim in \
matched_text so a trademark register can verify it.
    Do NOT flag ordinary descriptive shirt text. "DOG MOM", "NURSE LIFE", \
"FISHING DAD", "BLESSED", "GIRL BOSS", "EST. 1985" and similar are how millions \
of listings describe their subject; they are not slogans and are not findings. \
If you cannot name the brand that owns the phrase, it is not a finding — say \
nothing rather than guessing.
  - public_figure: recognisable likeness or name of a real celebrity, athlete, \
musician, or politician.
  - copyrighted_artwork: reproductions of protected artwork, film stills, album \
covers, photographs, or in-copyright paintings.
  - licensed_font: a typeface that is commercially licensed and commonly used \
without a licence (Disney/Waltograph-style script, Star Wars display faces, \
Coca-Cola script, ...). Flag as a lead for manual check — you cannot confirm a \
licence from pixels alone.
  - prohibited_content: weapons/firearms, drugs, explicit sexual content, hate \
symbols, discriminatory content, self-harm, or content targeting minors.

RULES
- Report only what is visible. Never invent a registration number, a case, or a \
rights holder you are not sure of. If you are unsure who owns it, leave \
rights_holder null and lower your confidence.
- Generic, non-protected subject matter is NOT a finding. A plain dog, a \
snowflake, a stethoscope, the word "Nurse", a generic pumpkin — these are safe. \
Do not manufacture findings to look thorough; an empty findings list is the \
correct answer for an original design.
- A parody or a common phrase is not automatically infringing. Say so in the \
description and let severity reflect the real risk.
- Give every finding a bbox in normalised 0..1 coordinates (x,y = top-left \
corner of the box, w,h = size) covering the offending region, plus a short \
location_hint in words.
- Transcribe ALL legible text in ocr_lines, each with its own bbox.
- remediation must be concrete and actionable: what to remove, replace, or \
redraw so the design becomes sellable.

SEVERITY
- critical: a clearly protected character/logo/artwork reproduced directly.
- high: strong resemblance to a protected work, or a well-known registered slogan.
- medium: a real lead needing human review (possible licensed font, ambiguous \
likeness, phrase that may be registered).
- low: worth noting, unlikely to block a listing.
"""


def _system_prompt(meta: DesignMetadata) -> str:
    """The analysis rules plus, when the job is not in English, the instruction
    to write every human-readable field in the job's language."""
    extra = i18n.OUTPUT_LANGUAGE_INSTRUCTION.get(i18n.normalize(meta.language), "")
    return SYSTEM_PROMPT + extra if extra else SYSTEM_PROMPT


def _context_block(meta: DesignMetadata) -> str:
    markets = ", ".join(meta.markets) or "US"
    platforms = ", ".join(meta.platforms) or "etsy"
    lines = [
        f"Target markets: {markets}",
        f"Selling platforms: {platforms}",
    ]
    if meta.title:
        lines.append(f"Seller-provided title: {meta.title}")
    if meta.notes:
        lines.append(f"Seller notes: {meta.notes}")
    lines.append(
        "Consider the policies of these platforms and the trademark practice of "
        "these markets when judging severity."
    )
    return "\n".join(lines)


def _schema() -> dict:
    return VisionAnalysis.model_json_schema()


# --------------------------------------------------------------------------
# Schema sanitising for providers that accept only a subset of JSON Schema
# --------------------------------------------------------------------------

#: Keys Gemini's response_schema validator accepts. Anything else — notably the
#: `exclusiveMinimum` that Pydantic emits for `Field(gt=0)` — is rejected
#: outright, so we strip rather than pass through.
_GEMINI_KEEP = {
    "type",
    "description",
    "enum",
    "properties",
    "required",
    "items",
    "nullable",
    "anyOf",
}


def _gemini_schema(schema: dict) -> dict:
    """Inline $refs and drop unsupported keywords.

    We keep full Pydantic validation on our side (`_coerce`), so narrowing the
    schema we hand the model costs us nothing — the constraints are still
    enforced when we parse the reply.
    """
    defs = schema.get("$defs", {})

    def walk(node: object) -> object:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[-1]
            return walk(defs.get(name, {}))

        # Pydantic renders Optional[X] as anyOf[X, null]; Gemini wants nullable.
        variants = node.get("anyOf")
        if variants:
            non_null = [v for v in variants if v.get("type") != "null"]
            if len(non_null) == 1 and len(non_null) < len(variants):
                inner = walk(non_null[0])
                if isinstance(inner, dict):
                    inner["nullable"] = True
                    if "description" in node:
                        inner.setdefault("description", node["description"])
                    return inner

        out: dict = {}
        for key, value in node.items():
            if key not in _GEMINI_KEEP:
                continue
            if key == "properties" and isinstance(value, dict):
                out[key] = {k: walk(v) for k, v in value.items()}
            else:
                out[key] = walk(value)

        # An object with no properties left is meaningless to the validator.
        if out.get("type") == "object" and not out.get("properties"):
            out.pop("required", None)
        return out

    return walk(schema)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Anthropic (default)
# --------------------------------------------------------------------------


def _analyze_anthropic(image_path: Path, meta: DesignMetadata, model: str) -> VisionAnalysis:
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    data = base64.standard_b64encode(image_path.read_bytes()).decode()

    response = client.messages.parse(
        model=model,
        max_tokens=16000,
        system=_system_prompt(meta),
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        output_format=VisionAnalysis,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": data},
                    },
                    {
                        "type": "text",
                        "text": f"{_context_block(meta)}\n\nAnalyse this design.",
                    },
                ],
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("Vision model declined to analyse this image.")
    if response.parsed_output is None:
        raise RuntimeError("Vision model returned no parseable analysis.")
    return response.parsed_output


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------


def _analyze_gemini(image_path: Path, meta: DesignMetadata, model: str) -> VisionAnalysis:
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
            f"{_context_block(meta)}\n\nAnalyse this design.",
        ],
        config=types.GenerateContentConfig(
            system_instruction=_system_prompt(meta),
            response_mime_type="application/json",
            # A sanitised dict, not the Pydantic class: Gemini rejects several
            # keywords Pydantic emits. We still validate the reply ourselves.
            response_schema=_gemini_schema(_schema()),
        ),
    )
    return _coerce(response.text)


# --------------------------------------------------------------------------
# Ollama (fully offline fallback)
# --------------------------------------------------------------------------


def _analyze_ollama(image_path: Path, meta: DesignMetadata, model: str) -> VisionAnalysis:
    import httpx  # noqa: PLC0415

    data = base64.standard_b64encode(image_path.read_bytes()).decode()
    payload = {
        "model": model,
        "system": _system_prompt(meta),
        "prompt": f"{_context_block(meta)}\n\nAnalyse this design. Reply with JSON only.",
        "images": [data],
        "format": _schema(),
        "stream": False,
        "options": {"num_ctx": 8192},
    }
    with httpx.Client(timeout=300) as client:
        resp = client.post(f"{settings.ollama_base_url}/api/generate", json=payload)
        resp.raise_for_status()
        return _coerce(resp.json().get("response", ""))


# --------------------------------------------------------------------------


def _coerce(raw: str | None) -> VisionAnalysis:
    if not raw:
        raise RuntimeError("Vision model returned an empty response.")
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    try:
        return VisionAnalysis.model_validate_json(text)
    except ValidationError:
        # Some models wrap the object in a preamble; salvage the outermost braces.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return VisionAnalysis.model_validate(json.loads(text[start : end + 1]))


_PROVIDERS = {
    "anthropic": _analyze_anthropic,
    "gemini": _analyze_gemini,
    "ollama": _analyze_ollama,
}

# Circuit breaker state is per provider:model and shared across worker threads.
_breaker_lock = threading.Lock()
_breaker_until: dict[str, float] = {}
_breaker_failures: dict[str, int] = {}


#: Substrings that mark an error as worth retrying. Free-tier vision endpoints
#: return these constantly under load; failing a design because the provider was
#: briefly busy would show up as a RISKY verdict on an otherwise clean design.
_TRANSIENT = (
    "503",
    "429",
    "500",
    "overloaded",
    "unavailable",
    "resource_exhausted",
    "rate limit",
    "ratelimit",
    "timeout",
    "deadline",
    "temporarily",
)


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(t in text for t in _TRANSIENT)


def _cb_key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def _cb_open_for(key: str, seconds: int) -> None:
    with _breaker_lock:
        _breaker_until[key] = time.monotonic() + max(1, seconds)
        _breaker_failures[key] = 0


def _cb_mark_success(key: str) -> None:
    with _breaker_lock:
        _breaker_failures[key] = 0
        _breaker_until.pop(key, None)


def _cb_mark_failure(key: str, *, threshold: int, cooldown_s: int) -> None:
    with _breaker_lock:
        count = _breaker_failures.get(key, 0) + 1
        _breaker_failures[key] = count
        if count >= max(1, threshold):
            _breaker_until[key] = time.monotonic() + max(1, cooldown_s)
            _breaker_failures[key] = 0


def _cb_remaining(key: str) -> float:
    with _breaker_lock:
        until = _breaker_until.get(key, 0.0)
    return max(0.0, until - time.monotonic())


def breaker_snapshot(provider: str | None = None) -> dict[str, dict[str, int | str]]:
    """Expose circuit-breaker state for health/monitoring endpoints.

    Returns a map keyed by "provider:model" with state, recent failure count,
    and cooldown time when open.
    """
    provider_name = (provider or settings.vision_provider).lower()

    primary = {
        "anthropic": settings.anthropic_model,
        "gemini": settings.gemini_model,
        "ollama": settings.ollama_model,
    }.get(provider_name)
    fallbacks = [m.strip() for m in (settings.vision_fallback_models or "").split(",") if m.strip()]

    configured = [m for m in ([primary] if primary else []) + fallbacks if m]
    configured = list(dict.fromkeys(configured))

    with _breaker_lock:
        known_models = {
            key.split(":", 1)[1]
            for key in set(_breaker_until) | set(_breaker_failures)
            if key.startswith(f"{provider_name}:") and ":" in key
        }

    models = list(dict.fromkeys(configured + sorted(known_models)))
    snapshot: dict[str, dict[str, int | str]] = {}
    for model in models:
        key = _cb_key(provider_name, model)
        remaining = _cb_remaining(key)
        with _breaker_lock:
            failures = int(_breaker_failures.get(key, 0))
        entry: dict[str, int | str] = {
            "state": "open" if remaining > 0 else "closed",
            "failures": failures,
        }
        if remaining > 0:
            entry["cooldown_remaining_s"] = int(math.ceil(remaining))
        snapshot[key] = entry

    return snapshot


def analyze(image_path: Path, meta: DesignMetadata) -> tuple[VisionAnalysis, str]:
    """Run the configured provider, retrying transient failures.

    Tries the primary model with backoff, then each fallback model in turn. A
    non-transient error (bad key, unknown model, malformed reply) fails fast —
    retrying those just burns the batch's time budget.

    Returns (analysis, provider_label).
    """
    provider = settings.vision_provider.lower()
    fn = _PROVIDERS.get(provider)
    if fn is None:
        raise RuntimeError(
            f"Unknown VISION_PROVIDER '{provider}'. Expected one of: {', '.join(_PROVIDERS)}"
        )

    primary = {
        "anthropic": settings.anthropic_model,
        "gemini": settings.gemini_model,
        "ollama": settings.ollama_model,
    }[provider]

    fallbacks = [m.strip() for m in (settings.vision_fallback_models or "").split(",") if m.strip()]
    chain = [primary] + [m for m in fallbacks if m != primary]
    threshold = max(1, settings.vision_circuit_breaker_threshold)
    cooldown_s = max(1, settings.vision_circuit_breaker_cooldown_s)

    last: Exception | None = None
    for model in chain:
        key = _cb_key(provider, model)
        remaining = _cb_remaining(key)
        if remaining > 0:
            log.warning("%s skipped: circuit open for %.0fs", model, remaining)
            continue

        for attempt in range(settings.vision_max_attempts):
            try:
                analysis = fn(image_path, meta, model)
                _cb_mark_success(key)
                return analysis, f"{provider}:{model}"
            except Exception as exc:
                last = exc
                if not _is_transient(exc):
                    _cb_open_for(key, cooldown_s)
                    if model == chain[-1]:
                        raise
                    log.warning("%s unusable (%s); trying next model", model, str(exc)[:120])
                    break  # no point retrying a bad key or an unknown model
                if attempt + 1 < settings.vision_max_attempts:
                    delay = 2**attempt
                    log.info(
                        "%s transient failure (%s); retry %d/%d in %ds",
                        model,
                        str(exc)[:80],
                        attempt + 1,
                        settings.vision_max_attempts - 1,
                        delay,
                    )
                    time.sleep(delay)
        else:
            # Loop ran to completion, so every attempt hit a transient failure.
            log.warning("%s still failing after %d attempts", model, settings.vision_max_attempts)
            _cb_mark_failure(key, threshold=threshold, cooldown_s=cooldown_s)

    if all(_cb_remaining(_cb_key(provider, m)) > 0 for m in chain):
        opens = [f"{m} ({_cb_remaining(_cb_key(provider, m)):.0f}s)" for m in chain]
        raise RuntimeError(
            "All configured vision models are temporarily blocked by the circuit "
            f"breaker: {', '.join(opens)}"
        )

    raise RuntimeError(
        f"All vision models failed ({', '.join(chain)}). Last error: {last}"
    ) from last
