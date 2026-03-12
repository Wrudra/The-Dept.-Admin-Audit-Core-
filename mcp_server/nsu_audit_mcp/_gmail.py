"""Gmail helpers — thin proxy to the backend API.

All OAuth credentials live on the backend server.
The MCP only passes the user's NSU JWT; Gmail tokens are stored server-side.
"""
from typing import Optional

import httpx

from ._client import _base_url, _handle
from ._auth import load_token



def _auth_headers() -> dict:
    token = load_token()
    if not token:
        raise RuntimeError("Not authenticated. Call `nsu_oauth_start` first.")
    return {"Authorization": f"Bearer {token}"}


def start_gmail_flow() -> dict:
    """Ask the backend to start a Gmail device-auth flow."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{_base_url()}/api/gmail/authorize/start",
            headers=_auth_headers(),
        )
    return _handle(resp)


def complete_gmail_flow(device_code: str) -> None:
    """Tell the backend to poll Google and store the Gmail token."""
    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{_base_url()}/api/gmail/authorize/complete",
            headers=_auth_headers(),
            json={"device_code": device_code},
        )
    _handle(resp)


def send_report_via_backend(
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
            headers=_auth_headers(),
            json=payload,
        )
    return _handle(resp)
