"""Google Drive router — server-side device flow + file access.

Credentials (GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET) live only on the server.
Users never see or need them; they just approve access in their own browser.

Per-user Drive tokens are stored as encrypted JSON in the drive_tokens table.
Access is strictly read-only (drive.readonly scope).
"""
import json
import re
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.session import get_current_claims
from ..config import settings
from ..database import get_db
from ..models.drive_token import DriveToken

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])

# ── Google API constants ──────────────────────────────────────────────────────

_GOOGLE_DEVICE_URL = "https://oauth2.googleapis.com/device/code"
_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_DRIVE_API_BASE    = "https://www.googleapis.com/drive/v3"
_DEVICE_GRANT      = "urn:ietf:params:oauth:grant-type:device_code"
_DRIVE_SCOPE       = "https://www.googleapis.com/auth/drive.readonly"

_MAX_FILE_BYTES    = 10 * 1024 * 1024   # 10 MB
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png", "image/tiff", "image/bmp",
    "text/csv", "text/plain",
}
# Drive file IDs are URL-safe base64 characters.
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

_MAX_POLL_ATTEMPTS = 20   # 20 × 5 s = up to 100 s


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_credentials() -> tuple[str, str]:
    cid = settings.gdrive_client_id.strip()
    sec = settings.gdrive_client_secret.strip()
    if not cid or not sec:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Drive integration is not configured on this server. "
                "Contact the administrator."
            ),
        )
    return cid, sec


async def _get_token(db: AsyncSession, user_id: str) -> Optional[str]:
    """Return a valid Drive access token for the user, refreshing if needed."""
    result = await db.execute(
        select(DriveToken).where(DriveToken.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return None

    # Still valid (with 60-second buffer)
    if time.time() < row.expires_at - 60:
        return row.access_token

    # Attempt silent refresh
    if not row.refresh_token:
        return None

    cid, sec = _require_credentials()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "refresh_token": row.refresh_token,
                "client_id":     cid,
                "client_secret": sec,
            },
        )
    if resp.status_code != 200:
        return None

    tok = resp.json()
    row.access_token = tok["access_token"]
    row.expires_at   = time.time() + tok.get("expires_in", 3600)
    await db.commit()
    return row.access_token


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/authorize/start", summary="Start Google Drive device flow")
async def gdrive_authorize_start(
    claims: dict = Depends(get_current_claims),
) -> dict:
    """Start the Device Authorization flow for Google Drive read-only access.

    Returns ``user_code`` and ``verification_url``.  The user opens the URL
    in their browser, enters the code, and approves read-only Drive access.
    Then call ``/api/gdrive/authorize/complete``.

    OAuth credentials never leave the server.
    """
    cid, _ = _require_credentials()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _GOOGLE_DEVICE_URL,
            data={"client_id": cid, "scope": _DRIVE_SCOPE},
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"Failed to start Drive authorization: {resp.text}")

    data = resp.json()
    # Store device_code temporarily in the response — client echoes it back.
    return {
        "user_code":        data["user_code"],
        "verification_url": data["verification_url"],
        "device_code":      data["device_code"],
        "interval":         data.get("interval", 5),
        "expires_in":       data.get("expires_in", 1800),
        "scope":            "drive.readonly — read-only access, no modifications",
    }


class CompleteRequest(BaseModel):
    device_code: str


@router.post("/authorize/complete", summary="Complete Google Drive device flow")
async def gdrive_authorize_complete(
    body:   CompleteRequest,
    claims: dict         = Depends(get_current_claims),
    db:     AsyncSession = Depends(get_db),
) -> dict:
    """Poll Google for the Drive access token after the user approved in browser.

    Call this after ``/api/gdrive/authorize/start``.  Pass the ``device_code``
    returned by start.  Polls up to 100 seconds; if pending, call again.
    """
    cid, sec = _require_credentials()
    user_id  = claims["user_id"]

    for _ in range(_MAX_POLL_ATTEMPTS):
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "grant_type":  _DEVICE_GRANT,
                    "device_code": body.device_code,
                    "client_id":   cid,
                    "client_secret": sec,
                },
            )
        if resp.status_code == 200:
            tok = resp.json()
            # Upsert DriveToken row for this user
            result = await db.execute(
                select(DriveToken).where(DriveToken.user_id == user_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                row = DriveToken(user_id=user_id)
                db.add(row)
            row.access_token  = tok["access_token"]
            row.refresh_token = tok.get("refresh_token", "")
            row.expires_at    = time.time() + tok.get("expires_in", 3600)
            await db.commit()
            return {"ok": True, "message": "Google Drive read-only access granted."}

        err = resp.json().get("error", "")
        if err == "authorization_pending":
            await _async_sleep(5)
            continue
        if err == "slow_down":
            await _async_sleep(10)
            continue
        raise HTTPException(400, f"Drive authorization failed: {err}")

    raise HTTPException(
        408,
        "Timed out waiting for Drive authorization. "
        "Approve in the browser first, then call this endpoint again.",
    )


@router.get("/files", summary="List Drive transcript files")
async def gdrive_list_files(
    search:    str = Query(default="", description="Optional filename search"),
    page_size: int = Query(default=20, ge=1, le=100),
    claims:    dict         = Depends(get_current_claims),
    db:        AsyncSession = Depends(get_db),
) -> list:
    """List PDF and image files in the user's Google Drive.

    Requires prior ``/api/gdrive/authorize/start`` + ``complete`` flow.
    Results ordered by most recently modified.
    """
    user_id = claims["user_id"]
    token   = await _get_token(db, user_id)
    if not token:
        raise HTTPException(
            401,
            "Drive not authorized. Call /api/gdrive/authorize/start first.",
        )

    mime_filter = " or ".join(
        f"mimeType='{m}'" for m in sorted(_ALLOWED_MIME_TYPES)
    )
    q = f"({mime_filter}) and trashed=false"
    if search.strip():
        safe = search.replace("'", "\\'")
        q = f"name contains '{safe}' and ({mime_filter}) and trashed=false"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{_DRIVE_API_BASE}/files",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "q":        q,
                "pageSize": page_size,
                "fields":   "files(id,name,mimeType,size,modifiedTime)",
                "orderBy":  "modifiedTime desc",
            },
        )
    if resp.status_code == 401:
        raise HTTPException(401, "Drive token expired. Re-authorize via /api/gdrive/authorize/start.")
    if resp.status_code != 200:
        raise HTTPException(502, f"Drive API error: {resp.text}")

    return resp.json().get("files", [])


@router.get("/files/{file_id}/download", summary="Download a Drive file")
async def gdrive_download_file(
    file_id: str,
    claims:  dict         = Depends(get_current_claims),
    db:      AsyncSession = Depends(get_db),
) -> Response:
    """Download a file from Google Drive and return it as raw bytes.

    Validates file ID format, MIME type, and size (max 10 MB).
    The MCP or backend audit endpoint calls this to retrieve the transcript.
    """
    if not _FILE_ID_RE.match(file_id):
        raise HTTPException(400, "Invalid Drive file ID format.")

    user_id = claims["user_id"]
    token   = await _get_token(db, user_id)
    if not token:
        raise HTTPException(401, "Drive not authorized.")

    # Get file metadata first
    async with httpx.AsyncClient(timeout=15) as client:
        meta = await client.get(
            f"{_DRIVE_API_BASE}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id,name,mimeType,size"},
        )
    if meta.status_code == 404:
        raise HTTPException(404, "File not found in Google Drive.")
    if meta.status_code != 200:
        raise HTTPException(502, f"Drive metadata error: {meta.text}")

    info      = meta.json()
    mime_type = info.get("mimeType", "")
    file_size = int(info.get("size", 0))
    filename  = info.get("name", "transcript")

    if mime_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type '{mime_type}'. "
            f"Accepted: PDF, CSV, JPEG, PNG, TIFF, BMP.",
        )
    if file_size > _MAX_FILE_BYTES:
        raise HTTPException(
            413,
            f"File is {file_size / 1024 / 1024:.1f} MB; maximum is 10 MB.",
        )

    # Download file content
    async with httpx.AsyncClient(timeout=60) as client:
        dl = await client.get(
            f"{_DRIVE_API_BASE}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"alt": "media"},
        )
    if dl.status_code != 200:
        raise HTTPException(502, f"Drive download error: {dl.text}")

    return Response(
        content=dl.content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Tiny async sleep (avoids blocking the event loop) ────────────────────────

async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)
