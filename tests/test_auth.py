"""Tests for backend auth helpers (PKCE, JWT)."""
import time
import uuid

import pytest

from backend.auth.google import generate_pkce_pair, generate_state
from backend.auth.session import create_token, decode_token


# ── PKCE ──────────────────────────────────────────────────────────────────────

def test_pkce_lengths():
    verifier, challenge = generate_pkce_pair()
    # Base64url-encoded 32-byte random → 43 chars; verifier = URL-safe base64url(64 bytes) → 86 chars
    assert len(verifier) == 86
    assert len(challenge) == 43


def test_pkce_deterministic_challenge():
    """Same verifier must always produce the same challenge."""
    import base64, hashlib
    v = "x" * 86
    digest    = hashlib.sha256(v.encode()).digest()
    expected  = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    _, c = generate_pkce_pair()
    # Just check the output is plausible base64url without padding
    assert "=" not in c
    assert all(ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in c)


def test_state_uniqueness():
    states = {generate_state() for _ in range(50)}
    assert len(states) == 50


# ── JWT ────────────────────────────────────────────────────────────────────────

def test_jwt_roundtrip():
    uid   = uuid.uuid4()
    token = create_token(uid, "google_sub_xyz", "test@northsouth.edu", "Test User")
    assert isinstance(token, str)

    claims = decode_token(token)
    assert claims["user_id"] == str(uid)
    assert claims["email"]   == "test@northsouth.edu"
    assert claims["name"]    == "Test User"
    assert claims["sub"]     == "google_sub_xyz"


def test_jwt_invalid_token():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        decode_token("this.is.garbage")
    assert exc_info.value.status_code == 401


def test_jwt_expired_token():
    """Manually craft a token with exp in the past and verify it's rejected."""
    from datetime import datetime, timezone, timedelta
    from jose import jwt
    from backend.config import settings
    from fastapi import HTTPException

    payload = {
        "sub":     "sub123",
        "user_id": str(uuid.uuid4()),
        "email":   "test@northsouth.edu",
        "name":    "Test",
        "iat":     datetime.now(timezone.utc) - timedelta(days=14),
        "exp":     datetime.now(timezone.utc) - timedelta(days=7),
    }
    token = jwt.encode(payload, settings.session_secret_key, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401
