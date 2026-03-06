"""Audit router — POST /api/audit/run and GET /api/audit/{id}."""
import asyncio
import io
import json
import tempfile
import threading
import time
import types
import uuid
from collections import defaultdict
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.session import get_current_claims
from ..config import settings
from ..database import get_db
from ..models.audit_run import AuditRun

router = APIRouter(prefix="/api/audit", tags=["audit"])

# ── Simple in-memory rate limiter (5 audits / 60 s per user) ─────────────────

_RATE_WINDOW = 60   # seconds
_RATE_LIMIT  = 5    # max audit runs per window
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()


def _check_rate_limit(user_id: str) -> None:
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW
    with _rate_lock:
        timestamps = _rate_store[user_id]
        _rate_store[user_id] = [t for t in timestamps if t > cutoff]
        if len(_rate_store[user_id]) >= _RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {_RATE_LIMIT} audits per {_RATE_WINDOW}s.",
            )
        _rate_store[user_id].append(now)

# ── Constants ─────────────────────────────────────────────────────────────────

_PROGRAM_MD = Path(__file__).parent.parent.parent / "program.md"
_MAX_BYTES   = settings.max_upload_size_mb * 1024 * 1024

_ALLOWED_EXTS = {".csv", ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
_OCR_EXTS     = _ALLOWED_EXTS - {".csv"}

# Threading lock — one audit at a time while audit_l1._CONFIG is a module global.
_AUDIT_LOCK = threading.Lock()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", summary="Run an audit against a transcript CSV")
async def run_audit_endpoint(
    transcript: UploadFile  = File(...,   description="Transcript CSV produced by transcript_to_csv.py"),
    program:    str          = Form(...,   description="Program code: CSE or MIC"),
    answers:    str          = Form("{}",  description="JSON object mapping AK_* answer-key strings to values"),
    db:         AsyncSession = Depends(get_db),
    claims:     dict         = Depends(get_current_claims),
) -> dict:
    """Upload a transcript CSV and pre-supplied answers, run the audit engine, return results."""

    # ── Input validation ──────────────────────────────────────────────────────
    program = program.strip().upper()
    if program not in ("CSE", "MIC"):
        raise HTTPException(status_code=400, detail="program must be CSE or MIC.")

    filename = transcript.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail="Only .csv, .pdf, .jpg, .jpeg, .png, .tif, .tiff, or .bmp files are accepted.",
        )

    try:
        answers_dict = json.loads(answers)
        if not isinstance(answers_dict, dict):
            raise ValueError("must be JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"answers must be a JSON object: {exc}")

    user_id = uuid.UUID(claims["user_id"])
    _check_rate_limit(str(user_id))

    # ── Read + size-check upload ──────────────────────────────────────────────
    content = await transcript.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_size_mb} MB limit.",
        )

    # ── OCR pre-processing for PDF / image uploads ───────────────────────────
    loop_ref = asyncio.get_running_loop()
    if ext in _OCR_EXTS:
        try:
            content = await loop_ref.run_in_executor(
                None, _ocr_to_csv_bytes, content, ext
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"OCR failed: {exc}")
        filename = Path(filename).stem + ".csv"   # rename for storage

    # ── Run audit in thread pool (CPU-bound; releases the async event loop) ──
    try:
        result_dict = await loop_ref.run_in_executor(
            None,
            _run_audit_in_thread,
            content,
            program,
            answers_dict,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audit engine error: {exc}")

    # ── Persist record ────────────────────────────────────────────────────────
    run = AuditRun(
        id=uuid.uuid4(),
        user_id=user_id,
        program=program,
        status="complete",
        transcript_filename=filename,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        result_json=result_dict,
        answers_json=answers_dict,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return {"run_id": str(run.id), "result": result_dict}


@router.get("/{run_id}", summary="Fetch a previously completed audit")
async def get_audit(
    run_id: uuid.UUID,
    db:     AsyncSession = Depends(get_db),
    claims: dict         = Depends(get_current_claims),
) -> dict:
    """Return a past audit run owned by the caller."""
    user_id = uuid.UUID(claims["user_id"])
    result  = await db.execute(
        select(AuditRun).where(AuditRun.id == run_id, AuditRun.user_id == user_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Audit run not found.")
    return {
        "run_id":               str(run.id),
        "program":              run.program,
        "status":               run.status,
        "transcript_filename":  run.transcript_filename,
        "created_at":           run.created_at.isoformat(),
        "completed_at":         run.completed_at.isoformat() if run.completed_at else None,
        "result":               run.result_json,
        "answers":              run.answers_json,
    }


# ── OCR helper (called via run_in_executor) ────────────────────────────────────

def _ocr_to_csv_bytes(content: bytes, ext: str) -> bytes:
    """Write uploaded bytes to a temp file with the correct extension, run OCR,
    return CSV bytes ready for the audit engine."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from transcript_to_csv import convert_to_csv_bytes

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        return convert_to_csv_bytes(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


# ── Synchronous audit worker (called via run_in_executor) ─────────────────────

def _run_audit_in_thread(content: bytes, program: str, answers: dict) -> dict:
    """Write the CSV bytes to a temp file, run the audit engine, return serialized result.

    Protected by _AUDIT_LOCK because audit_l1._CONFIG is a module-level global.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # Late imports — audit modules live at the repo root, not inside the package
    from audit_l1 import AuditConfig
    import audit_l2

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        config = AuditConfig(no_interact=True, answers=answers)
        args   = types.SimpleNamespace(
            transcript=tmp_path,
            program_name=program,
            program_knowledge=_PROGRAM_MD,
            no_interact=True,
        )

        captured = io.StringIO()
        with redirect_stdout(captured):
            with _AUDIT_LOCK:
                raw = audit_l2.run_audit(args, config)

        return _serialize_result(raw, captured.getvalue())
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _serialize_result(raw: dict, console_log: str) -> dict:
    """Convert the raw run_audit() dict into a JSON-serializable response."""
    prereq_failures = raw.get("prereq_failures") or {}
    return {
        "program":             raw["program_key"],
        "total_valid_credits": raw["total"],
        "required_credits":    raw["required_credits"],
        "credit_completed":    raw["credit_completed"],
        "cgpa":                round(float(raw["cgpa"]), 2),
        "waived_courses":      sorted(raw.get("waived_courses") or []),
        "waiver_notes":        raw.get("waiver_notes") or [],
        "major_electives":     raw.get("major_electives") or [],
        "open_elective":       raw.get("open_elective"),
        "free_electives":      raw.get("free_electives") or [],
        "prereq_failures":     dict(prereq_failures),  # dict[str, str]: course → reason
        "per_course_credits":  raw.get("per_course") or {},
        "console_log":         console_log,
    }

