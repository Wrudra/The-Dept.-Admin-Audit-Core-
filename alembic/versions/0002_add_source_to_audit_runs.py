"""Add source column to audit_runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-14 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_runs",
        sa.Column("source", sa.String(10), nullable=True, server_default="web"),
    )


def downgrade() -> None:
    op.drop_column("audit_runs", "source")
