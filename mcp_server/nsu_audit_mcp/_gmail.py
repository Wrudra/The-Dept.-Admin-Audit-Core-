"""Gmail helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
Functions accept an explicit ``token`` (NSU Audit JWT) so they work in both
stdio mode and hosted HTTP/SSE mode.

Authorization uses the standard OAuth 2.0 Authorization Code flow:
  - start_gmail_flow  → GET /api/gmail/authorize/start → returns auth_url
  - gmail_auth_status → GET /api/gmail/authorize/status → {"authorized": bool}
"""
from typing import Optional

import httpx

from ._client import _base_url, _handle


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start_gmail_flow(token: str) -> dict:
    """Ask the backend to generate a Google OAuth authorization URL for Gmail.

    Returns ``{"auth_url": ..., "scope": ..., "next_step": ...}``.
    The user must open ``auth_url`` in a browser and approve Gmail send access.
    The backend stores the token automatically via the OAuth callback.
    """
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{_base_url()}/api/gmail/authorize/start",
            headers=_headers(token),
        )
    return _handle(resp)


def gmail_auth_status(token: str) -> dict:
    """Check whether the current user has authorized Gmail access.

    Returns ``{"authorized": true/false}``.
    """
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{_base_url()}/api/gmail/authorize/status",
            headers=_headers(token),
        )
    return _handle(resp)


def send_report_via_backend(
    token: str,
    run_id: str,
    to: str,
    subject: Optional[str] = None,
) -> dict:
    """Ask the backend to build the Excel report and email it."""
    payload: dict = {"run_id": run_id, "to": to}
    if subject:
        payload["subject"] = subject
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{_base_url()}/api/gmail/send-report",
            headers=_headers(token),
            json=payload,
        )
    return _handle(resp)
