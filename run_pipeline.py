#!/usr/bin/env python3
"""
run_pipeline.py

End-to-end audit pipeline: converts a raw NSU transcript (PDF or image) into a
CSV and immediately runs it through the chosen audit level.

Usage
-----
    python run_pipeline.py Transcript.pdf CSE --level 3
    python run_pipeline.py Transcript.jpeg MIC --level 2 --no-interact
    python run_pipeline.py Transcript.pdf CSE --level 1 --output student.csv --debug

Positional arguments
--------------------
    transcript      Path to the transcript file (PDF, JPEG, PNG, TIFF, BMP)
    program_name    Program identifier: CSE  or  MIC

Optional arguments
------------------
    -l / --level        Audit level to run after CSV generation: 1, 2, or 3
                        (default: 3 — full deficiency report)
    -o / --output       Where to save the generated CSV
                        (default: same path as transcript, with .csv extension)
    --md                Path to the program knowledge Markdown file
                        (default: program.md in the same directory as this script)
    --no-interact       Non-interactive mode: auto-select best options.
                        Suitable for batch / AI-agent pipelines.
    --debug             Print OCR parsing details to stderr.
    --keep-csv          Keep the generated CSV after the audit finishes.
                        By default the CSV is kept; pass --no-keep-csv to delete it.
    --no-keep-csv       Delete the generated CSV after the audit finishes.

Exit codes
----------
    0   Success
    1   Error in transcript conversion or audit
"""

import argparse
import subprocess
import sys
from pathlib import Path

# ── import OCR/conversion functions from transcript_to_csv ───────────────────
try:
    from transcript_to_csv import _get_page_images, parse_page, _deduplicate, write_csv, IMAGE_EXTS
except ImportError as e:
    sys.exit(
        f"ERROR: Could not import transcript_to_csv — make sure it is in the same "
        f"directory and its dependencies are installed.\n  Detail: {e}"
    )

# ── audit-level → script mapping ─────────────────────────────────────────────
_AUDIT_SCRIPTS: dict[int, str] = {
    1: "audit_l1.py",
    2: "audit_l2.py",
    3: "audit_l3.py",
}

_LEVEL_LABELS: dict[int, str] = {
    1: "Level 1 — Credit Tally",
    2: "Level 2 — CGPA Engine",
    3: "Level 3 — Audit & Deficiency Reporter",
}


# ── step 1: transcript → CSV ──────────────────────────────────────────────────
def convert_transcript(src: Path, out: Path, debug: bool = False) -> Path:
    """Convert a PDF or image transcript to an audit-compatible CSV.

    Returns the path of the written CSV file.
    Exits with an error message if conversion produces zero rows.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  STEP 1 — Converting transcript to CSV", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Source : {src}", file=sys.stderr)
    print(f"  Output : {out}", file=sys.stderr)

    if not src.exists():
        sys.exit(f"ERROR: Transcript file not found: {src}")

    is_image = src.suffix.lower() in IMAGE_EXTS

    pages = _get_page_images(src)
    print(f"  Pages  : {len(pages)}", file=sys.stderr)

    all_rows: list[dict] = []
    for idx, page in enumerate(pages, 1):
        print(f"  OCR page {idx} …", file=sys.stderr)
        rows = parse_page(
            page,
            debug=debug,
            r_pass=is_image,
            inpaint_pass=is_image,
            camscanner_pass=is_image,
        )
        print(f"    → {len(rows)} course row(s) extracted", file=sys.stderr)
        all_rows.extend(rows)

    all_rows = _deduplicate(all_rows)

    if not all_rows:
        sys.exit(
            "ERROR: No course rows were extracted from the transcript.\n"
            "  • Check that the file is a valid NSU transcript.\n"
            "  • Run with --debug for detailed OCR output."
        )

    write_csv(all_rows, out)
    print(f"\n  Written {len(all_rows)} rows → {out}", file=sys.stderr)
    return out


# ── step 2: run audit level ───────────────────────────────────────────────────
def run_audit(
    level: int,
    csv_path: Path,
    program_name: str,
    program_md: Path,
    no_interact: bool,
) -> int:
    """Invoke the appropriate audit script as a subprocess.

    Returns the process exit code (0 = success).
    """
    script = Path(__file__).parent / _AUDIT_SCRIPTS[level]
    if not script.exists():
        sys.exit(f"ERROR: Audit script not found: {script}")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  STEP 2 — Running {_LEVEL_LABELS[level]}", file=sys.stderr)
    print(f"{'='*60}\n", file=sys.stderr)

    cmd = [
        sys.executable,
        str(script),
        str(csv_path),
        program_name,
        str(program_md),
    ]
    if no_interact:
        cmd.append("--no-interact")

    result = subprocess.run(cmd)
    return result.returncode


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Transcript-to-audit pipeline: convert a raw NSU transcript (PDF/image) "
            "to a CSV and immediately run it through the chosen audit level."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples\n"
            "--------\n"
            "  python run_pipeline.py Transcript.pdf cse l3\n"
            "  python run_pipeline.py Transcript.jpeg mic l2 --no-interact\n"
            "  python run_pipeline.py Transcript.pdf cse l1 --output out.csv\n"
        ),
    )

    ap.add_argument(
        "transcript",
        help="Path to the transcript file (PDF, JPEG, PNG, TIFF, BMP)",
    )
    ap.add_argument(
        "program_name",
        help="Program identifier: cse  or  mic  (case-insensitive)",
    )
    ap.add_argument(
        "level",
        help="Audit level to run: l1, l2, or l3",
    )
    ap.add_argument(
        "-o", "--output",
        help=(
            "Path for the generated CSV  "
            "[default: transcript filename with .csv extension]"
        ),
    )
    ap.add_argument(
        "--md",
        default=None,
        help=(
            "Path to the program knowledge Markdown file  "
            "[default: program.md next to this script]"
        ),
    )
    ap.add_argument(
        "--no-interact",
        action="store_true",
        help="Non-interactive: auto-select best options (batch / AI-agent mode)",
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="Print OCR parsing details to stderr",
    )

    keep_group = ap.add_mutually_exclusive_group()
    keep_group.add_argument(
        "--keep-csv",
        dest="keep_csv",
        action="store_true",
        default=True,
        help="Keep the generated CSV after the audit (default)",
    )
    keep_group.add_argument(
        "--no-keep-csv",
        dest="keep_csv",
        action="store_false",
        help="Delete the generated CSV after the audit finishes",
    )

    args = ap.parse_args()

    # ── resolve paths ──────────────────────────────────────────────────────────
    src = Path(args.transcript)
    out_csv = Path(args.output) if args.output else src.with_suffix(".csv")

    script_dir = Path(__file__).parent
    program_md = Path(args.md) if args.md else script_dir / "program.md"

    if not program_md.exists():
        sys.exit(
            f"ERROR: Program knowledge file not found: {program_md}\n"
            f"  Use --md to specify its location explicitly."
        )

    program_name = args.program_name.strip().upper()
    if program_name not in ("CSE", "MIC"):
        sys.exit(
            f"ERROR: Unsupported program '{args.program_name}'.\n"
            f"  Supported programs: cse, mic"
        )

    level_raw = args.level.strip().lower()
    level_map = {"l1": 1, "l2": 2, "l3": 3, "1": 1, "2": 2, "3": 3}
    if level_raw not in level_map:
        sys.exit(
            f"ERROR: Unrecognised level '{args.level}'.\n"
            f"  Supported levels: l1, l2, l3"
        )
    level = level_map[level_raw]

    # ── step 1: transcript → CSV ───────────────────────────────────────────────
    csv_path = convert_transcript(src, out_csv, debug=args.debug)

    # ── step 2: run chosen audit level ────────────────────────────────────────
    exit_code = run_audit(
        level=level,
        csv_path=csv_path,
        program_name=program_name,
        program_md=program_md,
        no_interact=args.no_interact,
    )

    # ── optional cleanup ───────────────────────────────────────────────────────
    if not args.keep_csv:
        try:
            csv_path.unlink()
            print(f"\n  Removed intermediate CSV: {csv_path}", file=sys.stderr)
        except OSError as e:
            print(f"\n  Warning: could not remove CSV: {e}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
