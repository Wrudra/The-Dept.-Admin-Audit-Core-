"""Google Drive helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
Functions accept an explicit ``token`` (NSU Audit JWT) so they work in both
stdio mode and hosted HTTP/SSE mode without touching the local credentials file.
"""
from typing import Tuple

import httpx

from ._client import _base_url, _handle


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start_gdrive_flow(token: str) -> dict:
    """Ask the backend to start a Drive device-auth flow.

    Returns {"user_code", "verification_url", "device_code", ...}.
    Credentials never leave the server.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_base_url()}/api/gdrive/authorize/start",
            headers=_headers(token),
        )
    return _handle(resp)


def complete_gdrive_flow(token: str, device_code: str) -> None:
    """Tell the backend to poll Google and store the Drive token."""
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{_base_url()}/api/gdrive/authorize/complete",
            headers=_headers(token),
            json={"device_code": device_code},
        )
    _handle(resp)


def gdrive_list_files(token: str, query: str = "", page_size: int = 20) -> list:
    """List Drive files via the backend."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/files",
            headers=_headers(token),
            params={"search": query, "page_size": page_size},
        )
    return _handle(resp)


def gdrive_download_file(token: str, file_id: str) -> Tuple[bytes, str]:
    """Download a Drive file via the backend. Returns (bytes, filename)."""
    with httpx.Client(timeout=120) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/files/{file_id}/download",
            headers=_headers(token),
        )
    if resp.status_code != 200:
        _handle(resp)
    cd = resp.headers.get("content-disposition", "")
    filename = "transcript"
    if 'filename="' in cd:
        filename = cd.split('filename="')[1].rstrip('"')
    return resp.content, filename
