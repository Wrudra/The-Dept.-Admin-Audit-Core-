"""Credential storage for the NSU Audit MCP server.

Stdio mode  : tokens are persisted to ~/.config/nsu-audit-mcp/credentials.json
              (mode 0600) so they survive across sessions.
Hosted mode : tokens are stored in FastMCP session state (ctx.set_state), which
              is isolated per connected client.  Disk writes still happen as a
              secondary fallback so stdio mode continues to work unchanged.
"""
from __future__ import annotations

import base64
import json
import os
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from fastmcp import Context

_CREDS_DIR    = Path.home() / ".config" / "nsu-audit-mcp"
_CREDS_FILE   = _CREDS_DIR / "credentials.json"
_PENDING_FILE = _CREDS_DIR / "pending_device.json"

_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

# Poll up to 6 × interval seconds before giving up and asking user to retry.
_MAX_POLL_ATTEMPTS = 6


# ── Credential file helpers ────────────────────────────────────────────────────

def _write_secure(path: Path, data: dict) -> None:
    """Write JSON to a file and lock permissions to owner-only (0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _jwt_is_expired(token: str) -> bool:
    """Return True if the JWT exp claim is in the past (with a 30-second buffer)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return True
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + "=" * padding)
        )
        exp = payload.get("exp")
        if exp is None:
            return False   # no exp claim — let the server decide
        return time.time() > (exp - 30)
    except Exception:
        return False   # if we can't parse, let the server reject it


def load_token() -> Optional[str]:
    """Return the stored API JWT if it exists and has not yet expired.

    Returns None (as if not logged in) when the token is expired so callers
    get a clear 'not authenticated' error instead of a confusing 401 from
    the backend.
    """
    if not _CREDS_FILE.exists():
        return None
    try:
        token = json.loads(_CREDS_FILE.read_text()).get("access_token")
    except Exception:
        return None
    if token and _jwt_is_expired(token):
        return None
    return token


def save_token(access_token: str) -> None:
    """Write the API JWT to disk with 0600 permissions."""
    _write_secure(_CREDS_FILE, {"access_token": access_token})


def delete_token() -> None:
    """Remove stored NSU Audit credentials from disk."""
    if _CREDS_FILE.exists():
        _CREDS_FILE.unlink()


# ── Device flow state ─────────────────────────────────────────────────────────

def _build_pending_payload(data: dict) -> dict:
    """Normalise a raw device-flow response into the fields needed for polling."""
    return {
        "device_code":   data["device_code"],
        "client_id":     data["client_id"],
        "client_secret": data.get("client_secret", ""),
        "interval":      int(data.get("interval", 5)),
        "expires_at":    time.time() + int(data.get("expires_in", 1800)),
    }


def save_pending_device(data: dict) -> None:
    """Persist the in-progress device flow state with 0600 permissions."""
    _write_secure(_PENDING_FILE, _build_pending_payload(data))


def load_pending_device() -> Optional[dict]:
    if not _PENDING_FILE.exists():
        return None
    try:
        return json.loads(_PENDING_FILE.read_text())
    except Exception:
        return None


def clear_pending_device() -> None:
    if _PENDING_FILE.exists():
        _PENDING_FILE.unlink()


# ── Async session-state helpers (hosted + stdio) ──────────────────────────────
# These use FastMCP session state as the primary store so that each connected
# client in hosted HTTP/SSE mode has fully isolated credentials.
# They also write to disk as a secondary store so that stdio mode retains
# credentials across process restarts.

async def get_token(ctx: "Context") -> Optional[str]:
    """Return the JWT: session state first, then disk fallback."""
    try:
        token = await ctx.get_state("nsu_jwt")
        if token:
            return token
    except Exception:
        pass
    return load_token()


async def store_token(ctx: "Context", access_token: str) -> None:
    """Store the JWT in session state and on disk."""
    await ctx.set_state("nsu_jwt", access_token)
    save_token(access_token)


async def clear_token(ctx: "Context") -> None:
    """Remove the JWT from session state and disk."""
    await ctx.set_state("nsu_jwt", None)
    delete_token()


async def get_pending(ctx: "Context") -> Optional[dict]:
    """Return pending device state: session state first, then disk fallback."""
    try:
        data = await ctx.get_state("nsu_pending_device")
        if data:
            return data
    except Exception:
        pass
    return load_pending_device()


async def store_pending(ctx: "Context", data: dict) -> None:
    """Store pending device state in session state and on disk."""
    payload = _build_pending_payload(data)
    await ctx.set_state("nsu_pending_device", payload)
    _write_secure(_PENDING_FILE, payload)


async def clear_pending(ctx: "Context") -> None:
    """Clear pending device state from session state and disk."""
    await ctx.set_state("nsu_pending_device", None)
    clear_pending_device()


# ── Device token polling ──────────────────────────────────────────────────────

def poll_with_pending(api_base_url: str, pending: dict) -> str:
    """Poll Google for the device token using the provided pending state dict.

    Does not read from or write to disk — callers are responsible for state
    persistence.  Polls up to _MAX_POLL_ATTEMPTS × interval seconds.
    Returns the NSU Audit API JWT on success.
    """
    if time.time() > pending["expires_at"]:
        raise RuntimeError(
            "Login session expired. Call `nsu_oauth_start` again to start a new flow."
        )

    device_code   = pending["device_code"]
    client_id     = pending["client_id"]
    client_secret = pending["client_secret"]
    interval      = int(pending.get("interval", 5))

    for _ in range(_MAX_POLL_ATTEMPTS):
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
            id_token = poll.json().get("id_token")
            if not id_token:
                raise RuntimeError(
                    "Google did not return an id_token. The account may not be "
                    "a valid @northsouth.edu address."
                )
            base = api_base_url.rstrip("/")
            with httpx.Client(timeout=15) as exc_client:
                resp = exc_client.post(
                    f"{base}/api/auth/device/exchange",
                    json={"id_token": id_token},
                )
            if resp.status_code == 403:
                raise RuntimeError(
                    "Access denied: only @northsouth.edu accounts are allowed."
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Backend token exchange failed ({resp.status_code}): {resp.text}"
                )
            return resp.json()["access_token"]

        err = (poll.json() or {}).get("error", "")
        if err == "slow_down":
            interval += 5
        elif err not in ("authorization_pending",):
            raise RuntimeError(f"Google authorization error: {err}")

    raise RuntimeError(
        "Still waiting for browser authorization. "
        "Make sure you have entered the code at the verification URL and "
        "approved access, then call `nsu_oauth_complete` again."
    )


def poll_device_token(api_base_url: str) -> str:
    """Legacy helper — reads pending state from disk then delegates to poll_with_pending.

    Kept for backward compatibility with the CLI.
    """
    pending = load_pending_device()
    if not pending:
        raise RuntimeError("No pending login found. Call the `login` tool first.")
    try:
        access_token = poll_with_pending(api_base_url, pending)
        save_token(access_token)
        clear_pending_device()
        return access_token
    except RuntimeError:
        clear_pending_device()
        raise
