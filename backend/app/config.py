from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage -------------------------------------------------------
    data_dir: Path = BASE_DIR / "var"
    db_path: Path = BASE_DIR / "var" / "compliance.db"

    # --- Vision provider ----------------------------------------------
    # "anthropic" | "gemini" | "ollama"
    vision_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    google_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2-vision"
    # Comma-separated models tried in order when the primary is unavailable.
    vision_fallback_models: str = ""
    vision_max_attempts: int = 3
    vision_circuit_breaker_threshold: int = 3
    vision_circuit_breaker_cooldown_s: int = 180

    # --- Trademark sources --------------------------------------------
    # The keyed Open Data Portal API (register at
    # https://data.uspto.gov/apis/getting-started). Kept as a fallback behind the
    # keyless public search below, which needs no credential and — unlike this
    # one — returns the Nice classes.
    uspto_live_lookup: bool = True
    uspto_api_key: str | None = None
    uspto_api_base: str = "https://api.uspto.gov/api/v1"

    # The public trademark search at tmsearch.uspto.gov queries the current
    # register with no key at all, and unlike the keyed Open Data Portal API it
    # returns the Nice classes — which is what lets an off-class hit be
    # recognised as such instead of blocking a listing. It is the endpoint the
    # USPTO's own search UI calls, so it is a public interface but not a
    # documented contract: treat it as best-effort like every other live
    # register, and turn it off here if it ever starts refusing traffic.
    uspto_tmsearch_lookup: bool = True
    uspto_tmsearch_url: str = "https://tmsearch.uspto.gov/prod-stage-v1-0-0/tmsearch"

    # EUIPO covers the EU market, which USPTO cannot speak for. Credentials are
    # free: register an app at https://dev.euipo.europa.eu, subscribe to the
    # Trademark Search API, then copy the Client ID / Secret here. Auth is OAuth2
    # client_credentials (scope "uid"); the client id also travels as the
    # X-IBM-Client-Id header on every call.
    #
    # Both URLs are settings rather than constants because EUIPO runs a separate
    # sandbox host, and gateway paths have moved before. If a deployment gets
    # HTTP 404 from the search call, the fix is an env var, not a code change.
    euipo_live_lookup: bool = True
    euipo_client_id: str | None = None
    euipo_client_secret: str | None = None
    euipo_api_base: str = "https://api.euipo.europa.eu/trademark-search"
    euipo_token_url: str = "https://euipo.europa.eu/cas-server-webapp/oidc/accessToken"

    # --- Pipeline ------------------------------------------------------
    worker_concurrency: int = 4
    max_upload_mb: int = 60
    fetch_timeout_s: int = 60
    fetch_max_attempts: int = 3
    fetch_retry_jitter_s: float = 0.35
    fetch_retry_base_delay_s: float = 0.75
    ocr_timeout_s: float = 20.0
    ocr_max_attempts: int = 2
    render_max_edge: int = 1600  # long-edge px sent to the vision model
    # Trim transparent margin so small artwork is not shrunk by the canvas ratio.
    #
    # OFF by default, and that is a measured decision rather than caution. Cropping
    # does make small art far sharper — a golf logo went from 1.6% of a 4200x4800
    # canvas to filling the frame, ~3x taller lettering. But A/B on real designs
    # (4 designs x 3 runs x 2 arms, data/ab_crop.py) found no net gain: 6/12 hits
    # uncropped vs 5/12 cropped. One case got clearly worse — a design that is
    # *only* a logo went from 3/3 detections to 0/3, the model calling the tight
    # crop "original work on a generic subject". A logo filling the frame reads as
    # a logo asset; the same logo on a print canvas reads as a design being sold.
    # Losing that framing costs more than the sharpness gains.
    #
    # Turn it on for catalogues of very small artwork on very large canvases, but
    # measure with data/ab_crop.py first — do not assume it helps.
    autocrop_transparent: bool = False

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"


settings = Settings()

for _p in (settings.data_dir, settings.uploads_dir, settings.renders_dir):
    _p.mkdir(parents=True, exist_ok=True)
