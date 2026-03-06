"""JWT session helpers — create, decode, and inject as FastAPI dependency."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request
from jose import JWTError, jwt

from ..config import settings

_ALGORITHM  = "HS256"
_TOKEN_TTL  = timedelta(days=7)
COOKIE_NAME = "nsu_audit_token"


def create_token(
    user_id: uuid.UUID,
    google_sub: str,
    email: str,
    display_name: str,
    is_admin: bool = False,
) -> str:
    """Create a signed JWT for an authenticated user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub":      google_sub,
        "user_id":  str(user_id),
        "email":    email,
        "name":     display_name,
        "is_admin": is_admin,
        "iat":      now,
        "exp":      now + _TOKEN_TTL,
    }
    return jwt.encode(payload, settings.session_secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT; raise HTTP 401 if invalid or expired."""
    try:
        return jwt.decode(token, settings.session_secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")


def get_current_claims(
    nsu_audit_token: Optional[str] = Cookie(default=None),
    authorization:   Optional[str] = Header(default=None, alias="Authorization"),
) -> dict:
    """FastAPI dependency — accepts the JWT from either:
      - The HttpOnly cookie ``nsu_audit_token`` (web browser flow), or
      - An ``Authorization: Bearer <token>`` header (CLI / API flow).
    Raises HTTP 401 if neither is present or the token is invalid.
    """
    token = nsu_audit_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return decode_token(token)

