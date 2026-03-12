"""Gmail helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
Functions accept an explicit ``token`` (NSU Audit JWT) so they work in both
stdio mode and hosted HTTP/SSE mode without touching the local credentials file.
"""
from typing import Optional

import httpx

from ._client import _base_url, _handle


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def start_gmail_flow(token: str) -> dict:
    """Ask the backend to start a Gmail device-auth flow."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_base_url()}/api/gmail/authorize/start",
            headers=_headers(token),
        )
    return _handle(resp)


def complete_gmail_flow(token: str, device_code: str) -> None:
    """Tell the backend to poll Google and store the Gmail token."""
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{_base_url()}/api/gmail/authorize/complete",
            headers=_headers(token),
            json={"device_code": device_code},
        )
    _handle(resp)


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
