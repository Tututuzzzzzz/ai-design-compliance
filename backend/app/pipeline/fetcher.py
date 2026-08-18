"""Resolve a user-supplied URL into a local file.

Handles direct image URLs plus the share-link formats people actually paste:
Google Drive, Dropbox, S3 (public or presigned), and generic HTTP(S).
"""

from __future__ import annotations

import random
import time
import re
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import settings

_DRIVE_FILE = re.compile(r"/file/d/([A-Za-z0-9_-]+)")
_DRIVE_FOLDER = re.compile(r"/folders/([A-Za-z0-9_-]+)")

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/tiff": ".tif",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
    "image/vnd.adobe.photoshop": ".psd",
    "application/x-photoshop": ".psd",
    "application/postscript": ".ai",
}


class FetchError(RuntimeError):
    pass


_TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


def is_drive_folder(url: str) -> bool:
    return "drive.google.com" in url and bool(_DRIVE_FOLDER.search(url))


def normalize(url: str) -> str:
    """Rewrite share links into their direct-download equivalents."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if "drive.google.com" in host:
        m = _DRIVE_FILE.search(url)
        if not m:
            qs = parse_qs(parsed.query)
            ids = qs.get("id")
            if not ids:
                raise FetchError(
                    "Google Drive link has no file id. Use a /file/d/<id>/view link, "
                    "or connect a folder via the folder importer."
                )
            file_id = ids[0]
        else:
            file_id = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    if "dropbox.com" in host:
        # ?dl=0 renders an HTML preview page; dl=1 serves the bytes.
        base = url.split("?")[0]
        return f"{base}?dl=1"

    return url


def filename_for(url: str, content_type: str | None) -> str:
    name = Path(urlparse(url).path).name
    ext = Path(name).suffix.lower()
    if ext:
        return name
    guessed = _EXT_BY_MIME.get((content_type or "").split(";")[0].strip(), ".png")
    return f"{(name or 'design')}{guessed}"


def fetch(url: str) -> tuple[Path, str]:
    """Download `url` into uploads/. Returns (local_path, display_filename)."""
    target = normalize(url)
    limit = settings.max_upload_mb * 1024 * 1024
    attempts = max(1, settings.fetch_max_attempts)
    base = max(0.05, settings.fetch_retry_base_delay_s)
    jitter = max(0.0, settings.fetch_retry_jitter_s)
    last_exc: Exception | None = None

    for attempt in range(attempts):
        dest: Path | None = None
        try:
            with httpx.Client(follow_redirects=True, timeout=settings.fetch_timeout_s) as client:
                with client.stream("GET", target) as resp:
                    if resp.status_code in _TRANSIENT_STATUS:
                        raise FetchError(f"Temporary HTTP {resp.status_code} while fetching {url}")
                    resp.raise_for_status()
                    ctype = resp.headers.get("content-type", "")
                    if "text/html" in ctype:
                        raise FetchError(
                            f"URL returned an HTML page, not a file ({url}). "
                            "Check that the link is publicly shared."
                        )

                    display = filename_for(url, ctype)
                    dest = settings.uploads_dir / f"{uuid.uuid4().hex}_{display}"
                    written = 0
                    with dest.open("wb") as fh:
                        for chunk in resp.iter_bytes(64 * 1024):
                            written += len(chunk)
                            if written > limit:
                                fh.close()
                                dest.unlink(missing_ok=True)
                                raise FetchError(
                                    f"File exceeds {settings.max_upload_mb} MB limit: {url}"
                                )
                            fh.write(chunk)
            return dest, display

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            last_exc = FetchError(f"Could not download {url}: HTTP {status}")
            if status not in _TRANSIENT_STATUS or attempt + 1 >= attempts:
                raise last_exc from exc

        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
            last_exc = FetchError(f"Could not download {url}: {exc}")
            if attempt + 1 >= attempts:
                raise last_exc from exc

        except FetchError as exc:
            last_exc = exc
            message = str(exc).lower()
            is_transient = "temporary http" in message
            if not is_transient or attempt + 1 >= attempts:
                raise

        finally:
            if dest is not None and dest.exists() and last_exc is not None:
                dest.unlink(missing_ok=True)

        delay = (base * (2**attempt)) + random.uniform(0.0, jitter)
        time.sleep(delay)

    raise FetchError(f"Could not download {url}: {last_exc or 'unknown error'}")


def list_drive_folder(url: str, api_key: str | None) -> list[tuple[str, str]]:
    """List image/design files in a public Drive folder. Returns [(url, name)].

    Requires a Google API key with the Drive API enabled — Drive has no
    unauthenticated folder-listing endpoint.
    """
    m = _DRIVE_FOLDER.search(url)
    if not m:
        raise FetchError("Not a Google Drive folder link")
    if not api_key:
        raise FetchError(
            "Drive folder import needs GOOGLE_API_KEY (Drive API enabled) in the environment."
        )

    folder_id = m.group(1)
    out: list[tuple[str, str]] = []
    page_token: str | None = None

    with httpx.Client(timeout=settings.fetch_timeout_s) as client:
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed=false",
                "key": api_key,
                "fields": "nextPageToken,files(id,name,mimeType)",
                "pageSize": "200",
            }
            if page_token:
                params["pageToken"] = page_token
            resp = client.get("https://www.googleapis.com/drive/v3/files", params=params)
            resp.raise_for_status()
            payload = resp.json()
            for f in payload.get("files", []):
                mime = f.get("mimeType", "")
                if mime.startswith("image/") or mime in _EXT_BY_MIME:
                    out.append(
                        (f"https://drive.google.com/uc?export=download&id={f['id']}", f["name"])
                    )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    return out
