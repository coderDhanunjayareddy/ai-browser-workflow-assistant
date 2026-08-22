from __future__ import annotations

import mimetypes
import os
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field


router = APIRouter(prefix="/local-files", tags=["local-file-broker"])


class ExactDownloadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)


def _downloads_root() -> Path:
    configured = os.getenv("AI_BROWSER_ASSIST_DOWNLOADS_DIR", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / "Downloads"


def _normalized_leaf(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


@router.post("/resolve-download")
def resolve_exact_download(
    payload: ExactDownloadRequest,
    x_ai_browser_assist_extension: str | None = Header(default=None),
) -> dict[str, str | int]:
    """Resolve one exact top-level Downloads file for the trusted local executor.

    The absolute path is returned only to the extension service worker. The
    side panel, planner and page never receive it.
    """
    if x_ai_browser_assist_extension != "service-worker":
        raise HTTPException(status_code=403, detail="Local file broker accepts only the extension executor.")

    requested = payload.filename.strip()
    if (
        requested in {".", ".."}
        or Path(requested).name != requested
        or "/" in requested
        or "\\" in requested
        or "\x00" in requested
    ):
        raise HTTPException(status_code=400, detail="An exact leaf filename is required.")

    root = _downloads_root().resolve(strict=False)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Downloads directory is unavailable: {root}")

    expected = _normalized_leaf(requested)
    matches: list[Path] = []
    for candidate in root.iterdir():
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if _normalized_leaf(candidate.name) != expected:
            continue
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Resolved file escaped the Downloads boundary.") from exc
        matches.append(resolved)

    if not matches:
        raise HTTPException(status_code=404, detail=f"Exact Downloads file not found: {requested}")
    if len(matches) != 1:
        raise HTTPException(status_code=409, detail=f"Exact Downloads filename is ambiguous: {requested}")

    file_path = matches[0]
    size = file_path.stat().st_size
    if size <= 0:
        raise HTTPException(status_code=409, detail=f"Downloads file is empty: {requested}")
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return {
        "absolute_path": str(file_path),
        "filename": file_path.name,
        "mime_type": mime_type,
        "size_bytes": size,
        "source": "local_downloads_broker_exact_match",
    }
