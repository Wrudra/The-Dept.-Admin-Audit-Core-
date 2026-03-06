"""NSU Audit API — FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import Base, engine
from .routers import admin, audit, auth, history


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


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
