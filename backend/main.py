"""NSU Audit API — FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings
from .database import Base, engine
from . import models  # noqa: F401 — ensures all ORM models are registered
from .routers import admin, audit, auth, gdrive, gmail, history

# Hosted MCP server — mounted at /mcp so any AI client can connect via SSE
# without installing the nsu-audit-mcp binary locally.
from mcp_server.nsu_audit_mcp.server import mcp as _mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist on startup (Alembic handles production migrations;
    # create_all is a safety net for local dev / first run)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="NSU Audit API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middleware (order matters: outermost middleware executes first on request) ─

# 1. Session — PKCE state + code_verifier stored in a short-lived signed cookie
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="nsu_session",
    max_age=600,                                 # 10 min — only needed during OAuth dance
    https_only=settings.app_env == "production",
    same_site="lax",
)

# 2. CORS — allow only the configured frontend origin(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(audit.router)
app.include_router(history.router)
app.include_router(admin.router)
app.include_router(gdrive.router)
app.include_router(gmail.router)

# ── Hosted MCP server — /mcp/sse (SSE) + /mcp/messages (POST) ────────────────
# Friends connect by adding this to their opencode/Claude Desktop config:
#   { "type": "remote", "url": "https://<your-ngrok-domain>/mcp/sse",
#     "headers": { "X-MCP-Secret": "<MCP_SHARED_SECRET from .env>" } }


class _McpSecretGuard(BaseHTTPMiddleware):
    """Block /mcp requests that don't carry the correct X-MCP-Secret header.

    Only active when MCP_SHARED_SECRET is set in the environment.
    Requests to non-/mcp paths pass through unconditionally.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        secret = settings.mcp_shared_secret
        if secret and request.url.path.startswith("/mcp"):
            provided = request.headers.get("x-mcp-secret", "")
            if provided != secret:
                return Response(
                    content='{"detail":"Forbidden — invalid or missing X-MCP-Secret"}',
                    status_code=403,
                    media_type="application/json",
                )
        return await call_next(request)


app.add_middleware(_McpSecretGuard)
app.mount("/mcp", _mcp_server.http_app(transport="sse"))


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
