from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage -------------------------------------------------------
    data_dir: Path = BASE_DIR / "var"
    db_path: Path = BASE_DIR / "var" / "compliance.db"
    uspto_db_path: Path = BASE_DIR / "var" / "uspto.db"

    # --- Vision provider ----------------------------------------------
    # "anthropic" | "gemini" | "openrouter" | "ollama"
    vision_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2-vision"
    # OpenRouter proxies many vendors behind one OpenAI-compatible endpoint, so a
    # Gemini model reached this way needs an `sk-or-v1-...` key, never a Google
    # AI Studio key — the two are not interchangeable.
    openrouter_api_key: str | None = None
    openrouter_model: str = "google/gemini-3.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Comma-separated models tried in order when the primary is unavailable.
    vision_fallback_models: str = ""
    vision_max_attempts: int = 3
    vision_circuit_breaker_threshold: int = 3
    vision_circuit_breaker_cooldown_s: int = 180

    # --- Trademark sources --------------------------------------------
    # USPTO retired bulkdata.uspto.gov; the Open Data Portal API replaced it and
    # requires a free API key (register at https://data.uspto.gov/apis/getting-started).
    # Without a key the local index built from a manually downloaded bulk zip is
    # the only offline source — see data/build_uspto_index.py --zip.
    uspto_live_lookup: bool = True
    uspto_api_key: str | None = None
    uspto_api_base: str = "https://api.uspto.gov/api/v1"
    euipo_client_id: str | None = None
    euipo_client_secret: str | None = None

    # --- Pipeline ------------------------------------------------------
    worker_concurrency: int = 4
    max_upload_mb: int = 60
    # Ceiling on one whole multipart request, not on a single file. A batch is
    # rejected before it is sent because the wall it would otherwise hit is
    # nginx's client_max_body_size — and nginx answers 413 while the browser is
    # still uploading, which leaves the request pending instead of failed.
    # Kept under Cloudflare's 100 MB per-request cap, the real hard limit.
    max_request_mb: int = 95
    fetch_timeout_s: int = 60
    fetch_max_attempts: int = 3
    fetch_retry_jitter_s: float = 0.35
    fetch_retry_base_delay_s: float = 0.75
    ocr_timeout_s: float = 20.0
    ocr_max_attempts: int = 2
    render_max_edge: int = 1600  # long-edge px sent to the vision model
    #: Long-edge px of the derivative the UI serves. The vision render is deleted
    #: once analysis finishes, so this is the image the dashboard and the
    #: annotated overlay are built from — it has to outlive the analysis.
    preview_max_edge: int = 800

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"


settings = Settings()

for _p in (settings.data_dir, settings.uploads_dir, settings.renders_dir):
    _p.mkdir(parents=True, exist_ok=True)
