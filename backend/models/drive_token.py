"""DriveToken ORM model — stores per-user Google Drive OAuth tokens."""
import time

from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class DriveToken(Base):
    __tablename__ = "drive_tokens"

    # user_id is a string FK to users.id (UUID stored as string for simplicity)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    access_token:  Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    refresh_token: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    expires_at:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
