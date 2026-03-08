"""JWT session helpers — create, decode, and inject as FastAPI dependency."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, Header, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db

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


async def get_current_user(
    db:     AsyncSession = Depends(get_db),
    claims: dict         = Depends(get_current_claims),
):
    """FastAPI dependency — decode JWT then upsert the user row.

    Using google_sub (not user_id) as the lookup key means the user is
    automatically re-created after a DB reset, eliminating FK violations
    on audit_runs caused by a stale user_id in an old JWT.

    Returns the live ORM User object so callers get the authoritative DB id.
    """
    # Late import avoids a circular-import at module load time
    from ..models.user import User

    google_sub = claims.get("sub", "")
    email      = claims.get("email", "")
    name       = claims.get("name", email.split("@")[0])
    hd         = email.split("@")[-1] if "@" in email else ""

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user   = result.scalar_one_or_none()
    now    = datetime.now(timezone.utc)

    if user is None:
        # DB was wiped or this is the first time — recreate the row.
        user = User(
            id=uuid.uuid4(),
            google_sub=google_sub,
            email=email,
            hd=hd,
            display_name=name,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.last_login_at = now
        await db.commit()

    return user

