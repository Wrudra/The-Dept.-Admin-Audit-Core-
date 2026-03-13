"""Thin httpx wrapper around the NSU Audit backend REST API.

The base URL is read from the NSU_AUDIT_BASE_URL environment variable,
defaulting to http://localhost:8000.

All API helpers now take an explicit ``token`` string so they work correctly
in hosted HTTP/SSE mode where the JWT comes from per-session FastMCP state
rather than a local credentials file.

All methods raise RuntimeError with a human-readable message on API errors
so that tool functions can surface them directly to the LLM.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from fastmcp import Context

_BASE_URL_ENV     = "NSU_AUDIT_BASE_URL"
_DEFAULT_BASE_URL = "http://localhost:8000"


def _base_url() -> str:
    url = os.environ.get(_BASE_URL_ENV, _DEFAULT_BASE_URL).rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise ValueError(
            f"NSU_AUDIT_BASE_URL must start with http:// or https://, got: {url!r}"
        )
    if url.startswith("http://"):
        host = url[len("http://"):].split("/")[0].split(":")[0]
        if host not in ("localhost", "127.0.0.1", "::1"):
            if not os.environ.get("NSU_AUDIT_ALLOW_HTTP"):
                raise ValueError(
                    f"NSU_AUDIT_BASE_URL uses plain HTTP for a non-local host ({host!r}). "
                    "Set it to an https:// URL to avoid transmitting your session token "
                    "in plaintext. If this is intentional for local development, "
                    "set NSU_AUDIT_ALLOW_HTTP=1 to override."
                )
    return url


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def get_token_or_raise(ctx: "Context") -> str:
    """Extract the JWT from session state or disk; raise if missing."""
    from ._auth import get_token
    token = await get_token(ctx)
    if not token:
        raise RuntimeError(
            "Not authenticated. Call the `nsu_oauth_start` tool first."
        )
    return token


def _handle(resp: httpx.Response) -> Any:
    """Raise a descriptive RuntimeError for any non-2xx response."""
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        if resp.status_code == 401:
            # Surface the actual backend message so the AI can distinguish
            # "NSU session expired" from "Drive not authorized", etc.
            raise RuntimeError(f"Unauthorized: {detail}")
        if resp.status_code == 403:
            raise RuntimeError(f"Forbidden: {detail}")
        if resp.status_code == 404:
            raise RuntimeError("Resource not found.")
        if resp.status_code == 429:
            raise RuntimeError(
                "Rate limit exceeded (max 5 audits / 60 s). Wait a moment and try again."
            )
        raise RuntimeError(f"API error {resp.status_code}: {detail}")
    return resp.json()


def api_get(path: str, token: str) -> Any:
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_base_url()}{path}", headers=_auth_headers(token))
    return _handle(resp)


def api_post(path: str, token: str = "", *, auth: bool = True, **kwargs) -> Any:
    headers = _auth_headers(token) if auth else {}
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{_base_url()}{path}", headers=headers, **kwargs)
    return _handle(resp)


def api_delete(path: str, token: str) -> Any:
    with httpx.Client(timeout=30) as client:
        resp = client.delete(f"{_base_url()}{path}", headers=_auth_headers(token))
    return _handle(resp)
