"""Raw snapshot storage.

Every byte a source returns is written to ``data/raw/<source>/<YYYY-MM-DD>/`` next to a
``manifest.json`` recording the URL, the SHA-256 and the fetch timestamp, *before* anything
parses it. Builds are therefore reproducible from the repository alone — which matters here
because several of the upstream portals go offline for days at a time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from transporte_sp.config import settings

log = logging.getLogger(__name__)


def snapshot_dir(source: str, on: date | None = None) -> Path:
    return settings.raw_dir / source / (on or _today()).isoformat()


def _today() -> date:
    return datetime.now(UTC).date()


def latest_snapshot(source: str) -> Path | None:
    """The most recent snapshot directory for *source*, or ``None`` if never fetched."""
    root = settings.raw_dir / source
    if not root.is_dir():
        return None
    dated = sorted(path for path in root.iterdir() if path.is_dir())
    return dated[-1] if dated else None


def write(source: str, filename: str, payload: bytes, url: str, licence: str) -> Path:
    """Store *payload* as today's snapshot of *source* and append it to the manifest."""
    directory = snapshot_dir(source)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    target.write_bytes(payload)

    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest[filename] = {
        "url": url,
        "licence": licence,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    log.info("%s: stored %s (%.1f KB)", source, filename, len(payload) / 1024)
    return target


def read(source: str, filename: str) -> bytes:
    """Read *filename* from the latest snapshot of *source*."""
    directory = latest_snapshot(source)
    if directory is None:
        raise FileNotFoundError(f"no snapshot for {source!r}; run `transporte-sp fetch` first")
    target = directory / filename
    if not target.exists():
        raise FileNotFoundError(f"{target} missing from the {source!r} snapshot")
    return target.read_bytes()


def manifest(source: str) -> dict[str, dict]:
    directory = latest_snapshot(source)
    if directory is None:
        return {}
    path = directory / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else {}


def fetched_on(source: str) -> date:
    directory = latest_snapshot(source)
    return date.fromisoformat(directory.name) if directory else _today()


def download(
    url: str,
    *,
    method: str = "GET",
    params: dict | None = None,
    data: str | bytes | None = None,
    headers: dict | None = None,
) -> bytes:
    """Fetch *url* with retries. Raises on a non-2xx response after the last attempt."""
    request_headers = {"User-Agent": settings.user_agent} | (headers or {})
    last_error: Exception | None = None
    for attempt in range(1, settings.http_retries + 1):
        try:
            with httpx.Client(timeout=settings.http_timeout, follow_redirects=True) as client:
                response = client.request(
                    method, url, params=params, content=data, headers=request_headers
                )
            response.raise_for_status()
            return response.content
        except Exception as error:  # noqa: BLE001 - retried below, re-raised on exhaustion
            last_error = error
            log.warning("%s attempt %d/%d failed: %s", url, attempt, settings.http_retries, error)
    raise RuntimeError(f"failed to download {url}") from last_error
