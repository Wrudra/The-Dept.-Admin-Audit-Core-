"""History router — list, retrieve, and delete past audit runs for the caller."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.session import get_current_user
from ..database import get_db
from ..models.audit_run import AuditRun
from ..models.user import User

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/", summary="List the caller's past audit runs")
async def list_history(
    limit:        int          = Query(20, ge=1, le=100),
    offset:       int          = Query(0,  ge=0),
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
) -> dict:
    """Return a paginated list of the caller's audit runs (most recent first)."""
    user_id = current_user.id
    result  = await db.execute(
        select(AuditRun)
        .where(AuditRun.user_id == user_id)
        .order_by(AuditRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    runs = result.scalars().all()
    return {
        "runs": [
            {
                "run_id":              str(r.id),
                "program":             r.program,
                "status":              r.status,
                "transcript_filename": r.transcript_filename,
                "created_at":          r.created_at.isoformat(),
                "completed_at":        r.completed_at.isoformat() if r.completed_at else None,
                "source":              r.source or "web",
                # Lightweight summary only — full result at GET /api/audit/{id}
                "cgpa":                (r.result_json or {}).get("cgpa"),
                "credit_completed":    (r.result_json or {}).get("credit_completed"),
                "required_credits":    (r.result_json or {}).get("required_credits"),
            }
            for r in runs
        ],
        "limit":  limit,
        "offset": offset,
    }


@router.get("/{run_id}", summary="Get one past audit run")
async def get_history_run(
    run_id:       uuid.UUID,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
) -> dict:
    user_id = current_user.id
    result  = await db.execute(
        select(AuditRun).where(AuditRun.id == run_id, AuditRun.user_id == user_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "run_id":              str(run.id),
        "program":             run.program,
        "status":              run.status,
        "transcript_filename": run.transcript_filename,
        "created_at":          run.created_at.isoformat(),
        "completed_at":        run.completed_at.isoformat() if run.completed_at else None,
        "source":              run.source or "web",
        "result":              run.result_json,
        "answers":             run.answers_json,
    }


@router.delete("/{run_id}", summary="Delete a past audit run")
async def delete_history_run(
    run_id:       uuid.UUID,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(get_current_user),
) -> dict:
    """Hard-delete a run owned by the caller."""
    user_id = current_user.id
    result  = await db.execute(
        select(AuditRun).where(AuditRun.id == run_id, AuditRun.user_id == user_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    await db.delete(run)
    await db.commit()
    return {"deleted": str(run_id)}

