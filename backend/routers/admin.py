"""Admin router — aggregate statistics and admin-only operations."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.session import get_current_claims
from ..database import get_db
from ..models.audit_run import AuditRun
from ..models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(claims: dict = Depends(get_current_claims)) -> dict:
    if not claims.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return claims


@router.get("/stats", summary="Aggregate platform statistics")
async def stats(
    db:     AsyncSession = Depends(get_db),
    claims: dict         = Depends(_require_admin),
) -> dict:
    """Return platform-wide stats. Admin only."""

    # Total run count
    total_runs_row = await db.execute(select(func.count(AuditRun.id)))
    total_runs: int = total_runs_row.scalar_one()

    # Total user count
    total_users_row = await db.execute(select(func.count(User.id)))
    total_users: int = total_users_row.scalar_one()

    # Runs by program
    program_rows = await db.execute(
        select(AuditRun.program, func.count(AuditRun.id))
        .group_by(AuditRun.program)
    )
    runs_by_program = {row[0]: row[1] for row in program_rows}

    # Average CGPA and average credits (from result_json — only complete runs)
    runs_result = await db.execute(
        select(AuditRun.result_json)
        .where(AuditRun.status == "complete", AuditRun.result_json.isnot(None))
    )
    results = [row[0] for row in runs_result]
    cgpas   = [r["cgpa"] for r in results if isinstance(r.get("cgpa"), (int, float))]
    credits = [r["credit_completed"] for r in results if isinstance(r.get("credit_completed"), (int, float))]

    avg_cgpa    = round(sum(cgpas) / len(cgpas), 2) if cgpas else None
    avg_credits = round(sum(credits) / len(credits), 1) if credits else None

    # Recent 20 runs across all users
    recent_rows = await db.execute(
        select(AuditRun, User.email, User.display_name)
        .join(User, AuditRun.user_id == User.id)
        .order_by(AuditRun.created_at.desc())
        .limit(20)
    )
    recent_runs = [
        {
            "run_id":              str(run.id),
            "program":             run.program,
            "status":              run.status,
            "transcript_filename": run.transcript_filename,
            "created_at":          run.created_at.isoformat(),
            "cgpa":                run.result_json.get("cgpa") if run.result_json else None,
            "credit_completed":    run.result_json.get("credit_completed") if run.result_json else None,
            "required_credits":    run.result_json.get("required_credits") if run.result_json else None,
            "user_email":          email,
            "user_name":           display_name,
        }
        for run, email, display_name in recent_rows
    ]

    return {
        "total_runs":      total_runs,
        "total_users":     total_users,
        "runs_by_program": runs_by_program,
        "avg_cgpa":        avg_cgpa,
        "avg_credits":     avg_credits,
        "recent_runs":     recent_runs,
    }


@router.delete("/history/{run_id}", summary="Hard-delete any audit run (admin only)")
async def admin_delete_run(
    run_id: uuid.UUID,
    db:     AsyncSession = Depends(get_db),
    claims: dict         = Depends(_require_admin),
) -> dict:
    """Permanently delete any audit run regardless of owner. Admin only."""
    result = await db.execute(select(AuditRun).where(AuditRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found.")
    await db.delete(run)
    await db.commit()
    return {"deleted": str(run_id)}
