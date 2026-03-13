"""Google Drive helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
Functions accept an explicit ``token`` (NSU Audit JWT) so they work in both
stdio mode and hosted HTTP/SSE mode.

Authorization uses the standard OAuth 2.0 Authorization Code flow:
  - start_gdrive_flow  → GET /api/gdrive/authorize/start → returns auth_url
  - gdrive_auth_status → GET /api/gdrive/authorize/status → {"authorized": bool}
"""
from typing import Tuple

import httpx

from ._client import _base_url, _handle


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start_gdrive_flow(token: str) -> dict:
    """Ask the backend to generate a Google OAuth authorization URL.

    Returns ``{"auth_url": ..., "scope": ..., "next_step": ...}``.
    The user must open ``auth_url`` in a browser and approve Drive access.
    The backend stores the token automatically via the OAuth callback.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/authorize/start",
            headers=_headers(token),
        )
    return _handle(resp)


def gdrive_auth_status(token: str) -> dict:
    """Check whether the current user has authorized Drive access.

    Returns ``{"authorized": true/false}``.
    """
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_base_url()}/api/gdrive/authorize/status",
            headers=_headers(token),
        )
    return _handle(resp)


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
