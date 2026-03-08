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

# Threading lock — one audit at a time while audit_l1.NO_INTERACT is a module global.
_AUDIT_LOCK = threading.Lock()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", summary="Run an audit against a transcript CSV")
async def run_audit_endpoint(
    transcript: UploadFile  = File(...,   description="Transcript CSV produced by transcript_to_csv.py"),
    program:    str          = Form(...,   description="Program code: CSE or MIC"),
    answers:    str          = Form("{}",  description="JSON object mapping choice keys to values"),
    save:       str          = Form("true", description="Whether to persist the audit run to the database"),
    db:         AsyncSession = Depends(get_db),
    claims:     dict         = Depends(get_current_claims),
) -> dict:
    """Upload a transcript CSV and pre-supplied answers, run the audit engine, return results + choices."""

    # ── Input validation ──────────────────────────────────────────────────────
    do_save = save.strip().lower() in ("true", "1", "yes")
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

    # ── Separate choices from stored result ──────────────────────────────────
    choices = result_dict.pop("choices", [])

    # ── Persist record (skip for discovery / preview calls) ───────────────────
    if do_save:
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
        return {"run_id": str(run.id), "result": result_dict, "choices": choices}

    return {"result": result_dict, "choices": choices}


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

    Protected by _AUDIT_LOCK because audit_l1.NO_INTERACT is a module-level global.
    Monkey-patches _prompt_pick and _prompt_yes_no to intercept interactive choices,
    using pre-supplied answers when available and auto-selecting otherwise.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    # Late imports — audit modules live at the repo root, not inside the package
    import audit_l1
    import audit_l2

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        args = types.SimpleNamespace(
            transcript=tmp_path,
            program_name=program,
            program_knowledge=_PROGRAM_MD,
            no_interact=True,
        )

        # ── Monkey-patch prompt functions to intercept choices ────────────
        import inspect as _inspect

        _choices: list[dict] = []
        _pick_idx = [0]   # counter for pick choices
        _yn_idx   = [0]   # counter for yes/no choices
        _last_heading = [""]  # last non-empty prompt (context for sub-picks)
        _sub_count = [0]  # sub-pick counter within a heading group
        _last_print = [""]  # last printed line (context for sub-picks)

        _orig_pick_l1 = audit_l1._prompt_pick
        _orig_yn_l1   = audit_l1._prompt_yes_no
        _orig_yn_l2   = audit_l2._prompt_yes_no   # locally-imported copy

        class _TrackingWriter(io.StringIO):
            """StringIO that also remembers the last non-empty line written."""

            def write(self, s: str) -> int:
                stripped = s.strip()
                if stripped:
                    _last_print[0] = stripped
                return super().write(s)

        # Map calling function → semantic group
        _FUNC_GROUP = {
            "resolve_cse_choice_groups":          "ged_core",
            "select_mic_core_choices":            "mic_core",
            "select_electives_cse":               "trail",
            "select_electives_mic":               "mic_elective",
            "resolve_cse_bio_internship_choice":  "bio_internship",
        }

        def _detect_group() -> str:
            """Walk the call stack to determine the semantic group."""
            for fi in _inspect.stack()[2:6]:
                g = _FUNC_GROUP.get(fi.function)
                if g:
                    return g
            return "other"

        def _patched_pick(prompt, options, display=None):
            key = f"pick_{_pick_idx[0]}"
            _pick_idx[0] += 1
            labels = display if display and len(display) == len(options) else options
            # Use pre-supplied answer if it matches a valid option
            selected = answers.get(key)
            if selected not in options:
                selected = options[0]        # auto-select first (best grade)
            # Detect semantic group from call stack
            group = _detect_group()
            # Build a descriptive label
            clean_prompt = (prompt or "").strip()
            if clean_prompt:
                label = clean_prompt.rstrip(":")
                _last_heading[0] = label
                _sub_count[0] = 0
                # Refine group for trail / MIC elective sub-types
                if group in ("trail", "mic_elective"):
                    lp = label.lower()
                    if "primary" in lp or "secondary" in lp:
                        group = "trail"
                    elif "open elective" in lp:
                        group = "open_elective"
                    elif "major elective" in lp:
                        group = "major_elective"
                    elif "free elective" in lp:
                        group = "free_elective"
            elif _last_heading[0]:
                _sub_count[0] += 1
                # Check if the last printed line gives extra context
                lp_ctx = _last_print[0].lower()
                if "open elective" in lp_ctx:
                    label = "Open Elective"
                    group = "open_elective"
                    _last_heading[0] = label
                    _sub_count[0] = 0
                elif "course" in lp_ctx and "from '" in lp_ctx:
                    # e.g. "Course 1 of 2 from 'Algorithms and Computation':"
                    label = _last_print[0].rstrip(":").strip()
                    if group == "trail":
                        group = "trail_course"
                elif group == "mic_core":
                    # Extract label from the printed context line
                    # e.g. "LANGUAGE (4th slot) — ..." → "Language"
                    for slot_name in ("language", "humanities", "social sciences", "science"):
                        if slot_name in lp_ctx:
                            label = slot_name.title()
                            break
                    else:
                        label = f"MIC Core — slot {_sub_count[0]}"
                else:
                    label = f"{_last_heading[0]} — course {_sub_count[0]}"
                    # Sub-picks under trail headings
                    if group == "trail":
                        lh = _last_heading[0].lower()
                        if "primary" in lh or "secondary" in lh:
                            group = "trail_course"
                        elif "open elective" in lh:
                            group = "open_elective"
            else:
                if group == "mic_core":
                    lp_ctx = _last_print[0].lower()
                    for slot_name in ("language", "humanities", "social sciences", "science"):
                        if slot_name in lp_ctx:
                            label = slot_name.title()
                            break
                    else:
                        label = f"MIC Core — slot {_pick_idx[0]}"
                else:
                    label = f"Course selection {_pick_idx[0]}"
            if prompt:
                print(prompt)
            for i, lbl in enumerate(labels, 1):
                marker = " ✓" if options[i - 1] == selected else ""
                print(f"  {i}. {lbl}{marker}")
            print(f"  → {labels[options.index(selected)]}")
            _choices.append({
                "key": key, "type": "pick", "group": group,
                "label": label, "prompt": clean_prompt,
                "options": list(options), "display": list(labels),
                "selected": selected,
            })
            return selected

        def _patched_yn(prompt):
            key = f"yn_{_yn_idx[0]}"
            _yn_idx[0] += 1
            if key in answers:
                selected = bool(answers[key])
            else:
                selected = False
            tag = "Yes" if selected else "No"
            print(f"  {prompt} → {tag}")
            _choices.append({
                "key": key, "type": "yes_no", "prompt": (prompt or "").strip(),
                "selected": selected,
            })
            return selected

        audit_l1._prompt_pick   = _patched_pick
        audit_l1._prompt_yes_no = _patched_yn
        audit_l2._prompt_yes_no = _patched_yn
        audit_l1.NO_INTERACT    = True

        captured = _TrackingWriter()
        try:
            with redirect_stdout(captured):
                with _AUDIT_LOCK:
                    raw = audit_l2.run_audit(args)
        finally:
            # Always restore originals
            audit_l1._prompt_pick   = _orig_pick_l1
            audit_l1._prompt_yes_no = _orig_yn_l1
            audit_l2._prompt_yes_no = _orig_yn_l2
            audit_l1.NO_INTERACT    = False

        # ── Build Level-3 extended data ───────────────────────────────────────
        from audit_l1 import (
            normalize_course_code, get_ncl_labs, get_display_grade,
            reason_not_counted, GRADE_RANK, has_passing_attempt, is_passing,
            CSE_MINOR_MATH, CSE_MINOR_PHYSICS, PASSING_GRADES,
        )
        from audit_l2 import get_class_equivalence, CGPA_EXCLUDED_BY_PROGRAM
        from audit_l3 import compute_deficiencies

        per_course          = raw.get("per_course") or {}
        by_course           = raw.get("by_course") or {}
        program_key         = raw["program_key"]
        major_elec          = raw.get("major_electives") or []
        open_elec           = raw.get("open_elective") or ""
        free_elec           = raw.get("free_electives") or []
        prereq_failures     = raw.get("prereq_failures") or {}
        allowed_codes       = raw.get("allowed_codes") or set()
        core_excluded       = raw.get("core_excluded") or set()
        unselected_elec     = raw.get("unselected_electives") or set()
        waived_courses      = raw.get("waived_courses") or set()
        program_credits_map = raw.get("program_credits") or {}

        major_set = {normalize_course_code(c) for c in major_elec}
        free_set  = {normalize_course_code(c) for c in free_elec}
        open_code = normalize_course_code(open_elec) if open_elec else ""
        ncl       = get_ncl_labs(program_key)

        # credit_passed = graduation credits + zero-credit-but-passed (e.g. MAT116 in CSE)
        _zero_extra = 0.0
        for _n in CGPA_EXCLUDED_BY_PROGRAM.get(program_key, set()):
            _atts = by_course.get(_n, [])
            if not has_passing_attempt(_atts):
                continue
            _pass = [a for a in _atts if is_passing(a["grade"])]
            _best = max(_pass, key=lambda a: GRADE_RANK.get(a["grade"], 0))
            _zero_extra += _best["credits"]
        credit_passed = raw["total"] + _zero_extra

        def _elec_label(n: str):
            if n == open_code:
                return "Free Elective" if program_key == "MIC" else "Open Elective"
            if n in free_set:
                return "Free Elective"
            if n in major_set:
                return "Major Elective"
            return None

        # Per-course detail (counted + not-counted rows, minus NCL labs)
        per_course_detail = []
        for code, cr in sorted(per_course.items()):
            n        = normalize_course_code(code)
            if n in ncl:
                continue
            attempts = by_course.get(code, [])
            grade    = get_display_grade(attempts)
            counted  = cr > 0
            label    = _elec_label(n) if counted else None
            reason   = None if counted else reason_not_counted(
                attempts,
                course_code=code,
                program_name=program.lower(),
                allowed_codes=allowed_codes,
                program_credits=program_credits_map,
                program_key=program_key,
                core_excluded=core_excluded,
                unselected_electives=unselected_elec,
                waived_courses=waived_courses,
                prereq_failure=prereq_failures.get(n),
            )
            per_course_detail.append({
                "course":  code,
                "credits": cr if counted else None,
                "grade":   grade,
                "counted": counted,
                "label":   label,
                "reason":  reason,
            })

        # Retake ghosts: superseded / failed attempts for courses that DO count
        for code in sorted(per_course):
            n = normalize_course_code(code)
            if per_course[code] == 0 or n in ncl:
                continue
            attempts = by_course.get(code, [])
            if len(attempts) <= 1:
                continue
            passing = [a for a in attempts if is_passing(a["grade"])]
            best    = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0)) if passing else None
            best_gr = best["grade"] if best else "—"
            for a in attempts:
                if a is best:
                    continue
                if is_passing(a["grade"]):
                    rsn = f"superseded by retake — {best_gr} counts"
                else:
                    lbl_map = {"F": "failure (F)", "W": "withdrawal (W)", "I": "incomplete (I)"}
                    g = a["grade"]
                    rsn = f"{lbl_map.get(g, 'grade ' + g)} — passed on retake ({best_gr})"
                per_course_detail.append({
                    "course":  code,
                    "credits": None,
                    "grade":   a["grade"],
                    "counted": False,
                    "label":   None,
                    "reason":  rsn,
                })

        # Deficiency report (Level-3)
        def_raw = compute_deficiencies(raw)
        deficiency = {
            "eligible":         def_raw["eligible"],
            "credit_shortfall": def_raw["credit_shortfall"],
            "probation":        def_raw["probation"],
            "missing_mandatory": [
                {"category": cat, "courses": items}
                for cat, items in def_raw["missing_mandatory"]
            ],
            "prereq_failures_list": [
                {"course": c, "reason": r}
                for c, r in def_raw["prereq_failures_list"]
            ],
            "retake_note": def_raw["retake_note"],
        }

        # ── Minor program detection (CSE only) ──────────────────────────────
        minor_programs = None
        if program_key == "CSE":
            selected_minor = raw.get("selected_minor_courses") or set()
            pf_minor = {normalize_course_code(c) for c in prereq_failures}
            declared_n = selected_minor - pf_minor
            open_code_n = open_code if open_code and open_code not in pf_minor else ""
            active_n = declared_n | ({open_code_n} if open_code_n else set())

            math_active = sorted(active_n & CSE_MINOR_MATH)
            physics_active = sorted(active_n & CSE_MINOR_PHYSICS)
            math_declared = sorted(declared_n & CSE_MINOR_MATH)
            physics_declared = sorted(declared_n & CSE_MINOR_PHYSICS)

            minor_programs = []
            if math_declared or (open_code_n in CSE_MINOR_MATH):
                MATH_CORE = {"MAT120", "MAT125", "MAT130", "MAT250"}
                extras_done = [c for c in math_active if c not in MATH_CORE]
                complete = len(extras_done) >= 3
                minor_programs.append({
                    "name": "Minor in Mathematics",
                    "total_credits": 21,
                    "complete": complete,
                    "progress": f"{len(extras_done)}/3 additional courses",
                    "core_courses": sorted(MATH_CORE),
                    "declared_courses": math_declared,
                    "open_elective_course": open_elec if open_code_n in CSE_MINOR_MATH else None,
                })
            if physics_declared or (open_code_n in CSE_MINOR_PHYSICS):
                PHYS_CHOICE = {"PHY310", "PHY440"}
                has_choice = bool(set(physics_active) & PHYS_CHOICE)
                base_done = [c for c in physics_active if c not in PHYS_CHOICE]
                total_done = len(base_done) + (1 if has_choice else 0)
                complete = total_done >= 5
                choice_course = next((c for c in physics_active if c in PHYS_CHOICE), None)
                minor_programs.append({
                    "name": "Minor in Physics",
                    "total_credits": 15,
                    "complete": complete,
                    "progress": f"{total_done}/5 courses",
                    "declared_courses": physics_declared,
                    "choice_slot": {"options": ["PHY310", "PHY440"], "selected": choice_course},
                    "open_elective_course": open_elec if open_code_n in CSE_MINOR_PHYSICS else None,
                })
            if not minor_programs:
                minor_programs = None

        extras = {
            "credit_passed":      credit_passed,
            "credit_counted":     raw["total_cr_attempted"],
            "total_grade_points": raw["total_gp"],
            "academic_standing":  get_class_equivalence(float(raw["cgpa"])),
            "per_course_detail":  per_course_detail,
            "deficiency":         deficiency,
            "minor_programs":     minor_programs,
        }

        result = _serialize_result(raw, captured.getvalue(), extras)
        result["choices"] = _choices   # frontend needs these; stripped before DB save
        return result
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _serialize_result(raw: dict, console_log: str, extras: Optional[dict] = None) -> dict:
    """Convert the raw run_audit() dict into a JSON-serializable response."""
    prereq_failures = raw.get("prereq_failures") or {}
    e = extras or {}
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
        "prereq_failures":     dict(prereq_failures),
        "per_course_credits":  raw.get("per_course") or {},
        "console_log":         console_log,
        # Level-3 extended fields
        "credit_passed":       e.get("credit_passed"),
        "credit_counted":      e.get("credit_counted"),
        "total_grade_points":  e.get("total_grade_points"),
        "academic_standing":   e.get("academic_standing"),
        "per_course_detail":   e.get("per_course_detail") or [],
        "deficiency":          e.get("deficiency"),
        "minor_programs":      e.get("minor_programs"),
    }

