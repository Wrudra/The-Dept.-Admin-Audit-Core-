"""Authentication router — Google OAuth 2.0 PKCE (web) + Device Auth Grant (CLI)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.google import (
    build_authorization_url,
    exchange_code,
    generate_pkce_pair,
    generate_state,
    start_device_flow,
    verify_id_token,
)
from ..auth.session import COOKIE_NAME, create_token, get_current_claims
from ..config import settings
from ..database import get_db
from ..models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

_IS_PROD = settings.app_env == "production"


# ── Web OAuth PKCE ────────────────────────────────────────────────────────────

@router.get("/login", summary="Start Google OAuth PKCE login")
async def login(request: Request) -> RedirectResponse:
    """Generate PKCE pair + state, store in session, redirect to Google."""
    verifier, challenge = generate_pkce_pair()
    state = generate_state()
    request.session["pkce_verifier"] = verifier
    request.session["oauth_state"]   = state
    return RedirectResponse(build_authorization_url(state, challenge))


@router.get("/callback", summary="Google OAuth callback")
async def callback(
    request: Request,
    response: Response,
    code:  str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="Anti-CSRF state token"),
    db:    AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Validate state + PKCE verifier, exchange code, upsert user, set JWT cookie."""
    saved_state   = request.session.pop("oauth_state",   None)
    code_verifier = request.session.pop("pkce_verifier", None)

    if not saved_state or state != saved_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF.")
    if not code_verifier:
        raise HTTPException(status_code=400, detail="PKCE verifier missing from session.")

    claims   = await exchange_code(code, code_verifier)
    user     = await _upsert_user(db, claims)
    is_admin = user.email in settings.admin_emails_list
    token    = create_token(user.id, user.google_sub, user.email, user.display_name, is_admin)

    resp = RedirectResponse(url=f"{settings.frontend_url}/dashboard", status_code=302)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_IS_PROD,
        samesite="lax",
        max_age=7 * 24 * 3600,  # 7 days, matches JWT TTL
    )
    return resp


@router.get("/me", summary="Current authenticated user")
async def me(claims: dict = Depends(get_current_claims)) -> dict:
    """Return basic profile from the JWT — no DB round-trip needed."""
    return {
        "user_id":      claims["user_id"],
        "email":        claims["email"],
        "display_name": claims["name"],
        "is_admin":     claims.get("is_admin", False),
    }


@router.post("/logout", summary="Log out")
async def logout(response: Response) -> dict:
    """Clear the JWT cookie."""
    response.delete_cookie(COOKIE_NAME, httponly=True, samesite="lax")
    return {"ok": True}


# ── CLI Device Authorization Grant ────────────────────────────────────────────

@router.post("/device/start", summary="Start CLI device flow")
async def device_start() -> dict:
    """Start Device Authorization Grant.

    Returns `user_code` (display to user), `verification_url`, `device_code`
    (CLI polls Google directly), and polling hints.
    """
    data = await start_device_flow()
    return {
        "user_code":        data["user_code"],
        "verification_url": data["verification_url"],
        # CLI needs device_code to poll Google's token endpoint itself
        "device_code":      data["device_code"],
        "expires_in":       data.get("expires_in", 1800),
        "interval":         data.get("interval", 5),
        "client_id":        settings.google_cli_client_id,
    }


class DeviceExchangeRequest(BaseModel):
    id_token: str


@router.post("/device/exchange", summary="Exchange CLI id_token for API JWT")
async def device_exchange(
    body: DeviceExchangeRequest,
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """After CLI polls Google and receives tokens, call this to get an API JWT.

    The CLI extracts `id_token` from Google's token response and sends it here.
    We verify it, enforce the @northsouth.edu domain restriction, and return
    a signed JWT the CLI stores locally.
    """
    claims   = await verify_id_token(body.id_token, settings.google_cli_client_id)
    user     = await _upsert_user(db, claims)
    is_admin = user.email in settings.admin_emails_list
    token    = create_token(user.id, user.google_sub, user.email, user.display_name, is_admin)
    return {"access_token": token, "token_type": "bearer"}


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _upsert_user(db: AsyncSession, claims: dict) -> User:
    """INSERT or UPDATE the users row from Google id_token claims."""
    google_sub = claims["sub"]
    email      = claims.get("email", "")
    hd         = claims.get("hd", "")
    name       = claims.get("name", email.split("@")[0])
    picture    = claims.get("picture")

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user   = result.scalar_one_or_none()
    now    = datetime.now(timezone.utc)

    if user is None:
        user = User(
            id=uuid.uuid4(),
            google_sub=google_sub,
            email=email,
            hd=hd,
            display_name=name,
            profile_picture_url=picture,
            created_at=now,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.last_login_at       = now
        user.display_name        = name
        user.profile_picture_url = picture

    await db.commit()
    await db.refresh(user)
    return user
