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

_GROUP_LABELS: dict[str, str] = {
    "ged_core":         "GED Core Courses",
    "mic_core":         "MIC Core Courses",
    "trail":            "Trail Selection",
    "trail_course":     "Trail Courses",
    "mic_elective":     "MIC Electives",
    "major_elective":   "Major Electives",
    "free_elective":    "Free Electives",
    "open_elective":    "Open Elective",
    "bio_internship":   "Internship / Research or BIO103L",
    "other":            "Course Selections",
}


def _collect_answers_interactive(api_url, token, transcript, program):
    """Collect user answers incrementally, re-discovering after divergent picks.

    Instead of collecting all answers in one pass (which shows options based on
    auto-selected defaults), this re-runs discovery whenever the user picks
    something different from the default.  Every subsequent prompt therefore
    shows options that reflect the user's actual prior choices.
    """
    answers: dict = {}
    prev_group = ""
    header_shown = False
    max_passes = 15          # safeguard against infinite loops

    for _ in range(max_passes):
        try:
            discovery = _api.api_post_multipart(
                api_url, "/api/audit/run", token,
                csv_path=transcript, program=program, answers=answers, save=False,
            )
        except Exception as exc:
            rprint(f"[red]Audit failed:[/red] {exc}")
            raise typer.Exit(1)

        choices = discovery.get("choices", [])

        # Identify choices that still need a (valid) answer
        remaining = []
        for c in choices:
            key = c["key"]
            if key not in answers:
                remaining.append(c)
            elif c["type"] == "pick" and answers[key] not in c["options"]:
                del answers[key]
                remaining.append(c)

        if not remaining:
            break

        if not header_shown:
            rprint("\n[bold]Configure the audit:[/bold]")
            header_shown = True

        yn_remaining   = [c for c in remaining if c["type"] == "yes_no"]
        pick_remaining = [c for c in remaining if c["type"] == "pick"]

        # ── Waivers — collect all at once (independent of each other) ────
        diverged = False
        if yn_remaining:
            rprint("\n[bold cyan]── Waivers ──────────────────────────────────────────[/bold cyan]")
            rprint("[dim]Waived courses count toward Credit Completed only (not CGPA).[/dim]")
            for c in yn_remaining:
                default = c.get("selected", False)
                hint    = "[Y/n]" if default else "[y/N]"
                raw     = typer.prompt(f"  {c['prompt']} {hint}", default="")
                raw     = raw.strip().lower()
                if raw in ("y", "yes"):
                    answers[c["key"]] = True
                elif raw in ("n", "no"):
                    answers[c["key"]] = False
                else:
                    answers[c["key"]] = default
                if answers[c["key"]] != default:
                    diverged = True
            if diverged:
                continue  # re-discover with waiver answers

        # ── Picks — one at a time, re-discover on divergence ─────────────
        for c in pick_remaining:
            group       = c.get("group", "other")
            label       = c.get("label", c["key"])
            options     = c["options"]
            display     = c.get("display", options)
            default_sel = c.get("selected", options[0] if options else "")
            default_idx = (options.index(default_sel) + 1) if default_sel in options else 1

            if group != prev_group:
                group_label = _GROUP_LABELS.get(group, "Course Selections")
                pad = max(0, 47 - len(group_label))
                rprint(f"\n[bold cyan]── {group_label} {'─' * pad}[/bold cyan]")
                prev_group = group

            rprint(f"\n  [bold]{label}[/bold]")
            for i, (opt, disp) in enumerate(zip(options, display), 1):
                rprint(f"    {i}. {disp}")

            while True:
                raw = typer.prompt(
                    f"  Select [1–{len(options)}]",
                    default=str(default_idx),
                    show_default=True,
                ).strip()
                try:
                    idx = int(raw)
                    if 1 <= idx <= len(options):
                        answers[c["key"]] = options[idx - 1]
                        break
                except ValueError:
                    pass
                if raw.upper() in options:
                    answers[c["key"]] = raw.upper()
                    break
                rprint(f"  [red]Enter a number between 1 and {len(options)}.[/red]")

            if answers[c["key"]] != default_sel:
                diverged = True
                break  # stop collecting; re-discover to refresh downstream options

        if not diverged:
            break  # all remaining picks matched defaults — done

    return answers


@app.command()
def run(
    transcript: Path = typer.Argument(..., help="Path to transcript CSV or image/PDF"),
    program:    str  = typer.Option(..., "--program", "-p", help="CSE or MIC"),
    answers:    Optional[str] = typer.Option(
        None, "--answers", "-a",
        help="Skip prompts — supply answers as inline JSON or path to a JSON file.  "
             "Keys are pick_N / yn_N (e.g. {\"yn_0\": true}).",
    ),
) -> None:
    """Run an audit via the API.  Requires login."""
    token = require_token()

    if not transcript.exists():
        rprint(f"[red]File not found:[/red] {transcript}")
        raise typer.Exit(1)

    answers_dict: dict = {}
    if answers:
        # Batch / scripted mode: use pre-supplied answers, skip prompts
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
    else:
        # Interactive mode — incremental discovery + user picks
        rprint(f"[cyan]Loading choices[/cyan] ({program}) …")
        answers_dict = _collect_answers_interactive(
            _API_URL, token, transcript, program,
        )

        rprint(f"\n[cyan]Running audit[/cyan] ({program}) …")

    try:
        resp = _api.api_post_multipart(
            _API_URL, "/api/audit/run", token,
            csv_path=transcript, program=program, answers=answers_dict, save=True,
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
    if result.get("academic_standing"):
        rprint(f"  Standing:          {result['academic_standing']}")
    if result.get("waived_courses"):
        rprint(f"  Waived:            {', '.join(result['waived_courses'])}")
    if result.get("major_electives"):
        rprint(f"  Major electives:   {', '.join(result['major_electives'])}")
    if result.get("open_elective"):
        rprint(f"  Open elective:     {result['open_elective']}")
    if result.get("free_electives"):
        rprint(f"  Free electives:    {', '.join(result['free_electives'])}")
    if result.get("prereq_failures"):
        rprint("[yellow]  Prereq failures:[/yellow]")
        for course, reason in result["prereq_failures"].items():
            rprint(f"    {course}: {reason}")
    not_counted = [
        r for r in result.get("per_course_detail", [])
        if not r["counted"] and r.get("reason")
    ]
    if not_counted:
        rprint("[yellow]  Not counted:[/yellow]")
        for r in not_counted:
            rprint(f"    {r['course']}: {r['reason']}")
    rprint()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
