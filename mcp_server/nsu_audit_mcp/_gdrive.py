"""Google Drive OAuth (device flow, drive.readonly scope) + file access helpers.

Requires two environment variables from a Google Cloud project
with the Drive API enabled and a Desktop-app OAuth2 client:
  GDRIVE_CLIENT_ID     — OAuth 2.0 client ID
  GDRIVE_CLIENT_SECRET — OAuth 2.0 client secret

Credentials are stored at ~/.config/nsu-audit-mcp/gdrive_credentials.json
with mode 0600.  Access is strictly read-only; the scope never escalates.
"""
import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Optional, Tuple

import httpx

_GDRIVE_DIR     = Path.home() / ".config" / "nsu-audit-mcp"
_GDRIVE_CREDS   = _GDRIVE_DIR / "gdrive_credentials.json"
_GDRIVE_PENDING = _GDRIVE_DIR / "gdrive_pending.json"

_GOOGLE_DEVICE_URL = "https://oauth2.googleapis.com/device/code"
_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_DRIVE_API_BASE    = "https://www.googleapis.com/drive/v3"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Strictly read-only — never request write access.
_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

_MAX_POLL_ATTEMPTS = 12   # 12 × 5 s = up to 60 s
_MAX_FILE_BYTES    = 10 * 1024 * 1024  # 10 MB — mirrors backend limit

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "text/csv",
    "text/plain",
}

# Google Drive file IDs are URL-safe base64 characters plus hyphens/underscores.
_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _write_secure(path: Path, data: dict) -> None:
    """Write JSON and set permissions to owner-only (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _client_creds() -> Tuple[str, str]:
    client_id     = os.environ.get("GDRIVE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Google Drive is not configured. "
            "Set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET environment variables "
            "from a Google Cloud project with the Drive API enabled "
            "(OAuth client type: Desktop app)."
        )
    return client_id, client_secret


def _refresh_access_token(refresh_token: str, current: dict) -> Optional[str]:
    """Silently refresh the Drive access token using the stored refresh token."""
    try:
        client_id, client_secret = _client_creds()
    except RuntimeError:
        return None
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
                "client_id":     client_id,
                "client_secret": client_secret,
            },
        )
    if resp.status_code != 200:
        return None
    new_tok = resp.json()
    current["access_token"] = new_tok["access_token"]
    current["expires_at"]   = time.time() + new_tok.get("expires_in", 3600)
    _write_secure(_GDRIVE_CREDS, current)
    return current["access_token"]


# ── Public interface ──────────────────────────────────────────────────────────

def load_gdrive_token() -> Optional[str]:
    """Return a valid Drive access token, auto-refreshing if needed."""
    if not _GDRIVE_CREDS.exists():
        return None
    try:
        data = json.loads(_GDRIVE_CREDS.read_text())
    except Exception:
        return None
    # Return current token if still valid (with 60-second buffer).
    if time.time() < data.get("expires_at", 0) - 60:
        return data.get("access_token")
    # Attempt silent refresh.
    refresh = data.get("refresh_token")
    if refresh:
        return _refresh_access_token(refresh, data)
    return None


def start_gdrive_flow() -> dict:
    """Start the device authorization flow for drive.readonly.

    Returns {"user_code": ..., "verification_url": ...}.
    Pending state is saved securely to disk for complete_gdrive_flow().
    """
    client_id, _ = _client_creds()
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            _GOOGLE_DEVICE_URL,
            data={"client_id": client_id, "scope": _DRIVE_SCOPE},
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Failed to start Google Drive authorization: {resp.text}"
        )
    data = resp.json()
    _write_secure(_GDRIVE_PENDING, data)
    return {
        "user_code":        data["user_code"],
        "verification_url": data["verification_url"],
    }


def complete_gdrive_flow() -> None:
    """Poll Google for the Drive access token and save credentials.

    Polls up to _MAX_POLL_ATTEMPTS times. Raises RuntimeError if the user
    has not yet authorized in the browser, with instructions to retry.
    """
    if not _GDRIVE_PENDING.exists():
        raise RuntimeError(
            "No pending Drive authorization. Call `gdrive_authorize` first."
        )
    pending = json.loads(_GDRIVE_PENDING.read_text())
    client_id, client_secret = _client_creds()

    device_code = pending["device_code"]
    interval    = int(pending.get("interval", 5))
    expires_in  = int(pending.get("expires_in", 1800))
    deadline    = time.time() + expires_in

    for _ in range(_MAX_POLL_ATTEMPTS):
        if time.time() > deadline:
            _GDRIVE_PENDING.unlink(missing_ok=True)
            raise RuntimeError(
                "Drive authorization session expired. Call `gdrive_authorize` again."
            )
        time.sleep(interval)
        with httpx.Client(timeout=15) as client:
            poll = client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "grant_type":    _DEVICE_GRANT_TYPE,
                    "device_code":   device_code,
                    "client_id":     client_id,
                    "client_secret": client_secret,
                },
            )
        if poll.status_code == 200:
            tok = poll.json()
            _write_secure(_GDRIVE_CREDS, {
                "access_token":  tok["access_token"],
                "refresh_token": tok.get("refresh_token"),
                "expires_at":    time.time() + tok.get("expires_in", 3600),
            })
            _GDRIVE_PENDING.unlink(missing_ok=True)
            return

        err = (poll.json() or {}).get("error", "")
        if err == "slow_down":
            interval += 5
        elif err not in ("authorization_pending",):
            _GDRIVE_PENDING.unlink(missing_ok=True)
            raise RuntimeError(f"Drive authorization error from Google: {err}")

    raise RuntimeError(
        "Drive authorization is taking too long. "
        "Ensure you have entered the code at the verification URL and approved "
        "access, then call `gdrive_authorize_complete` again."
    )


def gdrive_list_files(query: str = "", page_size: int = 20) -> list:
    """List PDF/image files in the user's Drive.

    If query is provided, restricts results to files whose names contain that string.
    Otherwise lists PDFs and images ordered by most-recently modified.
    """
    token = load_gdrive_token()
    if not token:
        raise RuntimeError(
            "Not authorized for Google Drive. Call `gdrive_authorize` first."
        )

    if query:
        # Sanitize: escape backslashes then single quotes to prevent Drive query injection.
        safe_q = query.replace("\\", "\\\\").replace("'", "\\'")
        q = f"name contains '{safe_q}' and trashed=false"
    else:
        q = (
            "(mimeType='application/pdf' or mimeType contains 'image/') "
            "and trashed=false"
        )

    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_DRIVE_API_BASE}/files",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "q":        q,
                "pageSize": min(int(page_size), 100),
                "fields":   "files(id,name,mimeType,size,modifiedTime)",
                "orderBy":  "modifiedTime desc",
            },
        )

    if resp.status_code == 401:
        raise RuntimeError(
            "Google Drive token expired or revoked. Call `gdrive_authorize` again."
        )
    resp.raise_for_status()
    return resp.json().get("files", [])


def gdrive_download_file(file_id: str) -> Tuple[bytes, str]:
    """Download a file from Google Drive by its ID.

    Returns (raw_bytes, filename).
    Validates the file ID format, MIME type (PDF/image/CSV only), and size (<= 10 MB)
    before transferring any content.
    """
    # Validate file ID: only safe characters allowed.
    if not _FILE_ID_RE.match(file_id):
        raise ValueError(f"Invalid Google Drive file ID: {file_id!r}")

    token = load_gdrive_token()
    if not token:
        raise RuntimeError(
            "Not authorized for Google Drive. Call `gdrive_authorize` first."
        )

    # Fetch metadata first to check type and size before downloading.
    with httpx.Client(timeout=20) as client:
        meta_resp = client.get(
            f"{_DRIVE_API_BASE}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id,name,mimeType,size"},
        )
    if meta_resp.status_code == 401:
        raise RuntimeError("Drive token expired. Call `gdrive_authorize` again.")
    if meta_resp.status_code == 404:
        raise RuntimeError(f"File not found in Google Drive: {file_id!r}")
    meta_resp.raise_for_status()

    meta = meta_resp.json()
    mime = meta.get("mimeType", "")
    name = meta.get("name", "transcript.pdf")
    # Drive omits 'size' for Google Docs native formats; treat as 0 (will be checked after download).
    size = int(meta.get("size", 0)) if str(meta.get("size", "0")).isdigit() else 0

    if mime not in _ALLOWED_MIME_TYPES:
        raise ValueError(
            f"File type '{mime}' is not a supported transcript format. "
            "Supported: PDF, JPEG, PNG, TIFF, BMP, or CSV."
        )
    if size > _MAX_FILE_BYTES:
        raise ValueError(
            f"File is {size / 1024 / 1024:.1f} MB; maximum is 10 MB."
        )

    # Download file content.
    with httpx.Client(timeout=120) as client:
        dl = client.get(
            f"{_DRIVE_API_BASE}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"alt": "media"},
        )
    dl.raise_for_status()

    # Final size guard — in case size was 0 from metadata.
    if len(dl.content) > _MAX_FILE_BYTES:
        raise ValueError(
            f"Downloaded file is {len(dl.content) / 1024 / 1024:.1f} MB; maximum is 10 MB."
        )

    return dl.content, name
