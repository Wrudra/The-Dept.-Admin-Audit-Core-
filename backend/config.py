"""Application settings loaded from the .env file at the repo root."""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Google OAuth — web (Authorization Code + PKCE) ──────────────────────
    google_web_client_id:     str
    google_web_client_secret: str

    # ── Google OAuth — CLI (Device Authorization Grant) ──────────────────────
    google_cli_client_id:     str
    google_cli_client_secret: str

    google_redirect_uri: str
    google_allowed_hd:   str = "northsouth.edu"

    # ── Session / JWT ────────────────────────────────────────────────────────
    session_secret_key: str   # 64-char hex; signs both HttpOnly JWT and PKCE session cookie

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str         # postgresql://user:pass@host:5432/dbname

    # ── Google Drive + Gmail (Desktop-app OAuth — server-side only) ────────
    gdrive_client_id:     str = ""
    gdrive_client_secret: str = ""

    # ── App ──────────────────────────────────────────────────────────────────
    app_env:              str = "development"
    backend_url:          str = "http://localhost:8000"
    frontend_url:         str = "http://localhost:5173"
    max_upload_size_mb:   int = 10
    cors_allowed_origins: str = "http://localhost:5173"
    admin_emails:         str = ""  # comma-separated admin email addresses

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",")]

    @property
    def admin_emails_list(self) -> list[str]:
        return [e.strip() for e in self.admin_emails.split(",") if e.strip()]

    model_config = {
        "env_file": str(Path(__file__).parent.parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",   # .env may contain fields for other services (DB, Redis, etc.)
    }


settings = Settings()
