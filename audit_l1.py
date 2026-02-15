#!/usr/bin/env python3
"""
Level 1: Credit Tally Engine
Reads a student transcript CSV and reports total valid (earned) credits for graduation.
Usage: ./audit_l1.py transcript.csv program_name program_knowledge.md
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional, Set

# NSU passing grades, best to worst (for retake: count best passing attempt once)
GRADE_RANK = {
    "A": 10,
    "A-": 9,
    "B+": 8,
    "B": 7,
    "B-": 6,
    "C+": 5,
    "C": 4,
    "C-": 3,
    "D+": 2,
    "D": 1,
}
PASSING_GRADES = set(GRADE_RANK.keys())
NO_CREDIT_GRADES = {"F", "W", "I"}  # Failure, Withdrawal, Incomplete

# Required total credits per program (from program.md)
PROGRAM_REQUIRED_CREDITS = {"CSE": 130, "MIC": 120}


def get_required_credits(program_name: str) -> Optional[int]:
    """Return required credits for the program (CSE 130, MIC 120)."""
    key = (program_name or "").strip().upper()
    return PROGRAM_REQUIRED_CREDITS.get(key)


def normalize_course_code(raw: str) -> str:
    """Normalize course code for comparison: remove spaces, uppercase (e.g. ENG 102 -> ENG102)."""
    return re.sub(r"\s+", "", (raw or "").strip()).upper()


def _extract_course_codes_from_text(text: str) -> Set[str]:
    """Extract course codes from program markdown: table cells like 'ENG 102', 'CSE115', 'POL 101 / POL 104'."""
    codes: Set[str] = set()
    # Match table rows: | Course | ... or | **Course** | ...
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        first_cell = parts[1].strip()
        # Remove markdown bold
        first_cell = re.sub(r"\*\*", "", first_cell)
        # Skip header/separator rows
        if not first_cell or first_cell.upper() in ("COURSE", "CREDITS", "NOTES") or re.match(r"^[-]+$", first_cell):
            continue
        # Split by / or , to get alternatives (e.g. "POL 101 / POL 104" -> POL101, POL104)
        for segment in re.split(r"\s*/\s*|,|\s+and\s+", first_cell, flags=re.IGNORECASE):
            segment = segment.strip()
            # Match pattern: letters + digits + optional letters (e.g. ENG102, CSE115L, MIC101)
            for match in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*", segment):
                code = normalize_course_code(match.group(0))
                if len(code) >= 4 and code not in ("CHOOSE", "ONE", "LAB", "NONCREDIT"):
                    codes.add(code)
    return codes


def load_program_courses(program_path: Path) -> dict[str, Set[str]]:
    """Parse program.md and return {'CSE': set of course codes, 'MIC': set of course codes}."""
    result: dict[str, Set[str]] = {"CSE": set(), "MIC": set()}
    if not program_path.exists():
        return result
    try:
        text = program_path.read_text(encoding="utf-8")
    except OSError:
        return result
    # Split at Microbiology header: part before = CSE + policy, part after = MIC only
    if "Microbiology Undergraduate Program" in text:
        before_mic, _, after_mic = text.partition("# Microbiology Undergraduate Program")
        result["MIC"] = _extract_course_codes_from_text(after_mic)
        # CSE block: only the part starting at "# CSE Undergraduate Program"
        cse_start = before_mic.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            result["CSE"] = _extract_course_codes_from_text(before_mic[cse_start:])
    else:
        cse_start = text.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            result["CSE"] = _extract_course_codes_from_text(text[cse_start:])
    return result


def parse_credits(raw: str) -> float:
    """Parse credits; invalid or empty -> 0."""
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def normalize_grade(raw: str) -> str:
    """Normalize grade: strip and uppercase for comparison."""
    return (raw or "").strip().upper()


def is_passing(grade: str) -> bool:
    return grade in PASSING_GRADES


def is_no_credit(grade: str) -> bool:
    return grade in NO_CREDIT_GRADES or grade not in PASSING_GRADES


def load_transcript(path: Path) -> list[dict]:
    """Load transcript CSV; return list of dicts with normalized keys."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        keys = {k.strip().lower().replace(" ", "_"): k for k in reader.fieldnames}
        for row in reader:
            course_code = (row.get(keys.get("course_code", "Course_Code")) or "").strip()
            credits = parse_credits(row.get(keys.get("credits", "Credits")) or "0")
            grade = normalize_grade(row.get(keys.get("grade", "Grade")) or "")
            semester = (row.get(keys.get("semester", "Semester")) or "").strip()
            if not course_code and not grade and credits == 0:
                continue  # skip empty rows
            rows.append({
                "course_code": course_code or "UNKNOWN",
                "credits": credits,
                "grade": grade,
                "semester": semester,
            })
    return rows


def valid_credits_for_course(attempts: list[dict]) -> float:
    """
    For one course (all attempts), return credits that count toward graduation.
    - W/I: never count.
    - 0-credit rows: best attempt may have 0 credits (e.g. MAT116) -> 0.
    - Retakes: only best passing attempt counts once; if no passing, 0.
    """
    if not attempts:
        return 0.0

    passing = [a for a in attempts if is_passing(a["grade"])]
    if not passing:
        return 0.0

    # Best passing attempt by grade rank; use that row's credits (0-credit course => 0)
    best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
    return best["credits"]


def get_display_grade(attempts: list[dict]) -> str:
    """Return the grade to show for this course: best passing if any, else latest attempt."""
    if not attempts:
        return "—"
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        return best["grade"]
    # Show most recent attempt's grade (transcript order = last row)
    return attempts[-1]["grade"] if attempts[-1]["grade"] else "—"


def reason_not_counted(
    attempts: list[dict],
    course_code: str = "",
    program_name: str = "",
    allowed_codes: Optional[Set[str]] = None,
) -> str:
    """Return a specific reason why this course contributes 0 credits."""
    if not attempts:
        return "no attempts on transcript"
    # If program filter is on and this course is not in the program curriculum, say so first
    if allowed_codes is not None and program_name and course_code:
        normalized = normalize_course_code(course_code)
        if normalized not in allowed_codes:
            return f"not in {program_name} curriculum"
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        if best["credits"] == 0:
            return "0-credit course (credits not applied toward graduation)"
        return "error: has passing attempt"  # should not appear
    grades = set(a["grade"] for a in attempts)
    parts = []
    if "F" in grades:
        parts.append("failure (F)")
    if "W" in grades:
        parts.append("withdrawal (W)")
    if "I" in grades:
        parts.append("incomplete (I)")
    other = grades - PASSING_GRADES - NO_CREDIT_GRADES
    if other:
        parts.append("non-passing grade")
    reason = " and ".join(parts) + "; no passing retake"
    return reason


def compute_total_valid_credits(
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
) -> tuple[float, dict[str, float], dict[str, list[dict]]]:
    """Group by course_code, compute valid credits per course; only count courses in allowed_codes if set."""
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        code = r["course_code"]
        by_course.setdefault(code, []).append(r)

    per_course = {}
    for code, attempts in by_course.items():
        raw_credits = valid_credits_for_course(attempts)
        if allowed_codes is not None:
            normalized = normalize_course_code(code)
            if normalized not in allowed_codes:
                per_course[code] = 0.0
            else:
                per_course[code] = raw_credits
        else:
            per_course[code] = raw_credits

    return sum(per_course.values()), per_course, by_course


def print_report(
    transcript_path: Path,
    program_name: str,
    total: float,
    per_course: dict[str, float],
    by_course: dict[str, list[dict]],
    required_credits: Optional[int] = None,
    allowed_codes: Optional[Set[str]] = None,
) -> None:
    """Print one organized report: header, total, and full per-course breakdown."""
    width = 50
    print("=" * width)
    print("  LEVEL 1: CREDIT TALLY REPORT")
    print("=" * width)
    print(f"  Transcript:   {transcript_path.name}")
    print(f"  Program:      {program_name}")
    print("-" * width)
    if required_credits is not None:
        print(f"  TOTAL VALID CREDITS:  {total:.1f} / {required_credits} (required for {program_name})")
    else:
        print(f"  TOTAL VALID CREDITS:  {total:.1f}")
    print("-" * width)
    counted = [(c, cr) for c, cr in sorted(per_course.items()) if cr > 0]
    excluded = [(c, cr) for c, cr in sorted(per_course.items()) if cr == 0]

    col_code, col_cr, col_grade, col_status = 14, 10, 8, 40
    sep = "  +" + "-" * (col_code + 2) + "+" + "-" * (col_cr + 2) + "+" + "-" * (col_grade + 2) + "+" + "-" * (col_status + 2) + "+"
    header = "  | {:^{}} | {:^{}} | {:^{}} | {:^{}} |".format("Course", col_code, "Credits", col_cr, "Grade", col_grade, "Status", col_status)

    print("  Counted (credits toward graduation):")
    print()
    print(sep)
    print(header)
    print(sep)
    for code, cr in counted:
        grade = get_display_grade(by_course[code])
        print("  | {:<{}} | {:>{}.1f} | {:<{}} | {:<{}} |".format(code, col_code, cr, col_cr, grade, col_grade, "Counted", col_status))
    print(sep)
    print()

    if excluded:
        print("  Not counted (0 credits):")
        print()
        print(sep)
        print(header)
        print(sep)
        for code, _ in excluded:
            grade = get_display_grade(by_course[code])
            reason = reason_not_counted(
                by_course[code],
                course_code=code,
                program_name=program_name,
                allowed_codes=allowed_codes,
            )
            status = reason[:col_status] if len(reason) <= col_status else reason[: col_status - 3] + "..."
            print("  | {:<{}} | {:^{}} | {:<{}} | {:<{}} |".format(code, col_code, "—", col_cr, grade, col_grade, status, col_status))
        print(sep)
    print()
    print("=" * width)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Level 1: Credit Tally Engine — total valid credits from transcript."
    )
    parser.add_argument("transcript", type=Path, help="Path to transcript CSV")
    parser.add_argument("program_name", type=str, help="Program name (unused in L1)")
    parser.add_argument("program_knowledge", type=Path, help="Path to program knowledge file (unused in L1)")
    args = parser.parse_args()

    if not args.transcript.exists():
        print(f"Error: transcript file not found: {args.transcript}", file=sys.stderr)
        return 1

    program_courses = load_program_courses(args.program_knowledge)
    program_key = (args.program_name or "").strip().upper()
    allowed_codes = program_courses.get(program_key) if program_key in ("CSE", "MIC") else None

    rows = load_transcript(args.transcript)
    total, per_course, by_course = compute_total_valid_credits(rows, allowed_codes=allowed_codes)
    required = get_required_credits(args.program_name)
    print_report(
        args.transcript,
        args.program_name,
        total,
        per_course,
        by_course,
        required,
        allowed_codes=allowed_codes,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
