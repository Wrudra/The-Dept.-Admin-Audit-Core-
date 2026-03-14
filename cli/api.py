"""HTTP client wrapper for the NSU Audit backend API."""
import json
from pathlib import Path
from typing import Optional

import httpx

_DEFAULT_TIMEOUT = 120  # audit runs can take a while (OCR etc.)


def api_get(api_url: str, path: str, token: str, **params) -> dict:
    """Authenticated GET request; raises on HTTP error."""
    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        resp = client.get(
            f"{api_url}{path}",
            params=params or None,
            headers={"Authorization": f"Bearer {token}"},
        )
    _raise(resp)
    return resp.json()


def api_post_json(api_url: str, path: str, token: str, body: dict) -> dict:
    """Authenticated POST with a JSON body."""
    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        resp = client.post(
            f"{api_url}{path}",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
    _raise(resp)
    return resp.json()


def api_post_multipart(
    api_url:    str,
    path:       str,
    token:      str,
    csv_path:   Path,
    program:    str,
    answers:    dict,
    save:       bool = True,
    source:     str  = "cli",
) -> dict:
    """POST a CSV file + metadata to the audit run endpoint."""
    with open(csv_path, "rb") as fh:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.post(
                f"{api_url}{path}",
                files={"transcript": (csv_path.name, fh, "text/csv")},
                data={
                    "program": program,
                    "answers": json.dumps(answers),
                    "save":    "true" if save else "false",
                    "source":  source,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
    _raise(resp)
    return resp.json()


def api_delete(api_url: str, path: str, token: str) -> dict:
    with httpx.Client(timeout=30) as client:
        resp = client.delete(
            f"{api_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    _raise(resp)
    return resp.json()


def _raise(resp: httpx.Response) -> None:
    """Raise a user-friendly error on HTTP 4xx/5xx."""
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise httpx.HTTPStatusError(
            f"API error {resp.status_code}: {detail}",
            request=resp.request,
            response=resp,
        )
