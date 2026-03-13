"""Google OAuth 2.0 helpers — PKCE (web) and Device Authorization Grant (CLI)."""
import base64
import hashlib
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

from ..config import settings

_GOOGLE_AUTH_URL   = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL  = "https://oauth2.googleapis.com/token"
_GOOGLE_DEVICE_URL = "https://oauth2.googleapis.com/device/code"
_GOOGLE_TOKENINFO  = "https://oauth2.googleapis.com/tokeninfo"


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier  = secrets.token_urlsafe(64)                              # 86 chars, URL-safe
    digest    = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def generate_state() -> str:
    """Return a random, unguessable state token for CSRF protection."""
    return secrets.token_urlsafe(32)


def build_authorization_url(state: str, code_challenge: str) -> str:
    """Build the Google Authorization URL that the browser navigates to."""
    params = {
        "client_id":             settings.google_web_client_id,
        "redirect_uri":          settings.google_redirect_uri,
        "response_type":         "code",
        "scope":                 "openid email profile",
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
        "access_type":           "online",
        "prompt":                "select_account",
        "hd":                    settings.google_allowed_hd,  # pre-filter to NSU accounts
    }
    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


# ── Token exchange ────────────────────────────────────────────────────────────

async def exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange an authorization code for tokens (PKCE web flow).

    Returns the validated id_token claims dict on success.
    Raises HTTPException on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_TOKEN_URL,
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  settings.google_redirect_uri,
                "client_id":     settings.google_web_client_id,
                "client_secret": settings.google_web_client_secret,
                "code_verifier": code_verifier,
            },
        )

    if resp.status_code != 200:
        logger.error(
            "Google token exchange failed — status=%s body=%s redirect_uri=%s",
            resp.status_code, resp.text, settings.google_redirect_uri,
        )
        raise HTTPException(status_code=400, detail="Google token exchange failed.")

    id_token = resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="id_token missing from Google response.")

    return await verify_id_token(id_token, settings.google_web_client_id)


async def verify_id_token(id_token: str, expected_aud: str) -> dict:
    """Verify a Google id_token via the tokeninfo endpoint.

    Validates: audience, issuer, expiry, and hosted domain (hd).
    Returns the claims dict on success.
    Raises HTTPException on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(_GOOGLE_TOKENINFO, params={"id_token": id_token})

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid id_token.")

    claims = resp.json()

    if claims.get("aud") != expected_aud:
        raise HTTPException(status_code=401, detail="id_token audience mismatch.")

    if claims.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(status_code=401, detail="id_token issuer invalid.")

    # Enforce @northsouth.edu domain restriction
    hd = claims.get("hd", "")
    if hd != settings.google_allowed_hd:
        raise HTTPException(
            status_code=403,
            detail=f"Only @{settings.google_allowed_hd} accounts are allowed.",
        )

    # Explicit expiry check (Google tokeninfo already does this, but be explicit)
    exp = int(claims.get("exp", 0))
    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="id_token has expired.")

    return claims


# ── Device Authorization Grant (CLI) ─────────────────────────────────────────

async def start_device_flow() -> dict:
    """Start Device Authorization Grant using the CLI OAuth client.

    Returns the full response from Google (device_code, user_code, etc.).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _GOOGLE_DEVICE_URL,
            data={
                "client_id": settings.google_cli_client_id,
                "scope":     "openid email profile",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to start device authorization flow.")

    return resp.json()
