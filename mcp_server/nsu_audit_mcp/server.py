"""NSU Audit MCP Server.

Exposes the NSU Transcript Audit backend as a set of Model Context Protocol tools
so AI assistants (opencode, Claude Desktop, etc.) can run graduation eligibility
audits on behalf of students and faculty.

Configuration — environment variables:
  NSU_AUDIT_BASE_URL   Backend base URL  (default: http://localhost:8000)

Typical workflow:
  1. nsu_oauth_start / nsu_oauth_complete  — authenticate with @northsouth.edu account
  2. discover_choices                       — learn what interactive decisions are needed
  3. run_audit                              — run the full audit with resolved answers
  4. Interpret deficiency field             — advise student on missing requirements

For transcripts stored in Google Drive:
  gdrive_authorize (open auth_url in browser) → gdrive_authorize_complete
  → gdrive_list_files → gdrive_download_and_audit

── Hosted vs stdio mode ──────────────────────────────────────────────────────
When running as a hosted HTTP/SSE server (mounted in FastAPI), each connecting
client has its own FastMCP session.  JWTs are stored in session state via
ctx.set_state / ctx.get_state — fully isolated per user.

When running as a local stdio binary (classic mode), session state still works
and tokens are ALSO saved to disk (~/.config/nsu-audit-mcp/credentials.json)
so they persist across process restarts without re-authentication.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from fastmcp import Context, FastMCP

from ._auth import (
    clear_pending,
    clear_token,
    delete_token,
    get_pending,
    get_token,
    poll_with_pending,
    store_pending,
    store_token,
)
from ._client import (
    _base_url,
    _handle,
    api_delete,
    api_get,
    api_post,
    get_token_or_raise,
)
from ._gdrive import (
    gdrive_auth_status,
    gdrive_download_file,
    gdrive_list_files as _gdrive_list_files,
    start_gdrive_flow,
)
from ._gmail import (
    gmail_auth_status,
    send_report_via_backend,
    start_gmail_flow,
)

# ── MCP application ───────────────────────────────────────────────────────────

mcp = FastMCP(
    name="nsu-audit",
    instructions=(
        "Tools for running graduation eligibility audits on NSU (North South University) "
        "student transcripts. Programs supported: CSE (130 credits) and MIC (120 credits).\n\n"
        "Typical OAuth → Audit workflow:\n"
        "  1. nsu_oauth_start   — begin Google OAuth 2.0 device flow (RFC 8628)\n"
        "  2. nsu_oauth_complete — finish after browser approval\n"
        "  3. discover_choices(transcript_path, program) — learn what picks/waivers are needed\n"
        "  4. run_audit(transcript_path, program, answers) — full audit, get result + deficiency\n\n"
        "For transcripts on Google Drive:\n"
        "  gdrive_authorize (open auth_url) → gdrive_authorize_complete "
        "→ gdrive_list_files → gdrive_download_and_audit\n\n"
        "Catalog / requirements queries (no session needed):\n"
        "  lookup_course, list_program_requirements\n\n"
        "Gmail report tools (requires gmail_authorize first):\n"
        "  gmail_authorize (open auth_url) → gmail_authorize_complete → send_audit_report"
    ),
)

# ── Constants ─────────────────────────────────────────────────────────────────

_ALLOWED_EXTS = {".csv", ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
_MAX_BYTES    = 10 * 1024 * 1024   # 10 MB — mirrors backend limit

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

_EXT_TO_MIME = {
    ".csv":  "text/csv",
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".tif":  "image/tiff",
    ".tiff": "image/tiff",
    ".bmp":  "image/bmp",
}

# ── Input validators ──────────────────────────────────────────────────────────

def _validate_program(program: str) -> str:
    p = program.strip().upper()
    if p not in ("CSE", "MIC"):
        raise ValueError("program must be 'CSE' or 'MIC'.")
    return p


def _validate_run_id(run_id: str) -> str:
    rid = run_id.strip()
    if not _UUID_RE.match(rid):
        raise ValueError(
            "run_id must be a valid UUID (e.g. '550e8400-e29b-41d4-a716-446655440000')."
        )
    return rid.lower()


def _validate_transcript_path(path: str) -> Path:
    """Resolve and validate a local transcript path."""
    import os
    
    # Rewrite local macOS path to Docker container /app path if necessary
    local_prefix = "/Users/rudratahsin/Developer/The-Dept.-Admin-Audit-Core-"
    if path.startswith(local_prefix):
        path = "/app" + path[len(local_prefix):]
        
    p = Path(path).resolve()
    if not p.is_file():
        raise ValueError(f"File not found or not a regular file: {path!r} (resolved to {p})")
    ext = p.suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise ValueError(
            f"Unsupported extension '{ext}'. "
            f"Accepted: {', '.join(sorted(_ALLOWED_EXTS))}"
        )
    size = p.stat().st_size
    if size > _MAX_BYTES:
        raise ValueError(
            f"File is {size / 1024 / 1024:.1f} MB; maximum is 10 MB."
        )
    return p


def _upload_transcript(
    path: Path,
    program: str,
    answers: dict,
    save: bool,
    token: str,
) -> dict:
    """POST a transcript file to the backend /api/audit/run endpoint."""
    content  = path.read_bytes()
    ext      = path.suffix.lower()
    mime     = _EXT_TO_MIME.get(ext, "application/octet-stream")

    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{_base_url()}/api/audit/run",
            headers={"Authorization": f"Bearer {token}"},
            files={"transcript": (path.name, content, mime)},
            data={
                "program": program,
                "answers": json.dumps(answers),
                "save":    "true" if save else "false",
            },
        )
    return _handle(resp)


# ── Catalog loader (shared by lookup_course) ──────────────────────────────────

_CATALOG: Optional[set] = None


def _load_catalog() -> set:
    global _CATALOG
    if _CATALOG is None:
        candidates = [
            Path(__file__).parent.parent.parent / "nsu_catalog.json",
            Path(__file__).parent / "data" / "nsu_catalog.json",
        ]
        for p in candidates:
            if p.exists():
                try:
                    _CATALOG = set(json.loads(p.read_text()))
                    break
                except Exception:
                    pass
        if _CATALOG is None:
            _CATALOG = set()
    return _CATALOG


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_device_start(base_url: str) -> dict:
    """Blocking helper — call the backend's device/start endpoint."""
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{base_url}/api/auth/device/start")
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to start OAuth flow: {resp.text}")
    return resp.json()


@mcp.tool()
async def nsu_oauth_start(ctx: Context) -> dict:
    """Begin Google OAuth 2.0 Device Authorization for the NSU Audit API.

    This is a standard OAuth 2.0 device flow (RFC 8628) — no passwords are
    handled by this tool. It asks Google's authorization server for a
    ``user_code`` and ``verification_url`` that the student opens in their
    own browser to grant read-only access to their NSU audit data.

    Steps:
      1. Call this tool — it returns ``user_code`` and ``verification_url``.
      2. Open ``verification_url`` in a browser and enter ``user_code``.
      3. Approve access (only @northsouth.edu accounts are accepted).
      4. Call ``nsu_oauth_complete`` to exchange the grant for an API session.
    """
    # Run the blocking HTTP call in a thread so the event loop stays free.
    # This is critical when running in hosted mode (MCP mounted inside FastAPI)
    # — a direct blocking call would deadlock the shared event loop.
    data = await asyncio.to_thread(_fetch_device_start, _base_url())
    # Store in session state (isolated per user in hosted mode) + disk (stdio mode).
    await store_pending(ctx, data)
    return {
        "user_code":        data["user_code"],
        "verification_url": data["verification_url"],
        "next_step": (
            "Open the verification_url in a browser, enter the user_code when prompted, "
            "approve access, then call `nsu_oauth_complete`."
        ),
    }


@mcp.tool()
async def nsu_oauth_complete(ctx: Context) -> dict:
    """Complete the Google OAuth 2.0 device flow after browser approval.

    Call this after the user has entered ``user_code`` at the
    ``verification_url`` and approved access in their browser.
    Polls Google's token endpoint (RFC 8628 §3.5) for up to 30 seconds.
    If still waiting, confirm browser approval and call this tool again.
    """
    pending = await get_pending(ctx)
    if not pending:
        raise RuntimeError(
            "No pending login found. Call `nsu_oauth_start` first."
        )

    # Run the blocking poll in a thread so we don't stall the event loop.
    try:
        access_token = await asyncio.to_thread(
            poll_with_pending, _base_url(), pending
        )
    except RuntimeError:
        await clear_pending(ctx)
        raise

    await store_token(ctx, access_token)
    await clear_pending(ctx)

    try:
        parts   = access_token.split(".")
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(
            base64.urlsafe_b64decode(parts[1] + "=" * padding)
        )
        return {
            "ok":           True,
            "email":        payload.get("email", ""),
            "display_name": payload.get("name", ""),
            "message":      "OAuth session established. Valid for 7 days.",
        }
    except Exception:
        return {"ok": True, "message": "OAuth session established."}


@mcp.tool()
async def nsu_sign_out(ctx: Context) -> dict:
    """Revoke the local NSU Audit API session.

    Removes the JWT from session state (hosted mode) and from disk (stdio mode).
    The JWT itself is stateless and expires automatically after 7 days.
    """
    await clear_token(ctx)
    return {"ok": True, "message": "Session revoked. Credentials removed."}


@mcp.tool()
async def nsu_current_user(ctx: Context) -> dict:
    """Return the profile of the currently authenticated NSU Audit API user.

    Returns user_id, email, display_name, and is_admin flag from the
    active OAuth session. Raises an error if no session exists or it
    has expired — call ``nsu_oauth_start`` to create a new one.
    """
    token = await get_token_or_raise(ctx)
    return await asyncio.to_thread(api_get, "/api/auth/me", token)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def discover_choices(
    ctx: Context,
    transcript_path: str,
    program: str,
    answers: Optional[dict] = None,
) -> dict:
    """Preview the interactive choices the audit engine will ask for.

    Submits the transcript without saving a run record and returns a
    ``choices`` array that describes every decision point:
      - Waiver confirmations (ENG102, MAT112)
      - Specialization trail selection (CSE only — 6 available trails)
      - Elective course picks
      - Internship/project slot choices

    Use the ``choices`` array to build a complete ``answers`` dict of the form::

        {
          "yn_0": true,          # waiver accepted
          "pick_0": "CSE440",    # trail course 1
          "pick_1": "CSE445",    # trail course 2
          ...
        }

    Then pass that dict to ``run_audit``.  Call this tool again with a
    partial ``answers`` dict whenever a pick changes the downstream options.

    Args:
        transcript_path: Absolute path to the transcript file (.csv, .pdf, image).
        program:         Degree program — ``'CSE'`` or ``'MIC'``.
        answers:         Optional partial answers dict from a previous call.
    """
    token = await get_token_or_raise(ctx)
    p     = _validate_transcript_path(transcript_path)
    prog  = _validate_program(program)
    return await asyncio.to_thread(
        _upload_transcript, p, prog, answers or {}, False, token
    )


@mcp.tool()
async def run_audit(
    ctx: Context,
    transcript_path: str,
    program: str,
    answers: Optional[dict] = None,
    save: bool = True,
) -> dict:
    """Run a full graduation eligibility audit on a student transcript.

    Accepts CSV (already converted), PDF, or a scanned image.
    For PDFs and images the backend OCR-converts the file automatically.

    Returns a result dict that includes:
      - ``cgpa``              Computed GPA on the NSU 4.0 scale
      - ``credit_completed``  Total valid credits earned
      - ``required_credits``  Credits needed for the degree (130 CSE / 120 MIC)
      - ``academic_standing`` First Class / Second Class / Third Class / Below Standard
      - ``deficiency``        Eligibility verdict with:
          - ``eligible``              bool
          - ``credit_shortfall``      float (0 if none)
          - ``probation``             bool (CGPA < 2.0)
          - ``missing_mandatory``     list of {category, courses[]}
          - ``prereq_failures_list``  list of {course, reason}
      - ``run_id``            UUID for later retrieval (only when save=True)

    Call ``discover_choices`` first to learn what keys to include in ``answers``.

    Args:
        transcript_path: Absolute path to the transcript file (.csv, .pdf, image).
        program:         Degree program — ``'CSE'`` or ``'MIC'``.
        answers:         Pre-supplied choices dict (keys: pick_0, yn_0, ...).
        save:            Persist the run to the database (default True).
    """
    token = await get_token_or_raise(ctx)
    p     = _validate_transcript_path(transcript_path)
    prog  = _validate_program(program)
    return await asyncio.to_thread(
        _upload_transcript, p, prog, answers or {}, save, token
    )


@mcp.tool()
async def get_audit_run(ctx: Context, run_id: str) -> dict:
    """Retrieve the full result and answers for a previously saved audit run.

    Args:
        run_id: UUID of the audit run (from the ``run_audit`` response).
    """
    token = await get_token_or_raise(ctx)
    rid   = _validate_run_id(run_id)
    return await asyncio.to_thread(api_get, f"/api/audit/{rid}", token)


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def list_audit_history(
    ctx: Context,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List the authenticated user's past audit runs, most recent first.

    Returns a lightweight summary per run (cgpa, credit_completed, program,
    status, timestamps).  Use ``get_audit_run`` for the full result of a run.

    Args:
        limit:  Number of runs to return (1–100, default 20).
        offset: Pagination offset (default 0).
    """
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    if offset < 0:
        raise ValueError("offset must be non-negative.")
    token = await get_token_or_raise(ctx)
    return await asyncio.to_thread(
        api_get, f"/api/history/?limit={limit}&offset={offset}", token
    )


@mcp.tool()
async def get_history_run(ctx: Context, run_id: str) -> dict:
    """Get the full result and stored answers for a specific past audit run.

    Args:
        run_id: UUID of the audit run.
    """
    token = await get_token_or_raise(ctx)
    rid   = _validate_run_id(run_id)
    return await asyncio.to_thread(api_get, f"/api/history/{rid}", token)


@mcp.tool()
async def delete_audit_run(ctx: Context, run_id: str) -> dict:
    """Permanently delete a past audit run from the database.

    This action is irreversible.  Only the owner of the run can delete it.

    Args:
        run_id: UUID of the audit run to delete.
    """
    token = await get_token_or_raise(ctx)
    rid   = _validate_run_id(run_id)
    return await asyncio.to_thread(api_delete, f"/api/history/{rid}", token)


# ═══════════════════════════════════════════════════════════════════════════════
# CATALOG & REQUIREMENTS TOOLS  (no auth required)
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def lookup_course(course_code: str) -> dict:
    """Check whether a course code exists in the NSU Spring 2026 catalog.

    Useful for validating elective selections before running an audit.

    Args:
        course_code: NSU course code, e.g. ``'CSE115'``, ``'MAT250'``, ``'ENG102'``.
    """
    code = course_code.strip().upper()
    if not re.fullmatch(r"[A-Z]{2,4}[0-9]{3}[A-Z]?", code):
        raise ValueError(
            f"Invalid course code format: {course_code!r}. "
            "Expected format: 2–4 letters + 3 digits (e.g. CSE115, MAT130)."
        )
    catalog    = _load_catalog()
    in_catalog = code in catalog
    return {
        "course_code":    code,
        "in_nsu_catalog": in_catalog,
        "note": "" if in_catalog else "Not found in the NSU Spring 2026 catalog.",
    }


@mcp.tool()
def list_program_requirements(program: str) -> dict:
    """Return the credit structure and graduation requirements for a degree program.

    Args:
        program: ``'CSE'`` (Computer Science & Engineering) or ``'MIC'`` (Microbiology).
    """
    prog = _validate_program(program)

    if prog == "CSE":
        return {
            "program":                "CSE",
            "total_required_credits": 130,
            "minimum_cgpa":           2.0,
            "academic_standing": {
                "First Class":    "CGPA >= 3.0",
                "Second Class":   "CGPA 2.5 – 2.99",
                "Third Class":    "CGPA 2.0 – 2.49",
                "Below Standard": "CGPA < 2.0 (ineligible)",
            },
            "categories": {
                "University Core": {
                    "credits": 21,
                    "notes": (
                        "MAT116 (0cr, prereq-only), MAT125, MAT130, PHY107+L, "
                        "CHE101+L, BIO103, and one of: BIO103L / CSE498R / CSE498I (1 cr)"
                    ),
                },
                "GED (General Education)": {
                    "credits": 21,
                    "notes": (
                        "ENG102 (waiverable, 3cr), BUS101, ECO101, CIS101 (3cr each). "
                        "Choice groups: PHI101 or PHI104; SOC101 or ANT101; "
                        "PSY101, PSY201, or SOC201."
                    ),
                },
                "CSE Core": {
                    "credits": 60,
                    "key_courses": [
                        "CSE115+L", "CSE215", "CSE225", "CSE231L", "CSE311+L",
                        "CSE321", "CSE331+L", "CSE341+L", "CSE411", "CSE421",
                        "CSE422", "CSE431", "CSE461+L",
                    ],
                },
                "Specialization Trail": {
                    "credits": 9,
                    "notes": "3 electives from one trail.",
                    "trails": [
                        "Algorithms & Computation",
                        "Software Engineering",
                        "Computer Networks",
                        "VLSI Design",
                        "Artificial Intelligence",
                        "Bioinformatics",
                    ],
                },
                "Open Elective": {
                    "credits": 3,
                    "notes": "Any valid NSU course not already counted (capped at 3 cr).",
                },
                "Internship": {
                    "credits": 3,
                    "course":  "CSE400 (or CSE498R/CSE498I in BIO103L slot)",
                },
                "Senior Project": {
                    "credits": 6,
                    "courses": ["CSE499A (3cr)", "CSE499B (3cr)"],
                },
            },
            "waiverable_courses": {
                "ENG102": "English Language course — counts toward credits completed but not CGPA",
                "MAT116": "0-credit prerequisite-only course — excluded from CGPA",
            },
        }

    else:  # MIC
        return {
            "program":                "MIC",
            "total_required_credits": 120,
            "minimum_cgpa":           2.0,
            "academic_standing": {
                "First Class":    "CGPA >= 3.0",
                "Second Class":   "CGPA 2.5 – 2.99",
                "Third Class":    "CGPA 2.0 – 2.49",
                "Below Standard": "CGPA < 2.0 (ineligible)",
            },
            "categories": {
                "University Core": {
                    "credits": 18,
                    "notes": (
                        "MAT112 (waiverable), PHY107+L, CHE101+L, CHE102+L, "
                        "BIO103+L, MAT125"
                    ),
                },
                "SHLS Core (Humanities / Social / Language)": {
                    "credits": 18,
                    "notes": (
                        "ENG102 (waiverable), plus language, humanities, and "
                        "social science choice groups."
                    ),
                },
                "Major Core": {
                    "credits": 60,
                    "notes":   "MIC-prefix required courses.",
                },
                "Major Electives": {
                    "credits": 9,
                    "notes":   "3 MIC-prefix elective courses.",
                },
                "Free Electives": {
                    "credits": 9,
                    "notes":   "3 courses from anywhere in the NSU catalog.",
                },
            },
            "waiverable_courses": {
                "ENG102": "Counted toward credits completed but not CGPA",
                "MAT112": "Counted toward credits completed but not CGPA",
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN TOOL
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_admin_stats(ctx: Context) -> dict:
    """Return platform-wide aggregate statistics. Requires admin access.

    Includes:
      - ``total_runs``, ``total_users``
      - ``runs_by_program`` (CSE vs MIC counts)
      - ``avg_cgpa``, ``avg_credits``
      - ``recent_runs`` (last 20 runs across all users with user identity)

    Raises a 403 error if the authenticated user is not an admin.
    """
    token = await get_token_or_raise(ctx)
    return await asyncio.to_thread(api_get, "/api/admin/stats", token)


# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE DRIVE TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def gdrive_authorize(ctx: Context) -> dict:
    """Start Google Drive read-only authorization (OAuth 2.0 web flow).

    The backend handles all OAuth credentials — they never reach this client.

    Returns an ``auth_url``:
      1. Open ``auth_url`` in any browser.
      2. Sign in with your Google account and approve read-only Drive access.
      3. The backend stores the token automatically — nothing more to do.
    Then call ``gdrive_authorize_complete`` to confirm the token was stored.

    Access is strictly read-only (``drive.readonly`` scope, no modifications).
    """
    token  = await get_token_or_raise(ctx)
    result = await asyncio.to_thread(start_gdrive_flow, token)
    return result


@mcp.tool()
async def gdrive_authorize_complete(ctx: Context) -> dict:
    """Confirm Google Drive authorization succeeded after browser approval.

    Call after opening the ``auth_url`` from ``gdrive_authorize`` and
    approving access.  The backend stores the token automatically via
    the OAuth callback — this just verifies it worked.
    """
    token  = await get_token_or_raise(ctx)
    status = await asyncio.to_thread(gdrive_auth_status, token)
    if status.get("authorized"):
        return {
            "ok":      True,
            "message": "Google Drive read-only access authorized successfully.",
        }
    return {
        "ok":      False,
        "message": (
            "Drive authorization not yet detected. "
            "Make sure you opened the auth_url and approved access in the browser, "
            "then try again."
        ),
    }


@mcp.tool()
async def gdrive_list_files(
    ctx: Context,
    search: str = "",
    page_size: int = 20,
) -> list:
    """List PDF and image files in the user's Google Drive.

    Without a ``search`` term, returns PDFs and images ordered by most
    recently modified — useful to surface the latest transcript upload.

    Args:
        search:    Optional filename search term (e.g. ``'transcript'``).
        page_size: Number of results to return (1–100, default 20).

    Returns a list of file objects with ``id``, ``name``, ``mimeType``,
    ``size``, and ``modifiedTime``.  Pass the ``id`` to
    ``gdrive_download_and_audit``.
    """
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100.")
    token = await get_token_or_raise(ctx)
    return await asyncio.to_thread(
        _gdrive_list_files, token, search, page_size
    )


@mcp.tool()
async def gdrive_download_and_audit(
    ctx: Context,
    file_id: str,
    program: str,
    answers: Optional[dict] = None,
    save: bool = True,
) -> dict:
    """Download a transcript from Google Drive and run a graduation eligibility audit.

    Combines Google Drive download and ``run_audit`` in one step.
    The file is downloaded to a secure temporary path, submitted to the
    backend, and the temp file is deleted immediately after.

    Requires both NSU Audit login and Google Drive authorization.

    Args:
        file_id: Google Drive file ID (from ``gdrive_list_files``).
        program: Degree program — ``'CSE'`` or ``'MIC'``.
        answers: Pre-supplied choices dict (see ``discover_choices``).
        save:    Persist the run to the database (default True).
    """
    token = await get_token_or_raise(ctx)
    prog  = _validate_program(program)

    file_bytes, filename = await asyncio.to_thread(
        gdrive_download_file, token, file_id
    )

    ext = Path(filename).suffix.lower()
    if not ext:
        ext = ".pdf"
    if ext not in _ALLOWED_EXTS:
        raise ValueError(
            f"Unsupported file extension '{ext}' from Google Drive. "
            f"Accepted: {', '.join(sorted(_ALLOWED_EXTS))}"
        )

    fd, tmp_str = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        tmp.write_bytes(file_bytes)
        safe_name = Path(filename).name or f"transcript{ext}"
        tmp = tmp.rename(tmp.parent / safe_name)
        return await asyncio.to_thread(
            _upload_transcript, tmp, prog, answers or {}, save, token
        )
    finally:
        tmp.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# GMAIL TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def gmail_authorize(ctx: Context) -> dict:
    """Start Gmail send-only authorization (OAuth 2.0 web flow).

    The backend handles all OAuth credentials — they never reach this client.
    The Google Cloud project must have the Gmail API enabled.

    Returns an ``auth_url``:
      1. Open ``auth_url`` in any browser.
      2. Sign in with your Google account and approve send-only Gmail access.
      3. The backend stores the token automatically — nothing more to do.
    Then call ``gmail_authorize_complete`` to confirm the token was stored.

    Only the ``gmail.send`` scope is requested — inbox is never read.
    """
    token  = await get_token_or_raise(ctx)
    result = await asyncio.to_thread(start_gmail_flow, token)
    return result


@mcp.tool()
async def gmail_authorize_complete(ctx: Context) -> dict:
    """Confirm Gmail authorization succeeded after browser approval.

    Call after opening the ``auth_url`` from ``gmail_authorize`` and
    approving access.  The backend stores the token automatically via
    the OAuth callback — this just verifies it worked.
    """
    token  = await get_token_or_raise(ctx)
    status = await asyncio.to_thread(gmail_auth_status, token)
    if status.get("authorized"):
        return {
            "ok":      True,
            "message": "Gmail send-only access authorized successfully.",
        }
    return {
        "ok":      False,
        "message": (
            "Gmail authorization not yet detected. "
            "Make sure you opened the auth_url and approved access in the browser, "
            "then try again."
        ),
    }


@mcp.tool()
async def send_audit_report(
    ctx: Context,
    run_id: str,
    to: str,
    subject: Optional[str] = None,
) -> dict:
    """Send an audit result as an Excel report via Gmail.

    The backend fetches the saved audit run, builds a multi-sheet .xlsx
    workbook (Summary, Course Grades, Missing Courses, Prereq Failures), and
    emails it to the recipient with a plain-text summary in the message body.

    Requires:
      - NSU Audit login  (``nsu_oauth_start`` / ``nsu_oauth_complete``)
      - Gmail authorization (``gmail_authorize`` / ``gmail_authorize_complete``)

    Args:
        run_id:  UUID of the saved audit run (from ``run_audit`` response).
        to:      Recipient email address (e.g. ``'advisor@northsouth.edu'``).
        subject: Optional custom subject line.
    """
    token = await get_token_or_raise(ctx)
    rid   = _validate_run_id(run_id)
    return await asyncio.to_thread(
        send_report_via_backend, token, rid, to, subject
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Run the MCP server over stdio (compatible with opencode, Claude Desktop, etc.)."""
    mcp.run()
