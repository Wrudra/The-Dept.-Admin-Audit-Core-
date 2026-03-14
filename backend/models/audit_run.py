"""AuditRun ORM model — one row per audit execution (web or CLI)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditRun(Base):
    __tablename__ = "audit_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    program: Mapped[str] = mapped_column(String(10), nullable=False)       # CSE | MIC
    level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNDERGRADUATE"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"                      # pending | processing | complete | failed
    )
    transcript_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    answers_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # How the audit was submitted: "web" | "mcp"  (nullable for legacy rows)
    source: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="web")
