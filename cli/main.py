"""NSU Audit CLI — command-line interface for the audit tool.

Usage:
    nsu-audit login               Log in with your @northsouth.edu Google account
    nsu-audit logout              Log out and remove stored credentials
    nsu-audit whoami              Show the currently logged-in user
    nsu-audit run <csv>           Run an audit via the API (requires login)
    nsu-audit run-local <csv>     Run an audit locally without network (no login needed)
    nsu-audit history             List your past audit runs
"""
import json
import os
import sys
import types
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table
from rich import box

from .auth import load_token, save_token, delete_token, require_token, device_login
from . import api as _api

app = typer.Typer(
    name="nsu-audit",
    help="NSU Transcript Audit Tool",
    no_args_is_help=True,
    add_completion=False,
)

_API_URL = os.environ.get("NSU_AUDIT_API_URL", "http://localhost:8000")

# Path to program.md relative to this file (repo root)
_PROGRAM_MD = Path(__file__).parent.parent / "program.md"


# ── Login / Logout / WhoAmI ───────────────────────────────────────────────────

@app.command()
def login() -> None:
    """Log in with your @northsouth.edu Google account (Device Authorization)."""
    try:
        token = device_login(_API_URL)
    except Exception as exc:
        rprint(f"[red]Login failed:[/red] {exc}")
        raise typer.Exit(1)

    save_token(token)
    rprint("[green]✓ Logged in successfully.[/green]")
    rprint(f"  Credentials saved to ~/.config/nsu-audit/credentials.json")


@app.command()
def logout() -> None:
    """Remove locally stored credentials."""
    delete_token()
    rprint("[yellow]Logged out.[/yellow]")


@app.command()
def whoami() -> None:
    """Show the currently logged-in user."""
    token = require_token()
    try:
        data = _api.api_get(_API_URL, "/api/auth/me", token)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)
    rprint(f"[bold]{data['display_name']}[/bold]  [dim]({data['email']})[/dim]")


# ── Run audit via API ─────────────────────────────────────────────────────────

@app.command()
def run(
    transcript: Path = typer.Argument(..., help="Path to transcript CSV"),
    program:    str  = typer.Option(..., "--program", "-p", help="CSE or MIC"),
    answers:    Optional[str] = typer.Option(
        None, "--answers", "-a",
        help="Answers as inline JSON or path to a JSON file.  "
             "Keys are AK_* constants (e.g. {\"waiver_eng102\": false}).",
    ),
) -> None:
    """Run an audit via the API.  Requires login."""
    token = require_token()

    if not transcript.exists():
        rprint(f"[red]File not found:[/red] {transcript}")
        raise typer.Exit(1)

    answers_dict: dict = {}
    if answers:
        ap = Path(answers)
        if ap.exists():
            try:
                answers_dict = json.loads(ap.read_text())
            except json.JSONDecodeError as exc:
                rprint(f"[red]Bad answers JSON file:[/red] {exc}")
                raise typer.Exit(1)
        else:
            try:
                answers_dict = json.loads(answers)
            except json.JSONDecodeError as exc:
                rprint(f"[red]Bad answers JSON:[/red] {exc}")
                raise typer.Exit(1)

    rprint(f"[cyan]Running audit[/cyan] ({program}) …")
    try:
        resp = _api.api_post_multipart(
            _API_URL, "/api/audit/run", token,
            csv_path=transcript, program=program, answers=answers_dict,
        )
    except Exception as exc:
        rprint(f"[red]Audit failed:[/red] {exc}")
        raise typer.Exit(1)

    run_id = resp["run_id"]
    result = resp["result"]
    _print_result(result, run_id)


# ── Local audit (no API, no login needed) ─────────────────────────────────────

@app.command("run-local")
def run_local(
    transcript: Path = typer.Argument(..., help="Path to transcript CSV"),
    program:    str  = typer.Option(..., "--program", "-p", help="CSE or MIC"),
    answers:    Optional[str] = typer.Option(
        None, "--answers", "-a",
        help="Answers as inline JSON or path to a JSON file.",
    ),
    no_interact: bool = typer.Option(
        False, "--no-interact", help="Auto-select all choices (pipeline mode)."
    ),
) -> None:
    """Run an audit locally without the API (no login required)."""
    if not transcript.exists():
        rprint(f"[red]File not found:[/red] {transcript}")
        raise typer.Exit(1)
    if not _PROGRAM_MD.exists():
        rprint(f"[red]program.md not found at {_PROGRAM_MD}[/red]")
        raise typer.Exit(1)

    answers_dict: dict = {}
    if answers:
        ap = Path(answers)
        if ap.exists():
            try:
                answers_dict = json.loads(ap.read_text())
            except json.JSONDecodeError as exc:
                rprint(f"[red]Bad answers JSON file:[/red] {exc}")
                raise typer.Exit(1)
        else:
            try:
                answers_dict = json.loads(answers)
            except json.JSONDecodeError as exc:
                rprint(f"[red]Bad answers JSON:[/red] {exc}")
                raise typer.Exit(1)

    # Import the audit engine directly (works because CLI lives in the repo)
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from audit_l1 import AuditConfig
        import audit_l2
    except ImportError as exc:
        rprint(f"[red]Cannot import audit engine:[/red] {exc}")
        raise typer.Exit(1)

    config = AuditConfig(no_interact=no_interact, answers=answers_dict)
    args   = types.SimpleNamespace(
        transcript=transcript,
        program_name=program,
        program_knowledge=_PROGRAM_MD,
        no_interact=no_interact,
    )

    try:
        result = audit_l2.run_audit(args, config)
    except (ValueError, FileNotFoundError) as exc:
        rprint(f"[red]Audit error:[/red] {exc}")
        raise typer.Exit(1)

    # Pretty-print key stats
    rprint(f"\n[bold green]Audit complete[/bold green]")
    rprint(f"  Program:          {result['program_key']}")
    rprint(f"  Credits completed: {result['credit_completed']} / {result['required_credits']}")
    rprint(f"  CGPA:             {round(float(result['cgpa']), 2)}")
    if result.get("waived_courses"):
        rprint(f"  Waived:           {', '.join(sorted(result['waived_courses']))}")
    if result.get("prereq_failures"):
        rprint(f"  [yellow]Prereq failures:[/yellow]")
        for course, reason in result["prereq_failures"].items():
            rprint(f"    {course}: {reason}")


# ── History ───────────────────────────────────────────────────────────────────

@app.command()
def history(
    limit:  int = typer.Option(10, "--limit",  "-n", help="Max rows to show"),
    offset: int = typer.Option(0,  "--offset",       help="Pagination offset"),
) -> None:
    """List your past audit runs (most recent first)."""
    token = require_token()
    try:
        data = _api.api_get(_API_URL, "/api/history/", token, limit=limit, offset=offset)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    runs = data["runs"]
    if not runs:
        rprint("[dim]No audit runs yet.[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Run ID", style="dim", width=10)
    table.add_column("Program", width=7)
    table.add_column("CGPA",    width=6)
    table.add_column("Credits", width=12)
    table.add_column("Status",  width=10)
    table.add_column("Date",    width=20)

    for r in runs:
        cgpa    = str(r["cgpa"])    if r["cgpa"]    is not None else "—"
        credits = (
            f"{r['credit_completed']}/{r['required_credits']}"
            if r["credit_completed"] is not None else "—"
        )
        table.add_row(
            r["run_id"][:8],
            r["program"],
            cgpa,
            credits,
            r["status"],
            r["created_at"][:19].replace("T", " "),
        )

    rprint(table)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_result(result: dict, run_id: str) -> None:
    rprint(f"\n[bold green]Audit complete[/bold green]  [dim](run {run_id[:8]})[/dim]")
    rprint(f"  Program:           {result['program']}")
    rprint(f"  Credits completed: {result['credit_completed']} / {result['required_credits']}")
    rprint(f"  CGPA:              {result['cgpa']}")
    if result.get("waived_courses"):
        rprint(f"  Waived:            {', '.join(result['waived_courses'])}")
    if result.get("prereq_failures"):
        rprint("[yellow]  Prereq failures:[/yellow]")
        for course, reason in result["prereq_failures"].items():
            rprint(f"    {course}: {reason}")
    rprint()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
