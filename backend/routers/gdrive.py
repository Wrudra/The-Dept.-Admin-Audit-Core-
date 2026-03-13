"""Google Drive router — OAuth 2.0 Authorization Code flow + file access.

The device authorization flow is NOT used here because Google does not permit
``drive.readonly`` (or any Drive scope) in that flow — only YouTube/TV scopes
are allowed.  We use the standard Authorization Code flow instead:

  1. GET  /api/gdrive/authorize/start     — returns ``auth_url`` the user opens
  2. GET  /api/gdrive/authorize/callback  — Google redirects here; token stored
  3. GET  /api/gdrive/authorize/status    — poll to confirm authorization
  4. POST /api/gdrive/authorize/revoke    — delete stored Drive token

Works with Desktop-type OAuth 2.0 clients.  Google automatically accepts any
``http://localhost`` redirect URI for Desktop clients — no Cloud Console
registration needed for localhost.

Credentials (GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET) live only on the server.
"""
import re
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.session import get_current_claims
from ..config import settings
from ..database import get_db
from ..models.drive_token import DriveToken

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])

# ── Google API constants ──────────────────────────────────────────────────────

_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRIVE_API_BASE   = "https://www.googleapis.com/drive/v3"
_DRIVE_SCOPE      = "https://www.googleapis.com/auth/drive.readonly"

_MAX_FILE_BYTES    = 10 * 1024 * 1024   # 10 MB
_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg", "image/jpg", "image/png", "image/tiff", "image/bmp",
    "text/csv", "text/plain",
}
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# ── In-memory pending-state store {state → {user_id, exp}} ───────────────────
# Fine for a single-worker dev deployment.

_PENDING: dict[str, dict] = {}
_STATE_TTL = 600  # 10 minutes


def _redirect_uri() -> str:
    return f"{settings.backend_url}/api/gdrive/authorize/callback"


def _put_state(state: str, user_id: str) -> None:
    now = time.time()
    expired = [k for k, v in _PENDING.items() if now > v["exp"]]
    for k in expired:
        del _PENDING[k]
    _PENDING[state] = {"user_id": user_id, "exp": now + _STATE_TTL}


def _pop_state(state: str) -> Optional[str]:
    entry = _PENDING.pop(state, None)
    if not entry or time.time() > entry["exp"]:
        return None
    return entry["user_id"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_credentials() -> tuple[str, str]:
    cid = settings.gdrive_client_id.strip()
    sec = settings.gdrive_client_secret.strip()
    if not cid or not sec:
        raise HTTPException(
            503,
            "Google Drive integration is not configured. "
            "Set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET in the server environment.",
        )
    return cid, sec


async def _get_token(db: AsyncSession, user_id: str) -> Optional[str]:
    """Return a valid Drive access token, refreshing silently if needed."""
    result = await db.execute(
        select(DriveToken).where(DriveToken.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if not row or not row.access_token:
        return None

    if time.time() < row.expires_at - 60:
        return row.access_token

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


# ── Auth endpoints ────────────────────────────────────────────────────────────

@router.get("/authorize/start", summary="Start Google Drive OAuth authorization")
async def gdrive_authorize_start(
    claims: dict = Depends(get_current_claims),
) -> dict:
    """Generate a Google OAuth 2.0 URL for Drive read-only access.

    Returns ``auth_url``.  Open it in a browser and approve access.
    Google will redirect to the backend callback automatically — no further
    action needed beyond approval.  Poll ``/authorize/status`` to confirm.
    """
    cid, _ = _require_credentials()
    state = secrets.token_urlsafe(32)
    _put_state(state, claims["user_id"])

    auth_url = _GOOGLE_AUTH_URL + "?" + urlencode({
        "client_id":     cid,
        "redirect_uri":  _redirect_uri(),
        "response_type": "code",
        "scope":         _DRIVE_SCOPE,
        "state":         state,
        "access_type":   "offline",
        "prompt":        "consent",
    })

    return {
        "auth_url": auth_url,
        "scope":    "drive.readonly — read-only, no modifications",
        "next_step": (
            "Open auth_url in a browser and approve Google Drive read-only access. "
            "The backend stores the token automatically via the OAuth callback. "
            "Then call gdrive_authorize_complete to confirm."
        ),
    }


@router.get("/authorize/callback", summary="OAuth callback — Google redirects here")
async def gdrive_authorize_callback(
    code:  str = Query(...),
    state: str = Query(...),
    db:    AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Receive the authorization code from Google and exchange it for tokens.

    Called automatically by Google after the user approves Drive access.
    """
    user_id = _pop_state(state)
    if not user_id:
        return HTMLResponse(
            "<h2 style='font-family:sans-serif;color:#c00'>Authorization failed</h2>"
            "<p style='font-family:sans-serif'>Invalid or expired state. "
            "Please start the authorization again.</p>",
            status_code=400,
        )

    cid, sec = _require_credentials()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type":   "authorization_code",
                "code":          code,
                "redirect_uri":  _redirect_uri(),
                "client_id":     cid,
                "client_secret": sec,
            },
        )

    if resp.status_code != 200:
        return HTMLResponse(
            f"<h2 style='font-family:sans-serif;color:#c00'>Authorization failed</h2>"
            f"<p style='font-family:sans-serif'>{resp.text}</p>",
            status_code=502,
        )

    tok = resp.json()
    result = await db.execute(
        select(DriveToken).where(DriveToken.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = DriveToken(user_id=user_id)
        db.add(row)
    row.access_token  = tok["access_token"]
    row.refresh_token = tok.get("refresh_token") or row.refresh_token
    row.expires_at    = time.time() + tok.get("expires_in", 3600)
    await db.commit()

    return HTMLResponse(
        "<h2 style='font-family:sans-serif;color:#1a7a1a'>Google Drive authorized ✓</h2>"
        "<p style='font-family:sans-serif'>"
        "Read-only access granted. You can close this tab.</p>"
    )


@router.get("/authorize/status", summary="Check Drive authorization status")
async def gdrive_authorize_status(
    claims: dict         = Depends(get_current_claims),
    db:     AsyncSession = Depends(get_db),
) -> dict:
    """Return whether the current user has a valid Drive token stored."""
    token = await _get_token(db, claims["user_id"])
    return {"authorized": token is not None}


@router.post("/authorize/revoke", summary="Revoke Drive authorization")
async def gdrive_authorize_revoke(
    claims: dict         = Depends(get_current_claims),
    db:     AsyncSession = Depends(get_db),
) -> dict:
    """Delete the stored Drive token for the current user."""
    result = await db.execute(
        select(DriveToken).where(DriveToken.user_id == claims["user_id"])
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"ok": True, "message": "Drive authorization revoked."}


# ── File endpoints ────────────────────────────────────────────────────────────

@router.get("/files", summary="List Drive transcript files")
async def gdrive_list_files(
    search:    str = Query(default="", description="Optional filename search"),
    page_size: int = Query(default=20, ge=1, le=100),
    claims:    dict         = Depends(get_current_claims),
    db:        AsyncSession = Depends(get_db),
) -> list:
    """List PDF and image files in the user's Google Drive.

    Requires prior Drive authorization.  Results ordered by most recently modified.
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
    """Download a file from Google Drive and return raw bytes.

    Validates file ID format, MIME type, and size (max 10 MB).
    """
    if not _FILE_ID_RE.match(file_id):
        raise HTTPException(400, "Invalid Drive file ID format.")

    user_id = claims["user_id"]
    token   = await _get_token(db, user_id)
    if not token:
        raise HTTPException(401, "Drive not authorized.")

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
            "Accepted: PDF, CSV, JPEG, PNG, TIFF, BMP.",
        )
    if file_size > _MAX_FILE_BYTES:
        raise HTTPException(
            413,
            f"File is {file_size / 1024 / 1024:.1f} MB; maximum is 10 MB.",
        )

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
