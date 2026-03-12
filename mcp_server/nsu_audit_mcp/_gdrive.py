"""Google Drive helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
The MCP only passes the user's NSU JWT; Drive tokens are stored server-side.
"""
from typing import Tuple

import httpx

from ._client import _base_url, _handle
from ._auth import load_token


def _auth_headers() -> dict:
    token = load_token()
    if not token:
        raise RuntimeError("Not authenticated. Call `nsu_oauth_start` first.")
    return {"Authorization": f"Bearer {token}"}


def start_gdrive_flow() -> dict:
    """Ask the backend to start a Drive device-auth flow.

    Returns {"user_code", "verification_url", "device_code", ...}.
    Credentials never leave the server.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_base_url()}/api/gdrive/authorize/start",
            headers=_auth_headers(),
        )
    return _handle(resp)


def complete_gdrive_flow(device_code: str) -> None:
    """Tell the backend to poll Google and store the Drive token."""
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{_base_url()}/api/gdrive/authorize/complete",
            headers=_auth_headers(),
            json={"device_code": device_code},
        )
    _handle(resp)


def gdrive_list_files(query: str = "", page_size: int = 20) -> list:
    """List Drive files via the backend."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/files",
            headers=_auth_headers(),
            params={"search": query, "page_size": page_size},
        )
    return _handle(resp)


def gdrive_download_file(file_id: str) -> Tuple[bytes, str]:
    """Download a Drive file via the backend. Returns (bytes, filename)."""
    with httpx.Client(timeout=120) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/files/{file_id}/download",
            headers=_auth_headers(),
        )
    if resp.status_code != 200:
        _handle(resp)  # raises descriptive error
    cd = resp.headers.get("content-disposition", "")
    filename = "transcript"
    if 'filename="' in cd:
        filename = cd.split('filename="')[1].rstrip('"')
    return resp.content, filename
