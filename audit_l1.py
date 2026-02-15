#!/usr/bin/env python3
"""
Level 1: Credit Tally Engine
Reads a student transcript CSV and reports total valid (earned) credits for graduation.
Usage: ./audit_l1.py transcript.csv program_name program_knowledge.md
"""

import argparse
import csv
import sys
from pathlib import Path

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


def reason_not_counted(attempts: list[dict]) -> str:
    """Return a specific reason why this course contributes 0 credits."""
    if not attempts:
        return "no attempts on transcript"
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


def compute_total_valid_credits(rows: list[dict]) -> tuple[float, dict[str, float], dict[str, list[dict]]]:
    """Group by course_code, compute valid credits per course; return (total, per_course, by_course)."""
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        code = r["course_code"]
        by_course.setdefault(code, []).append(r)

    per_course = {}
    for code, attempts in by_course.items():
        per_course[code] = valid_credits_for_course(attempts)

    return sum(per_course.values()), per_course, by_course


def print_report(
    transcript_path: Path,
    program_name: str,
    total: float,
    per_course: dict[str, float],
    by_course: dict[str, list[dict]],
) -> None:
    """Print one organized report: header, total, and full per-course breakdown."""
    width = 50
    print("=" * width)
    print("  LEVEL 1: CREDIT TALLY REPORT")
    print("=" * width)
    print(f"  Transcript:   {transcript_path.name}")
    print(f"  Program:      {program_name}")
    print("-" * width)
    print(f"  TOTAL VALID CREDITS:  {total:.1f}")
    print("-" * width)
    print("  Per-course breakdown (credits counted toward graduation):")
    print()
    counted = [(c, cr) for c, cr in sorted(per_course.items()) if cr > 0]
    excluded = [(c, cr) for c, cr in sorted(per_course.items()) if cr == 0]
    for code, cr in counted:
        print(f"    {code:<12}  {cr:>5.1f}  (counted)")
    if excluded:
        print()
        print("  Not counted (0 credits):")
        for code, _ in excluded:
            reason = reason_not_counted(by_course[code])
            print(f"    {code:<12}  —     {reason}")
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

    rows = load_transcript(args.transcript)
    total, per_course, by_course = compute_total_valid_credits(rows)
    print_report(args.transcript, args.program_name, total, per_course, by_course)

    return 0


if __name__ == "__main__":
    sys.exit(main())
