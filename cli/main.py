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
import shutil
import sys
import types
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.table import Table
from rich import box
from rich.padding import Padding
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape

from .auth import load_token, save_token, delete_token, require_token, device_login
from . import api as _api
from .branding import header_panel

app = typer.Typer(
    name="nsu-audit",
    help="NSU Transcript Audit Tool",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _tui_callback(ctx: typer.Context) -> None:
    """Launch the interactive TUI when called with no sub-command."""
    if ctx.invoked_subcommand is None:
        _tui()

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
    "minor_declare":    "Minor Declaration",
    "trail":            "Trail Selection",
    "trail_course":     "Trail Courses",
    "mic_elective":     "MIC Electives",
    "major_elective":   "Major Electives",
    "free_elective":    "Free Electives",
    "open_elective":    "Open Elective",
    "bio_internship":   "Internship / Research or BIO103L",
    "other":            "Course Selections",
}

# ── Content panels (double border, width fits inner lines) ───────────────────
_BC = "#c15f3c"


def _content_panel(rows: list[str | None]) -> Panel:
    """Render lines inside a compact Panel. Use None for an inner horizontal rule."""
    str_rows = [r for r in rows if r is not None]
    max_len = max((len(r) for r in str_rows), default=12)
    term = shutil.get_terminal_size(fallback=(100, 24)).columns
    sep_w = max(8, min(max_len, max(12, term - 8)))

    parts: list[Text] = []
    for r in rows:
        if r is None:
            parts.append(Text("─" * sep_w, style=_BC))
        else:
            parts.append(Text(escape(r)))
    return Panel(
        Group(*parts),
        border_style=_BC,
        box=box.DOUBLE,
        expand=False,
        padding=(0, 1),
    )


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
            rprint()
            rprint(_content_panel(["CONFIGURE THE AUDIT"]))
            header_shown = True

        yn_remaining   = [c for c in remaining if c["type"] == "yes_no"]
        pick_remaining = [c for c in remaining if c["type"] == "pick"]

        # ── Waivers — all questions together in one box ──────────────────
        diverged = False
        if yn_remaining:
            rprint()
            waiver_rows: list[str | None] = [
                "WAIVER CHECK",
                "Waived courses count toward Credit Completed only (not Credit Counted or CGPA).",
                None,
                "",
            ]
            for c in yn_remaining:
                default = c.get("selected", False)
                hint    = "[Y/n]" if default else "[y/N]"
                waiver_rows.append(f"  {c['prompt']} {hint}")
            waiver_rows.append("")
            rprint(_content_panel(waiver_rows))
            # Collect answers after the box is fully drawn
            verdicts: list[str] = []
            for c in yn_remaining:
                default = c.get("selected", False)
                course  = c["prompt"].split()[1]  # "Is ENG102 waived…" → "ENG102"
                raw = typer.prompt(f"  {course}", default="").strip().lower()
                if raw in ("y", "yes"):
                    answers[c["key"]] = True
                elif raw in ("n", "no"):
                    answers[c["key"]] = False
                else:
                    answers[c["key"]] = default
                verdict = "waived" if answers[c["key"]] else "not waived"
                verdicts.append(f"  \u2713  {course} \u2014 {verdict}.")
                if answers[c["key"]] != default:
                    diverged = True
            rprint(_content_panel(verdicts))
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

            pick_rows: list[str | None] = []
            if group != prev_group:
                group_label = _GROUP_LABELS.get(group, "Course Selections")
                rprint()
                pick_rows.extend([group_label.upper(), None])
                prev_group = group
            pick_rows.extend(["", f"  {label}"])
            for i, (opt, disp) in enumerate(zip(options, display), 1):
                marker = "  \u25c4 default" if opt == default_sel else ""
                pick_rows.append(f"    {i}. {disp}{marker}")
            rprint(_content_panel(pick_rows))

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

            chosen_disp = display[options.index(answers[c["key"]])]
            rprint(_content_panel([f"    \u2713  {chosen_disp}  selected."]))

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
    _print_result(result, run_id, transcript_name=transcript.name)


# ── Local audit (no API, no login needed) ─────────────────────────────────────

_LOCAL_OCR_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


@app.command("run-local")
def run_local(
    transcript: Path = typer.Argument(..., help="Path to transcript CSV, PDF, or image"),
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

    # ── OCR pre-processing for PDF / image files ──────────────────────────────
    if transcript.suffix.lower() in _LOCAL_OCR_EXTS:
        _repo = Path(__file__).parent.parent
        if str(_repo) not in sys.path:
            sys.path.insert(0, str(_repo))
        try:
            from run_pipeline import convert_transcript
        except ImportError as exc:
            rprint(f"[red]OCR engine not available:[/red] {exc}")
            raise typer.Exit(1)
        import tempfile
        rprint(f"[cyan]Converting {transcript.suffix.upper()} to CSV via OCR…[/cyan]")
        with tempfile.TemporaryDirectory() as _tmpdir:
            tmp_csv = Path(_tmpdir) / (transcript.stem + ".csv")
            try:
                convert_transcript(transcript, tmp_csv)
            except SystemExit as exc:
                rprint(f"[red]OCR failed:[/red] {exc}")
                raise typer.Exit(1)
            _run_local_csv(tmp_csv, program, answers, no_interact)
        return

    _run_local_csv(transcript, program, answers, no_interact)


def _run_local_csv(
    transcript: Path,
    program: str,
    answers: Optional[str],
    no_interact: bool,
) -> None:
    """Core local-audit logic — expects a CSV file."""
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
        import audit_l1 as _al1
        import audit_l2
        import audit_l3
    except ImportError as exc:
        rprint(f"[red]Cannot import audit engine:[/red] {exc}")
        raise typer.Exit(1)

    args = types.SimpleNamespace(
        transcript=transcript,
        program_name=program,
        program_knowledge=_PROGRAM_MD,
        no_interact=no_interact,
    )

    # Monkey-patch prompts to consume pre-supplied answers (fall back to
    # auto-select when an answer key is absent or invalid).
    _pick_idx = [0]
    _yn_idx   = [0]
    _orig_pick   = _al1._prompt_pick
    _orig_yn_l1  = _al1._prompt_yes_no
    _orig_yn_l2  = audit_l2._prompt_yes_no

    def _ans_pick(prompt, options, display=None):
        key = f"pick_{_pick_idx[0]}"
        _pick_idx[0] += 1
        sel = answers_dict.get(key)
        if sel not in options:
            if no_interact or answers_dict:
                sel = options[0]
            else:
                return _orig_pick(prompt, options, display)
        labels = display if display and len(display) == len(options) else options
        if prompt:
            print(prompt)
        for i, lbl in enumerate(labels, 1):
            print(f"  {i}. {lbl}")
        print(f"  \u2192 {labels[options.index(sel)]}")
        return sel

    def _ans_yn(prompt):
        key = f"yn_{_yn_idx[0]}"
        _yn_idx[0] += 1
        if key in answers_dict:
            sel = bool(answers_dict[key])
            print(f"  {prompt} \u2192 {'Yes' if sel else 'No'}")
            return sel
        if no_interact or answers_dict:
            print(f"  [auto] {prompt} \u2192 No")
            return False
        return _orig_yn_l1(prompt)

    if answers_dict or no_interact:
        _al1._prompt_pick        = _ans_pick
        _al1._prompt_yes_no      = _ans_yn
        audit_l2._prompt_yes_no  = _ans_yn
        _al1.NO_INTERACT         = True

    try:
        result = audit_l2.run_audit(args)
    except (ValueError, FileNotFoundError) as exc:
        rprint(f"[red]Audit error:[/red] {exc}")
        raise typer.Exit(1)
    finally:
        _al1._prompt_pick        = _orig_pick
        _al1._prompt_yes_no      = _orig_yn_l1
        audit_l2._prompt_yes_no  = _orig_yn_l2
        _al1.NO_INTERACT         = False

    # Full L3-style report (audit engine already printed waivers/electives above)
    audit_l2.print_report(
        result["transcript_path"], result["program_name"],
        result["total"], result["per_course"], result["by_course"],
        result["required_credits"],
        result["cgpa"], result["total_gp"], result["total_cr_attempted"],
        result["per_course_cgpa"], result["waiver_notes"],
        allowed_codes=result["allowed_codes"],
        program_credits=result["program_credits"],
        program_key=result["program_key"],
        major_electives=result["major_electives"],
        open_elective=result["open_elective"],
        free_electives=result["free_electives"],
        core_excluded=result["core_excluded"],
        unselected_electives=result["unselected_electives"],
        waived_courses=result["waived_courses"],
        prereq_failures=result["prereq_failures"],
        report_level=3,
    )
    deficiencies = audit_l3.compute_deficiencies(result)
    audit_l3.print_deficiency_report(result, deficiencies)


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
    table.add_column("Run ID",  style="dim", width=10)
    table.add_column("Program", width=7)
    table.add_column("Source",  width=8)
    table.add_column("CGPA",    width=6)
    table.add_column("Credits", width=12)
    table.add_column("Status",  width=10)
    table.add_column("Date",    width=20)

    _SOURCE_STYLE = {"web": "cyan", "cli": "yellow", "mcp": "magenta"}

    for r in runs:
        cgpa    = str(r["cgpa"])    if r["cgpa"]    is not None else "—"
        credits = (
            f"{r['credit_completed']}/{r['required_credits']}"
            if r["credit_completed"] is not None else "—"
        )
        src       = (r.get("source") or "web").lower()
        src_style = _SOURCE_STYLE.get(src, "white")
        table.add_row(
            r["run_id"][:8],
            r["program"],
            f"[{src_style}]{src.upper()}[/{src_style}]",
            cgpa,
            credits,
            r["status"],
            r["created_at"][:19].replace("T", " "),
        )

    rprint(table)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_result(result: dict, run_id: str, transcript_name: str = "") -> None:
    from rich.markup import escape as _esc

    program  = result.get("program", "")

    # ── Selected Electives box ─────────────────────────────────────────────────
    major_els = result.get("major_electives") or []
    open_el   = result.get("open_elective") or ""
    free_els  = result.get("free_electives") or []

    if major_els or open_el or free_els:
        rprint()
        el_rows: list[str | None] = [
            "SELECTED ELECTIVES  (included in credit tally)",
            None,
        ]
        for e in major_els:
            el_rows.append(f"  \u25b8 {e}   [Major Elective]")
        if open_el:
            elec_lbl = "Free Elective" if program == "MIC" else "Open Elective"
            el_rows.append(f"  \u25b8 {open_el}   [{elec_lbl}]")
        for e in free_els:
            el_rows.append(f"  \u25b8 {e}   [Free Elective]")
        rprint(_content_panel(el_rows))

    # ── Minor Programs box (CSE only) ─────────────────────────────────────────
    minors = result.get("minor_programs") or []
    if minors:
        rprint()
        min_rows: list[str | None] = ["MINOR PROGRAM(S) DETECTED"]
        for mp in minors:
            min_rows.append(None)
            done_str = "\u2713 COMPLETE" if mp.get("complete") else f"\u2717 INCOMPLETE \u2014 {mp.get('progress', '')}"
            min_rows.append(f"  {mp['name']} ({mp['total_credits']} credits)   \u2014   {done_str}")
            if mp.get("core_courses"):
                min_rows.append(f"  School Core (already required): {', '.join(mp['core_courses'])}")
            if mp.get("declared_courses"):
                min_rows.append(f"  Declared courses: {', '.join(mp['declared_courses'])}")
            cs = mp.get("choice_slot") or {}
            if cs.get("selected"):
                opts = " or ".join(cs.get("options") or [])
                min_rows.append(f"  Elective slot ({opts}): {cs['selected']} \u2713")
        rprint(_content_panel(min_rows))

    # ── CGPA & Credit Tally box ────────────────────────────────────────────────
    credit_passed    = float(result.get("credit_passed") or 0)
    credit_counted   = float(result.get("credit_counted") or 0)
    credit_completed = float(result.get("credit_completed") or 0)
    required_credits = result.get("required_credits")
    cgpa             = float(result.get("cgpa") or 0)
    standing         = result.get("academic_standing") or ""
    total_gp         = float(result.get("total_grade_points") or 0)

    credit_ok = credit_completed >= (required_credits or 0)
    cgpa_ok   = cgpa >= 2.0
    cr_flag   = "\u2713 MET" if credit_ok else "\u2717 NOT MET"
    cgpa_flag = "\u2713 MET (\u2265 2.0)" if cgpa_ok else "\u2717 PROBATION \u2014 below 2.0 minimum"

    rprint()
    tally_rows: list[str | None] = ["CGPA & CREDIT TALLY REPORT", None]
    if transcript_name:
        tally_rows.append(f"Transcript  :  {transcript_name}")
    tally_rows.append(f"Program     :  {program}")
    for note in (result.get("waiver_notes") or []):
        tally_rows.append(f"Waiver      :  {note}")
    tally_rows.extend(
        [
            None,
            f"CREDIT PASSED     :  {credit_passed:.1f}   (passing grades A\u2013D; counts toward graduation)",
            f"CREDIT COUNTED    :  {credit_counted:.1f}   (A\u2013F grades in curriculum; CGPA denominator)",
        ]
    )
    if required_credits is not None:
        tally_rows.append(
            f"CREDIT COMPLETED  :  {credit_completed:.1f} / {required_credits} required   [{cr_flag}]"
        )
    else:
        tally_rows.append(f"CREDIT COMPLETED  :  {credit_completed:.1f}")
    tally_rows.extend(
        [
            f"CGPA              :  {cgpa:.2f}   [{standing}]   [{cgpa_flag}]",
            f"Grade Points      :  {total_gp:.2f}  \u00f7  {credit_counted:.1f} Credit Counted",
        ]
    )
    rprint(_content_panel(tally_rows))

    # ── Course tables ─────────────────────────────────────────────────────────
    detail   = result.get("per_course_detail") or []
    counted  = sorted([r for r in detail if r.get("counted")],         key=lambda r: r["course"])
    excluded = sorted([r for r in detail if not r.get("counted") and r.get("reason")], key=lambda r: r["course"])

    def _tbl() -> Table:
        t = Table(
            box=box.SQUARE,
            show_header=True,
            header_style="",
            border_style=_BC,
            show_lines=False,
            padding=(0, 1),
        )
        t.add_column("Course",          width=14, no_wrap=True)
        t.add_column("Credits",         width=9,  justify="right", no_wrap=True)
        t.add_column("Grade",           width=6,  no_wrap=True)
        t.add_column("Status / Reason", no_wrap=False, min_width=30)
        return t

    if counted:
        rprint()
        rprint(f"[{_BC}]  Courses counted toward graduation:[/{_BC}]")
        t = _tbl()
        for r in counted:
            cr_s   = f"{r['credits']:.1f}" if r.get("credits") is not None else "\u2014"
            status = f"Counted  [{r['label']}]" if r.get("label") else "Counted"
            t.add_row(r["course"], cr_s, r.get("grade") or "\u2014", status)
        rprint(Padding(t, (0, 0, 0, 2)))

    if excluded:
        rprint()
        rprint(f"[{_BC}]  Courses not counted (0 credits):[/{_BC}]")
        t = _tbl()
        for r in excluded:
            t.add_row(r["course"], "\u2014", r.get("grade") or "\u2014", _esc(r.get("reason") or ""))
        rprint(Padding(t, (0, 0, 0, 2)))

    # ── Summary box ───────────────────────────────────────────────────────────
    standing_line = (
        "\u26a0  PROBATION \u2014 CGPA is below the 2.0 minimum required for graduation"
        if cgpa < 2.0 else standing
    )
    rprint()
    rprint(
        _content_panel(
            [
                f"Credit Passed                :  {credit_passed:.1f}   (passing grades A\u2013D; toward graduation)",
                f"Credit Counted               :  {credit_counted:.1f}   (A\u2013F grades; CGPA denominator \u2014 includes F where applicable)",
                f"Total Grade Points           :  {total_gp:.2f}",
                f"CGPA                         :  {cgpa:.2f}   ({standing})",
                f"Academic Standing            :  {standing_line}",
            ]
        )
    )

    # ── Deficiency Report box ─────────────────────────────────────────────────
    deficiency = result.get("deficiency") or {}
    eligible   = deficiency.get("eligible", False)
    status_str = "\u2713  ELIGIBLE FOR GRADUATION" if eligible else "\u2717  NOT ELIGIBLE FOR GRADUATION"
    wrap_w = min(96, max(48, shutil.get_terminal_size(fallback=(100, 24)).columns - 8))

    def_rows: list[str | None] = [
        "DEFICIENCY REPORT",
        None,
    ]
    if transcript_name:
        def_rows.append(f"Transcript  :  {transcript_name}")
    def_rows.extend([f"Program     :  {program}", None, f"Graduation Status  :  {status_str}", None])

    if eligible:
        def_rows.append("  All requirements satisfied. Student is cleared for graduation.")
    else:
        sf = float(deficiency.get("credit_shortfall") or 0)
        if sf > 0:
            def_rows.append(
                f"  \u25b8 Credit shortfall     :  {sf:.1f} credit(s) below the required total"
            )
        if deficiency.get("probation"):
            def_rows.append(
                "  \u25b8 Probation            :  CGPA is below the 2.0 minimum required for graduation"
            )
        for mm in (deficiency.get("missing_mandatory") or []):
            cat   = mm.get("category", "")
            items = mm.get("courses") or []
            label = f"  \u25b8 Missing [{cat}]"
            full  = f"{label}  :  {', '.join(items)}"
            if len(full) <= wrap_w:
                def_rows.append(full)
            else:
                def_rows.append(label)
                chunk = ""
                for item in items:
                    candidate = chunk + ("  " if chunk else "      ") + item
                    if len(candidate) <= wrap_w - 2:
                        chunk = candidate
                    else:
                        if chunk:
                            def_rows.append(chunk)
                        chunk = "      " + item
                if chunk:
                    def_rows.append(chunk)
        if deficiency.get("prereq_failures_list"):
            def_rows.append("  \u25b8 Prerequisite failures:")
            for pf in deficiency["prereq_failures_list"]:
                detail = pf.get("reason", "").removeprefix("prereq not met: ")
                def_rows.append(f"      {pf['course']}  \u2014  needs: {detail}")

    def_rows.extend([None, f"  {deficiency.get('retake_note', '')}"])
    rprint()
    rprint(_content_panel(def_rows))

    rprint()
    rprint(f"[dim]  Run ID: {run_id[:8]}[/dim]")


# ── TUI ───────────────────────────────────────────────────────────────────────

def _tui_do_login() -> None:
    """Device login flow inside the TUI."""
    rprint()
    try:
        token = device_login(_API_URL)
    except Exception as exc:
        rprint(f"\n[red]Login failed:[/red] {exc}")
        input("\n  Press Enter to continue…")
        return
    save_token(token)
    rprint("\n[green]✓ Logged in successfully.[/green]")
    rprint("  Credentials saved to ~/.config/nsu-audit/credentials.json")
    input("\n  Press Enter to continue…")


def _tui_do_logout() -> None:
    """Logout with confirmation inside the TUI."""
    import questionary
    rprint()
    if questionary.confirm("Log out?", default=False).ask():
        delete_token()
        rprint("[yellow]Logged out.[/yellow]")
    input("\n  Press Enter to continue…")


def _tui_do_run_audit(token: str) -> None:
    """Guided new audit inside the TUI."""
    import questionary
    rprint()

    path_str = questionary.path(
        "Path to transcript CSV / PDF / image:",
        validate=lambda p: True if Path(p).exists() else "File not found",
    ).ask()
    if path_str is None:
        return

    transcript = Path(path_str)
    program = questionary.select("Program:", choices=["CSE", "MIC"]).ask()
    if program is None:
        return

    rprint(f"\n[cyan]Loading choices[/cyan] ({program}) …")
    try:
        answers_dict = _collect_answers_interactive(_API_URL, token, transcript, program)
        rprint(f"\n[cyan]Running audit[/cyan] ({program}) …")
        resp = _api.api_post_multipart(
            _API_URL, "/api/audit/run", token,
            csv_path=transcript, program=program, answers=answers_dict, save=True,
        )
    except (SystemExit, typer.Exit):
        return
    except Exception as exc:
        rprint(f"\n[red]Audit failed:[/red] {exc}")
        input("\n  Press Enter to continue…")
        return

    _print_result(resp["result"], resp["run_id"], transcript_name=transcript.name)
    input("\n  Press Enter to return to menu…")


def _tui_do_history(token: str) -> None:
    """Show audit history inside the TUI."""
    rprint()
    try:
        data = _api.api_get(_API_URL, "/api/history/", token, limit=10, offset=0)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        input("\n  Press Enter to continue…")
        return

    runs = data["runs"]
    if not runs:
        rprint("[dim]No audit runs yet.[/dim]")
        input("\n  Press Enter to continue…")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Run ID",  style="dim", width=10)
    table.add_column("Program", width=7)
    table.add_column("Source",  width=8)
    table.add_column("CGPA",    width=6)
    table.add_column("Credits", width=12)
    table.add_column("Status",  width=10)
    table.add_column("Date",    width=20)

    _SOURCE_STYLE = {"web": "cyan", "cli": "yellow", "mcp": "magenta"}

    for r in runs:
        cgpa    = str(r["cgpa"]) if r["cgpa"] is not None else "—"
        credits = (
            f"{r['credit_completed']}/{r['required_credits']}"
            if r["credit_completed"] is not None else "—"
        )
        src       = (r.get("source") or "web").lower()
        src_style = _SOURCE_STYLE.get(src, "white")
        table.add_row(
            r["run_id"][:8], r["program"],
            f"[{src_style}]{src.upper()}[/{src_style}]",
            cgpa, credits, r["status"],
            r["created_at"][:19].replace("T", " "),
        )
    rprint(table)
    input("\n  Press Enter to return to menu…")


def _tui_do_admin_stats(token: str) -> None:
    """Show admin stats inside the TUI."""
    rprint()
    try:
        data = _api.api_get(_API_URL, "/api/admin/stats", token)
    except Exception as exc:
        rprint(f"[red]Error:[/red] {exc}")
        input("\n  Press Enter to continue…")
        return

    admin_rows: list[str | None] = ["ADMIN STATS", None]
    for k, v in data.items():
        if isinstance(v, dict):
            admin_rows.append(f"  {k}:")
            for dk, dv in v.items():
                admin_rows.append(f"      {dk}: {dv}")
        elif isinstance(v, list):
            admin_rows.append(f"  {k}:  ({len(v)} entries)")
            for _i, item in enumerate(v, 1):
                admin_rows.append(None)
                if isinstance(item, dict):
                    for ik, iv in item.items():
                        admin_rows.append(f"    {ik}: {iv}")
                else:
                    admin_rows.append(f"    {item}")
        else:
            admin_rows.append(f"  {k}: {v}")
    rprint(_content_panel(admin_rows))
    input("\n  Press Enter to return to menu…")


def _tui_do_run_local() -> None:
    """Run a local audit (no API, no login) inside the TUI."""
    import questionary
    rprint()

    _all_exts = {".csv"} | _LOCAL_OCR_EXTS

    def _validate_path(p: str) -> bool | str:
        if not Path(p).exists():
            return "File not found"
        if Path(p).suffix.lower() not in _all_exts:
            return f"Unsupported file type. Accepted: {', '.join(sorted(_all_exts))}"
        return True

    path_str = questionary.path(
        "Path to transcript (CSV / PDF / image):",
        validate=_validate_path,
    ).ask()
    if path_str is None:
        return

    transcript = Path(path_str)
    program = questionary.select("Program:", choices=["CSE", "MIC"]).ask()
    if program is None:
        return

    try:
        run_local(transcript=transcript, program=program, answers=None, no_interact=False)
    except (SystemExit, typer.Exit):
        pass

    input("\n  Press Enter to return to menu…")


def _tui() -> None:
    """Interactive TUI — invoked when `nsu-audit` is run with no sub-command."""
    try:
        import questionary
        from questionary import Separator
    except ImportError:
        rprint("[red]questionary is not installed.[/red]  Run:  pip install questionary")
        raise typer.Exit(1)

    while True:
        os.system("clear" if os.name != "nt" else "cls")

        # Refresh auth state on every loop iteration
        token = load_token()
        username: Optional[str] = None
        if token:
            try:
                data = _api.api_get(_API_URL, "/api/auth/me", token)
                username = data.get("display_name") or data.get("email")
            except Exception:
                token = None

        rprint()
        rprint(header_panel(username))
        rprint()

        if token and username:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    "Run New Audit",
                    "View History",
                    "Admin Stats",
                    Separator(),
                    "Log Out",
                    "Exit",
                ],
            ).ask()
        else:
            choice = questionary.select(
                "What would you like to do?",
                choices=[
                    "Log In",
                    "Run Local Audit",
                    Separator(),
                    "Exit",
                ],
            ).ask()

        if choice is None or choice == "Exit":
            break

        if choice == "Log In":
            _tui_do_login()
        elif choice == "Log Out":
            _tui_do_logout()
        elif choice == "Run New Audit":
            _tui_do_run_audit(token)
        elif choice == "View History":
            _tui_do_history(token)
        elif choice == "Admin Stats":
            _tui_do_admin_stats(token)
        elif choice == "Run Local Audit":
            _tui_do_run_local()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
