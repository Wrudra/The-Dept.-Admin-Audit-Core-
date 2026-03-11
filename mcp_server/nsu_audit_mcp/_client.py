"""Thin httpx wrapper around the NSU Audit backend REST API.

The base URL is read from the NSU_AUDIT_BASE_URL environment variable,
defaulting to http://localhost:8000.

All methods raise RuntimeError with a human-readable message on API errors
so that tool functions can surface them directly to the LLM.
"""
import os
from typing import Any

import httpx

from ._auth import load_token

_BASE_URL_ENV     = "NSU_AUDIT_BASE_URL"
_DEFAULT_BASE_URL = "http://localhost:8000"


def _base_url() -> str:
    url = os.environ.get(_BASE_URL_ENV, _DEFAULT_BASE_URL).rstrip("/")
    # SSRF guard: only allow http/https scheme.
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"NSU_AUDIT_BASE_URL must start with http:// or https://, got: {url!r}"
        )
    # Warn when HTTP is used outside localhost — JWT Bearer token would be sent
    # in plaintext over the network.
    if url.startswith("http://"):
        host = url[len("http://"):].split("/")[0].split(":")[0]
        if host not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError(
                f"NSU_AUDIT_BASE_URL uses plain HTTP for a non-local host ({host!r}). "
                "Set it to an https:// URL to avoid transmitting your session token "
                "in plaintext. If this is intentional for local development, "
                "set NSU_AUDIT_ALLOW_HTTP=1 to override."
            ) if not os.environ.get("NSU_AUDIT_ALLOW_HTTP") else None
    return url


def _auth_headers() -> dict:
    token = load_token()
    if not token:
        raise RuntimeError("Not authenticated. Call the `login` tool first.")
    return {"Authorization": f"Bearer {token}"}


def _handle(resp: httpx.Response) -> Any:
    """Raise a descriptive RuntimeError for any non-2xx response."""
    if resp.status_code == 401:
        raise RuntimeError(
            "Session expired or invalid. Call `login` and `login_complete` again."
        )
    if resp.status_code == 403:
        raise RuntimeError("Forbidden. You don't have permission for this action.")
    if resp.status_code == 404:
        raise RuntimeError("Resource not found.")
    if resp.status_code == 429:
        raise RuntimeError(
            "Rate limit exceeded (max 5 audits / 60 s). Wait a moment and try again."
        )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"API error {resp.status_code}: {detail}")
    return resp.json()


def api_get(path: str) -> Any:
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_base_url()}{path}", headers=_auth_headers())
    return _handle(resp)


def api_post(path: str, *, auth: bool = True, **kwargs) -> Any:
    headers = _auth_headers() if auth else {}
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{_base_url()}{path}", headers=headers, **kwargs)
    return _handle(resp)


def api_delete(path: str) -> Any:
    with httpx.Client(timeout=30) as client:
        resp = client.delete(f"{_base_url()}{path}", headers=_auth_headers())
    return _handle(resp)
