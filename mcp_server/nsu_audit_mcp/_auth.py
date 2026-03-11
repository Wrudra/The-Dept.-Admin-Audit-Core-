"""Credential storage for the NSU Audit MCP server.

Tokens are stored at ~/.config/nsu-audit-mcp/credentials.json with mode 0600.
The device flow state (pending authorization) is stored at
~/.config/nsu-audit-mcp/pending_device.json with the same permissions.
"""
import base64
import json
import os
import stat
import time
from pathlib import Path
from typing import Optional

import httpx

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

def save_pending_device(data: dict) -> None:
    """Persist the in-progress device flow state with 0600 permissions.

    Stores only the fields needed for polling (device_code, client credentials,
    interval, and computed expiry timestamp).  The raw client_secret received
    from the backend is stored here — this mirrors the existing CLI behaviour.
    """
    payload = {
        "device_code":   data["device_code"],
        "client_id":     data["client_id"],
        "client_secret": data.get("client_secret", ""),
        "interval":      int(data.get("interval", 5)),
        "expires_at":    time.time() + int(data.get("expires_in", 1800)),
    }
    _write_secure(_PENDING_FILE, payload)


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


# ── Device token polling ──────────────────────────────────────────────────────

def poll_device_token(api_base_url: str) -> str:
    """Poll Google for the device token, then exchange with the backend for an API JWT.

    Polls up to _MAX_POLL_ATTEMPTS times (each attempt waits `interval` seconds).
    Returns the API JWT string on success.
    Raises RuntimeError if the user has not yet authorized, or if the flow expired.
    Callers should surface the error message and ask the user to call login_complete again.
    """
    pending = load_pending_device()
    if not pending:
        raise RuntimeError("No pending login found. Call the `login` tool first.")

    if time.time() > pending["expires_at"]:
        clear_pending_device()
        raise RuntimeError(
            "Login session expired. Call `login` again to start a new flow."
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
            # Exchange the Google id_token for the backend API JWT.
            base = api_base_url.rstrip("/")
            with httpx.Client(timeout=15) as exc_client:
                resp = exc_client.post(
                    f"{base}/api/auth/device/exchange",
                    json={"id_token": id_token},
                )
            if resp.status_code == 403:
                clear_pending_device()
                raise RuntimeError(
                    "Access denied: only @northsouth.edu accounts are allowed."
                )
            if resp.status_code != 200:
                clear_pending_device()
                raise RuntimeError(
                    f"Backend token exchange failed ({resp.status_code}): {resp.text}"
                )
            access_token = resp.json()["access_token"]
            save_token(access_token)
            clear_pending_device()
            return access_token

        err = (poll.json() or {}).get("error", "")
        if err == "slow_down":
            interval += 5
        elif err not in ("authorization_pending",):
            clear_pending_device()
            raise RuntimeError(f"Google authorization error: {err}")

    raise RuntimeError(
        "Still waiting for browser authorization. "
        "Make sure you have entered the code at the verification URL and "
        "approved access, then call `login_complete` again."
    )
