from __future__ import annotations

import csv
import io
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .. import db, queue, reports
from ..config import settings
from ..models import DesignMetadata
from ..pipeline import fetcher, i18n, loader, ocr, trademark, vision
from ..pipeline.rules import MARKETS, PLATFORMS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------
# Request bodies
# --------------------------------------------------------------------------


class LinkRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    metadata: DesignMetadata = Field(default_factory=DesignMetadata)
    label: str | None = None


class FolderRequest(BaseModel):
    url: str
    metadata: DesignMetadata = Field(default_factory=DesignMetadata)
    label: str | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _parse_metadata(raw: str | None) -> DesignMetadata:
    if not raw:
        return DesignMetadata()
    try:
        return DesignMetadata.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(422, f"Invalid metadata JSON: {exc}") from exc


def _new_job(source: str, label: str, meta: DesignMetadata) -> str:
    job_id = uuid.uuid4().hex[:12]
    db.create_job(job_id, source, label, meta.model_dump(mode="json"))
    return job_id


def _enqueue(
    job_id: str,
    filename: str,
    source: str,
    source_ref: str | None,
    path: Path | None,
    meta: DesignMetadata,
) -> str:
    design_id = uuid.uuid4().hex[:12]
    db.create_design(design_id, job_id, filename, source, source_ref, str(path) if path else None)
    queue.submit(
        queue.Task(
            design_id=design_id,
            job_id=job_id,
            filename=filename,
            source=source,
            source_ref=source_ref,
            path=path,
            meta=meta,
        )
    )
    return design_id


def _save_upload(upload: UploadFile) -> Path:
    name = Path(upload.filename or "design.png").name
    if Path(name).suffix.lower() not in loader.SUPPORTED_EXT:
        raise HTTPException(
            415,
            f"Unsupported file type '{Path(name).suffix}'. Supported: "
            + ", ".join(sorted(loader.SUPPORTED_EXT)),
        )

    dest = settings.uploads_dir / f"{uuid.uuid4().hex}_{name}"
    limit = settings.max_upload_mb * 1024 * 1024
    written = 0
    with dest.open("wb") as fh:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"{name} exceeds the {settings.max_upload_mb} MB limit")
            fh.write(chunk)
    return dest


# --------------------------------------------------------------------------
# Input method 1 — direct upload (1..N files)
# --------------------------------------------------------------------------


@router.post("/analyze/upload")
async def analyze_upload(
    files: list[UploadFile] = File(...),
    metadata: str | None = Form(None),
    label: str | None = Form(None),
):
    meta = _parse_metadata(metadata)
    job_id = _new_job("upload", label or f"{len(files)} uploaded file(s)", meta)

    accepted = 0
    for upload in files:
        try:
            path = _save_upload(upload)
        except HTTPException as exc:
            log.warning("Rejected upload %s: %s", upload.filename, exc.detail)
            continue
        _enqueue(job_id, Path(upload.filename or path.name).name, "upload", None, path, meta)
        accepted += 1

    if accepted == 0:
        db.fail_job(job_id, "No supported files in this upload")
        raise HTTPException(400, "No supported design files were uploaded")

    db.set_job_total(job_id, accepted)
    return {"job_id": job_id, "queued": accepted}


# --------------------------------------------------------------------------
# Input method 2 — CSV batch
# --------------------------------------------------------------------------

_FILE_KEYS = ("filename", "file", "file_name", "name", "design", "design_name", "image")
_URL_KEYS = ("url", "link", "image_url", "file_url", "drive_link", "source", "path")
_TITLE_KEYS = ("title", "listing_title", "product_title")
_MARKET_KEYS = ("market", "markets", "target_market", "region")
_PLATFORM_KEYS = ("platform", "platforms", "marketplace", "channel")
_NOTE_KEYS = ("notes", "note", "description", "comment")


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        for actual, value in row.items():
            if actual and actual.strip().lower().replace(" ", "_") == k:
                v = (value or "").strip()
                if v:
                    return v
    return None


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.replace(";", ",").replace("|", ",").split(",")]
    return [p for p in parts if p] or None


@router.post("/analyze/csv")
async def analyze_csv(
    file: UploadFile = File(...),
    metadata: str | None = Form(None),
    label: str | None = Form(None),
    attachments: list[UploadFile] = File(default=[]),
):
    """Batch from a CSV manifest.

    Recognised columns (case/spacing insensitive): filename, url/link, title,
    markets, platforms, notes. A row needs either a URL (fetched) or a filename
    matching one of the `attachments` files uploaded alongside the CSV.
    """
    default_meta = _parse_metadata(metadata)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    if not rows:
        raise HTTPException(400, "CSV is empty or has no header row")

    by_name: dict[str, Path] = {}
    for att in attachments or []:
        try:
            by_name[Path(att.filename or "").name.lower()] = _save_upload(att)
        except HTTPException as exc:
            log.warning("Skipping CSV attachment %s: %s", att.filename, exc.detail)

    job_id = _new_job("csv", label or Path(file.filename or "batch.csv").name, default_meta)

    queued, skipped = 0, []
    for i, row in enumerate(rows, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue

        url = _pick(row, _URL_KEYS)
        name = _pick(row, _FILE_KEYS)

        meta = DesignMetadata(
            markets=_split(_pick(row, _MARKET_KEYS)) or default_meta.markets,
            platforms=_split(_pick(row, _PLATFORM_KEYS)) or default_meta.platforms,
            title=_pick(row, _TITLE_KEYS) or default_meta.title,
            notes=_pick(row, _NOTE_KEYS) or default_meta.notes,
            # Language is a property of the batch, never of a CSV row.
            language=default_meta.language,
        )

        if url and url.lower().startswith(("http://", "https://")):
            _enqueue(job_id, name or Path(url).name or f"row-{i}", "csv", url, None, meta)
            queued += 1
        elif name and (local := by_name.get(Path(name).name.lower())):
            _enqueue(job_id, Path(name).name, "csv", None, local, meta)
            queued += 1
        else:
            skipped.append({"row": i, "reason": "no usable url or matching attached file"})

    if queued == 0:
        db.fail_job(job_id, "No usable rows in CSV")
        raise HTTPException(
            400,
            {
                "message": "No CSV row had a fetchable URL or a matching attached file.",
                "skipped": skipped[:20],
            },
        )

    db.set_job_total(job_id, queued)
    return {"job_id": job_id, "queued": queued, "skipped": skipped}


# --------------------------------------------------------------------------
# Input method 3 — links
# --------------------------------------------------------------------------


@router.post("/analyze/links")
async def analyze_links(body: LinkRequest):
    urls = [u.strip() for u in body.urls if u.strip()]
    if not urls:
        raise HTTPException(400, "No URLs provided")

    job_id = _new_job("link", body.label or f"{len(urls)} link(s)", body.metadata)
    for url in urls:
        _enqueue(job_id, Path(url).name or url, "link", url, None, body.metadata)
    db.set_job_total(job_id, len(urls))
    return {"job_id": job_id, "queued": len(urls)}


# --------------------------------------------------------------------------
# Bonus input method — cloud folder
# --------------------------------------------------------------------------


@router.post("/analyze/folder")
async def analyze_folder(body: FolderRequest):
    if not fetcher.is_drive_folder(body.url):
        raise HTTPException(
            400,
            "Only Google Drive folder links are supported here. For Dropbox, share "
            "individual file links via the link importer.",
        )
    try:
        entries = fetcher.list_drive_folder(body.url, settings.google_api_key)
    except fetcher.FetchError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not entries:
        raise HTTPException(404, "No design files found in that folder")

    job_id = _new_job("folder", body.label or f"Drive folder ({len(entries)})", body.metadata)
    for url, name in entries:
        _enqueue(job_id, name, "folder", url, None, body.metadata)
    db.set_job_total(job_id, len(entries))
    return {"job_id": job_id, "queued": len(entries)}


# --------------------------------------------------------------------------
# Reading results
# --------------------------------------------------------------------------


@router.get("/jobs")
async def get_jobs(limit: int = Query(50, ge=1, le=200)):
    jobs = db.list_jobs(limit)
    for job in jobs:
        job["stats"] = db.job_stats(job["id"])
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job["stats"] = db.job_stats(job_id)
    job["pending"] = queue.pending()
    return job


@router.get("/designs")
async def get_designs(
    job_id: str | None = None,
    verdict: str | None = None,
    niche: str | None = None,
    category: str | None = None,
):
    return {"designs": db.list_designs(job_id, verdict, niche, category)}


@router.get("/designs/{design_id}")
async def get_design(design_id: str):
    design = db.get_design(design_id)
    if not design:
        raise HTTPException(404, "Design not found")
    return design


@router.get("/jobs/{job_id}/export.csv")
async def export_csv(
    job_id: str,
    verdict: str | None = None,
    category: str | None = None,
    lang: str | None = None,
):
    designs = db.list_designs(job_id, verdict, None, category)
    return Response(
        content=reports.to_csv(designs, i18n.normalize(lang)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="compliance-{job_id}.csv"'},
    )


@router.get("/jobs/{job_id}/export.xlsx")
async def export_xlsx(
    job_id: str,
    verdict: str | None = None,
    category: str | None = None,
    lang: str | None = None,
):
    designs = db.list_designs(job_id, verdict, None, category)
    return Response(
        content=reports.to_xlsx(designs, db.job_stats(job_id), i18n.normalize(lang)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="compliance-{job_id}.xlsx"'},
    )


@router.get("/files/{name}")
async def get_file(name: str):
    safe = Path(name).name  # never let a path escape the renders dir
    path = settings.renders_dir / safe
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type="image/png")


# --------------------------------------------------------------------------
# Health / capability probe — the UI shows this so misconfiguration is obvious
# --------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, Any]:
    provider = settings.vision_provider
    key_present = {
        "anthropic": bool(settings.anthropic_api_key),
        "gemini": bool(settings.google_api_key),
        "ollama": True,
    }.get(provider, False)

    return {
        "status": "ok",
        "vision": {
            "provider": provider,
            "model": {
                "anthropic": settings.anthropic_model,
                "gemini": settings.gemini_model,
                "ollama": settings.ollama_model,
            }.get(provider),
            "configured": key_present,
            "circuit_breakers": vision.breaker_snapshot(provider),
        },
        "ocr": {"engine": "rapidocr" if ocr.available() else "vision-model-fallback"},
        "trademark": {
            **trademark.index_stats(),
            "live_lookup": settings.uspto_live_lookup,
        },
        "queue": {"pending": queue.pending(), "workers": settings.worker_concurrency},
        "formats": sorted(loader.SUPPORTED_EXT),
        "platforms": list(PLATFORMS.keys()),
        "markets": list(MARKETS.keys()),
    }


@router.get("/policies")
async def policies():
    return {
        "platforms": [
            {"key": p.key, "name": p.name, "source": p.source, "note": p.note}
            for p in PLATFORMS.values()
        ],
        "markets": [
            {"key": m.key, "name": m.name, "source": m.source, "note": m.note}
            for m in MARKETS.values()
        ],
    }
