"""GmailToken ORM model — stores per-user Gmail send-only OAuth tokens."""
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class GmailToken(Base):
    __tablename__ = "gmail_tokens"

    user_id:       Mapped[str]   = mapped_column(String(36), primary_key=True)
    access_token:  Mapped[str]   = mapped_column(String(2048), nullable=False, default="")
    refresh_token: Mapped[str]   = mapped_column(String(2048), nullable=False, default="")
    expires_at:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
