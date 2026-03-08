"""Credential storage for the NSU Audit CLI.

Tokens are stored at ~/.config/nsu-audit/credentials.json with mode 0600.
"""
import json
import os
import stat
import time
from pathlib import Path
from typing import Optional

import httpx

_CREDS_DIR  = Path.home() / ".config" / "nsu-audit"
_CREDS_FILE = _CREDS_DIR / "credentials.json"

_GOOGLE_TOKEN_URL   = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT_TYPE  = "urn:ietf:params:oauth:grant-type:device_code"


# ── Token file ────────────────────────────────────────────────────────────────

def load_token() -> Optional[str]:
    """Return the stored JWT, or None if not logged in."""
    if not _CREDS_FILE.exists():
        return None
    try:
        return json.loads(_CREDS_FILE.read_text()).get("access_token")
    except Exception:
        return None


def save_token(access_token: str) -> None:
    """Write the JWT to disk and set permissions to 0600."""
    _CREDS_DIR.mkdir(parents=True, exist_ok=True)
    _CREDS_FILE.write_text(json.dumps({"access_token": access_token}, indent=2))
    os.chmod(_CREDS_FILE, stat.S_IRUSR | stat.S_IWUSR)  # owner read/write only


def delete_token() -> None:
    """Remove the stored credentials (logout)."""
    if _CREDS_FILE.exists():
        _CREDS_FILE.unlink()


def require_token() -> str:
    """Return the JWT or die with a helpful message."""
    token = load_token()
    if not token:
        import sys
        print("Not logged in.  Run:  nsu-audit login", file=sys.stderr)
        sys.exit(1)
    return token


# ── Device Authorization Grant ────────────────────────────────────────────────

def device_login(api_url: str) -> str:
    """Run Device Authorization Grant; return the API JWT.

    Flow:
      1. POST /api/auth/device/start  → get user_code, verification_url, device_code
      2. Ask the user to visit the URL and enter the code
      3. Poll Google's token endpoint until approved
      4. POST /api/auth/device/exchange with id_token → get API JWT
    """
    with httpx.Client(timeout=30) as client:
        # Step 1 — start the flow via our backend
        resp = client.post(f"{api_url}/api/auth/device/start")
        resp.raise_for_status()
        data = resp.json()

    user_code        = data["user_code"]
    verification_url = data["verification_url"]
    device_code      = data["device_code"]
    client_id        = data["client_id"]
    client_secret    = data.get("client_secret", "")
    interval         = int(data.get("interval", 5))
    expires_in       = int(data.get("expires_in", 1800))

    print(f"\n  Open this URL in your browser:")
    print(f"    {verification_url}\n")
    print(f"  Then enter the code:  {user_code}\n")
    print("  Waiting for authorization", end="", flush=True)

    # Step 2 — poll Google directly for the token
    deadline = time.time() + expires_in
    with httpx.Client(timeout=15) as client:
        while time.time() < deadline:
            time.sleep(interval)
            print(".", end="", flush=True)

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
                if id_token:
                    print("  authorized!\n")
                    # Step 3 — exchange Google id_token for our API JWT
                    with httpx.Client(timeout=15) as exc_client:
                        exch = exc_client.post(
                            f"{api_url}/api/auth/device/exchange",
                            json={"id_token": id_token},
                        )
                    exch.raise_for_status()
                    return exch.json()["access_token"]

            err = (poll.json() or {}).get("error", "")
            if err == "slow_down":
                interval += 5       # back off as instructed
            elif err not in ("authorization_pending",):
                print()
                raise RuntimeError(f"Authorization error from Google: {err}")

    print()
    raise TimeoutError("Device authorization timed out.")
