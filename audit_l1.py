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

# CSE Major Elective Trails (from program.md)
CSE_TRAILS: dict[str, list[str]] = {
    "Algorithms and Computation": ["CSE257", "CSE417", "CSE326", "CSE426", "CSE273", "CSE473"],
    "Software Engineering":       ["CSE411"],
    "Networks":                   ["CSE422", "CSE562", "CSE338", "CSE438", "CSE482", "CSE485", "CSE486"],
    "Computer Architecture and VLSI": ["CSE435", "CSE413", "CSE414"],
    "Artificial Intelligence":    ["CSE440", "CSE445", "CSE465", "CSE467", "CSE419", "CSE598"],
}

# MIC Elective courses (from program.md)
MIC_ELECTIVES: list[str] = ["MIC201", "MIC318", "MIC404", "MIC311", "MIC309", "MIC416", "MIC417", "MIC317", "MIC418"]

# MIC required course categories — used to flag courses already serving a requirement
MIC_REQUIRED_CATEGORIES: dict[str, set[str]] = {
    "University Core": {
        "ENG102", "ENG103", "ENG105", "ENG111", "BEN205",
        "HIS101", "HIS103", "PHI101",
        "POL101", "POL104", "ECO101", "ECO104", "SOC101", "ANT101",
        "MAT107", "MAT116", "BUS172",
        "BIO103", "BIO103L", "PHY107", "PHY107L",
    },
    "SHLS Core": {
        "CHE101", "CHE101L", "CHE201", "CHE202", "CHE202L",
        "BIO201", "MIC110", "BIO103L", "BIO201L", "MIC101L",
        "BIO202", "BIO202L", "MIC101", "BBT230", "BUS172", "MIC203",
    },
    "Major Core": {
        "MIC202", "MIC206", "MIC307", "MIC314", "MIC201",
        "MIC315", "MIC315L", "MIC316", "MIC316L", "MIC317", "MIC317L",
        "MIC401", "MIC412", "MIC416", "MIC413", "MIC413L",
        "MIC414", "MIC414L", "MIC415", "MIC415L", "MIC498",
    },  # MIC309 removed — it is a prereq for MIC203, not a standalone requirement
}

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

# Non-credit labs: included in theory course grade, never shown separately in reports
# Non-credit labs (CSE-only): grade folds into theory course; 0 credits regardless of transcript.
# BIO103L is a genuine 1-credit lab for MIC — not included here.
CSE_NCL_LABS = {"CSE225L", "CSE231L", "CSE311L", "CSE331L", "CSE332L", "BIO103L"}

def get_ncl_labs(program_key=None) -> set:
    """Return zero/non-credit lab codes for the given program."""
    if program_key == "CSE":
        return CSE_NCL_LABS  # BIO103L is 0-credit in CSE School Core
    return CSE_NCL_LABS - {"BIO103L"}  # MIC: BIO103L is a real 1-credit lab

# Required total credits per program (from program.md)
PROGRAM_REQUIRED_CREDITS = {"CSE": 130, "MIC": 120}

# MIC SHLS Core alias pairs: these course codes mean the SAME thing.
# Taking either one satisfies that requirement slot — only one should be counted.
MIC_ALIAS_PAIRS: list[tuple[str, str]] = [
    ("BIO201",  "MIC110"),   # Cell Biology / Intro Microbiology theory
    ("BIO201L", "MIC101L"),  # Cell Biology Lab / Intro Microbiology Lab
    ("BIO202",  "MIC101"),   # Molecular Biology theory equivalent
    ("BIO202L", "MIC101L"),  # Molecular Biology Lab (MIC101L appears for both lab slots)
]

# MIC University Core choice groups — student may have taken more than one;
# admin must select which single course (or course pair for Science) counts.
MIC_HUMANITIES_CHOICES: list[str] = ["HIS101", "HIS103", "PHI101"]
MIC_SOCIAL_CHOICES: list[str]     = ["POL101", "POL104", "ECO101", "ECO104", "SOC101", "ANT101"]
# Science is a paired choice: theory + lab together
MIC_SCIENCE_CHOICES: list[tuple[str, str]] = [
    ("BIO103", "BIO103L"),
    ("PHY107", "PHY107L"),
]


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
        # Comma separates course from prerequisite — only the part BEFORE the first comma
        # is the actual required course. Slash (/) still denotes alternatives (e.g. POL101 / POL104).
        course_part = first_cell.split(",")[0].strip()
        for segment in re.split(r"\s*/\s*|\s+and\s+", course_part, flags=re.IGNORECASE):
            segment = segment.strip()
            # Match pattern: letters + digits + optional letters (e.g. ENG102, CSE115L, MIC101)
            for match in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*", segment):
                code = normalize_course_code(match.group(0))
                if len(code) >= 4 and code not in ("CHOOSE", "ONE", "LAB", "NONCREDIT"):
                    codes.add(code)
    return codes


def _extract_course_credits_from_text(text: str) -> dict[str, float]:
    """Extract course -> credits from program markdown tables (for program-specific overrides, e.g. MAT116)."""
    result: dict[str, float] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        first_cell = re.sub(r"\*\*", "", parts[1].strip())
        # Credits are in second column (index 2) for 3-col tables, or same for 2-col
        cred_cell = parts[2].strip() if len(parts) > 2 else "0"
        if not first_cell or first_cell.upper() in ("COURSE", "CREDITS", "NOTES") or re.match(r"^[-]+$", first_cell):
            continue
        # Explicitly handle "Non-Credit" cells — these are 0-credit courses by definition
        if re.match(r"non-?credit", cred_cell, flags=re.IGNORECASE):
            cred_values = [0.0]
        else:
            # Handle "3 + 1" style cells (theory + lab split) — assign in order to each code
            cred_values = [float(m) for m in re.findall(r"\d+\.?\d*", cred_cell)] or [0.0]

        # Comma separates course from prerequisite — only the part BEFORE the first comma is the course.
        course_part = first_cell.split(",")[0].strip()
        codes_in_row: list[str] = []
        for segment in re.split(r"\s*/\s*|\s+and\s+", course_part, flags=re.IGNORECASE):
            for match in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*", segment.strip()):
                code = normalize_course_code(match.group(0))
                if len(code) >= 4 and code not in ("CHOOSE", "ONE", "LAB", "NONCREDIT"):
                    codes_in_row.append(code)

        for i, code in enumerate(codes_in_row):
            result[code] = cred_values[i] if i < len(cred_values) else cred_values[-1]
    return result


def load_program_courses(program_path: Path) -> tuple[dict[str, Set[str]], dict[str, dict[str, float]]]:
    """Parse program.md; return (course codes per program, course credits per program for overrides)."""
    codes: dict[str, Set[str]] = {"CSE": set(), "MIC": set()}
    credits: dict[str, dict[str, float]] = {"CSE": {}, "MIC": {}}
    if not program_path.exists():
        return codes, credits
    try:
        text = program_path.read_text(encoding="utf-8")
    except OSError:
        return codes, credits
    if "Microbiology Undergraduate Program" in text:
        before_mic, _, after_mic = text.partition("# Microbiology Undergraduate Program")
        codes["MIC"] = _extract_course_codes_from_text(after_mic)
        credits["MIC"] = _extract_course_credits_from_text(after_mic)
        cse_start = before_mic.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            cse_block = before_mic[cse_start:]
            codes["CSE"] = _extract_course_codes_from_text(cse_block)
            credits["CSE"] = _extract_course_credits_from_text(cse_block)
    else:
        cse_start = text.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            cse_block = text[cse_start:]
            codes["CSE"] = _extract_course_codes_from_text(cse_block)
            credits["CSE"] = _extract_course_credits_from_text(cse_block)
    return codes, credits


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
    - 0-credit rows: best attempt may have 0 credits (e.g. MAT116 in CSE) -> 0.
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


def has_passing_attempt(attempts: list[dict]) -> bool:
    """True if the student has at least one passing grade in this course."""
    return any(is_passing(a["grade"]) for a in attempts)


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
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
) -> str:
    """Return a specific reason why this course contributes 0 credits."""
    if not attempts:
        return "no attempts on transcript"
    normalized = normalize_course_code(course_code) if course_code else ""
    if allowed_codes is not None and program_name and course_code:
        if normalized not in allowed_codes:
            return f"not in {program_name} curriculum"
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        # Check effective credit: program override takes priority over transcript credits
        program_defined_credit = (
            program_credits[program_key].get(normalized)
            if program_credits and program_key and normalized in program_credits.get(program_key, {})
            else None
        )
        effective_credit = program_defined_credit if program_defined_credit is not None else best["credits"]
        if effective_credit == 0:
            if program_defined_credit == 0:
                # Distinguish between 0-credit courses (MAT116) and non-credit labs (CSE225L)
                label = "non-credit lab" if normalized.endswith("L") else "0-credit course"
                return f"{label} (credits not applied toward graduation)"
            else:
                return "transcript shows 0 credits (check transcript data)"
        return "error: has passing attempt but counted 0 (report bug)"  # should not appear
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
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
) -> tuple[float, dict[str, float], dict[str, list[dict]]]:
    """Group by course_code, compute valid credits per course; apply program-specific credit overrides (e.g. MAT116)."""
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        code = r["course_code"]
        by_course.setdefault(code, []).append(r)

    per_course = {}
    for code, attempts in by_course.items():
        normalized = normalize_course_code(code)
        # Non-credit labs are never counted regardless of program credit definition
        if normalized in get_ncl_labs(program_key):
            per_course[code] = 0.0
            continue
        raw_credits = valid_credits_for_course(attempts)
        if allowed_codes is not None:
            if normalized not in allowed_codes:
                per_course[code] = 0.0
            else:
                # Program-specific credit override (e.g. MAT116: 0 for CSE, 3 for MIC)
                if program_credits and program_key and normalized in program_credits.get(program_key, {}):
                    override = program_credits[program_key][normalized]
                    if has_passing_attempt(attempts):
                        per_course[code] = override
                    else:
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
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
    major_electives: Optional[list[str]] = None,
    open_elective: str = "",
    free_electives: Optional[list[str]] = None,
) -> None:
    """Print one organized report: header, total, and full per-course breakdown."""
    major_set = set(normalize_course_code(c) for c in (major_electives or []))
    free_set  = set(normalize_course_code(c) for c in (free_electives or []))
    open_code = normalize_course_code(open_elective) if open_elective else ""
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
    _ncl = get_ncl_labs(program_key)
    counted = [(c, cr) for c, cr in sorted(per_course.items()) if cr > 0 and normalize_course_code(c) not in _ncl]
    excluded = [(c, cr) for c, cr in sorted(per_course.items()) if cr == 0 and normalize_course_code(c) not in _ncl]

    col_code, col_cr, col_grade, col_status = 14, 10, 8, 55
    sep = "  +" + "-" * (col_code + 2) + "+" + "-" * (col_cr + 2) + "+" + "-" * (col_grade + 2) + "+" + "-" * (col_status + 2) + "+"
    header = "  | {:^{}} | {:^{}} | {:^{}} | {:^{}} |".format("Course", col_code, "Credits", col_cr, "Grade", col_grade, "Status", col_status)

    print("  Counted (credits toward graduation):")
    print()
    print(sep)
    print(header)
    print(sep)
    for code, cr in counted:
        grade = get_display_grade(by_course[code])
        normalized = normalize_course_code(code)
        if normalized == open_code:
            status = "Counted [Free Elective]" if program_key == "MIC" else "Counted [Open Elective]"
        elif normalized in free_set:
            status = "Counted [Free Elective]"
        elif normalized in major_set:
            status = "Counted [Major Elective]"
        else:
            status = "Counted"
        print("  | {:<{}} | {:>{}.1f} | {:<{}} | {:<{}} |".format(code, col_code, cr, col_cr, grade, col_grade, status, col_status))
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
                program_credits=program_credits,
                program_key=program_key,
            )
            status = reason[:col_status] if len(reason) <= col_status else reason[: col_status - 3] + "..."
            print("  | {:<{}} | {:^{}} | {:<{}} | {:<{}} |".format(code, col_code, "—", col_cr, grade, col_grade, status, col_status))
        print(sep)
    print()
    print("=" * width)


def _mic_course_category(code: str) -> Optional[str]:
    """Return the MIC required category name for a course code, or None if not required."""
    normalized = normalize_course_code(code)
    for category, codes in MIC_REQUIRED_CATEGORIES.items():
        if normalized in codes:
            return category
    return None


def _prompt_pick(prompt: str, options: list[str], display: Optional[list[str]] = None) -> str:
    """Show a numbered menu of options and return the chosen one. Re-prompts on invalid input."""
    labels = display if display and len(display) == len(options) else options
    while True:
        if prompt:
            print(prompt)
        for i, label in enumerate(labels, 1):
            print(f"  {i}. {label}")
        raw = input("  Enter number: ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        print("  Invalid input, please try again.\n")


def _course_display(code: str, rows: list[dict]) -> str:
    """Return a display string for a course: 'CSE440  (3 cr, A-)'."""
    attempts = [r for r in rows if normalize_course_code(r["course_code"]) == normalize_course_code(code)]
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        cr = best["credits"]
        cr_str = str(int(cr)) if cr == int(cr) else str(cr)
        return f"{code:<10}  ({cr_str} cr, {best['grade']})"
    return code


def _get_taken_courses(rows: list[dict]) -> list[str]:
    """Return unique course codes from the transcript that have at least one passing grade."""
    seen: dict[str, list[dict]] = {}
    for r in rows:
        seen.setdefault(r["course_code"], []).append(r)
    return [code for code, attempts in seen.items() if has_passing_attempt(attempts)]


def select_electives_cse(rows: list[dict], allowed_codes: Optional[Set[str]] = None) -> tuple[list[str], str]:
    """
    CSE elective selection driven by transcript.
    Returns (major_electives, open_elective).
    major_electives: up to 3 courses (2 from primary trail, 1 from secondary).
    open_elective: 1 course from trail courses or outside curriculum.
    """
    taken = set(_get_taken_courses(rows))

    # Build trail -> taken courses mapping
    trail_taken: dict[str, list[str]] = {}
    for trail_name, codes in CSE_TRAILS.items():
        matched = [c for c in codes if c in taken]
        if matched:
            trail_taken[trail_name] = matched

    print("\n" + "=" * 50)
    print("  CSE MAJOR ELECTIVE SELECTION")
    print("  Showing courses from your transcript only.")
    print("  Rule: 2 from one trail + 1 from another + 1 open elective")
    print("=" * 50)

    # --- Overview: show all available elective courses before prompting ---
    print("\n  Available elective courses from your transcript:\n")
    for trail_name, codes in trail_taken.items():
        print(f"  [{trail_name}]")
        for c in codes:
            print(f"    {_course_display(c, rows)}")
    # Open elective pool preview — trail courses + courses outside CSE curriculum
    all_trail_codes = {c for trail in CSE_TRAILS.values() for c in trail}
    open_preview = sorted([
        c for c in taken
        if c in all_trail_codes or c not in (allowed_codes or set())
    ])
    if open_preview:
        print(f"\n  [Open Elective candidates]  (trail courses + outside curriculum)")
        for c in open_preview:
            print(f"    {_course_display(c, rows)}")
    print()

    major_electives: list[str] = []

    # --- Primary trail: 2 courses ---
    eligible_primary = [t for t, c in trail_taken.items() if len(c) >= 2]
    if not eligible_primary:
        eligible_primary = list(trail_taken.keys())

    if not eligible_primary:
        print("  No elective courses found in transcript for CSE trails. Skipping major elective selection.")
        return major_electives, "", []

    primary_name = _prompt_pick("\nSelect your PRIMARY trail (need 2 courses from here):", eligible_primary)
    primary_pool = trail_taken[primary_name]

    print(f"\nSelect course 1 of 2 from '{primary_name}':")
    c1 = _prompt_pick("", primary_pool, display=[_course_display(c, rows) for c in primary_pool])
    major_electives.append(c1)

    remaining_primary = [c for c in primary_pool if c != c1]
    if remaining_primary:
        print(f"\nSelect course 2 of 2 from '{primary_name}':")
        c2 = _prompt_pick("", remaining_primary, display=[_course_display(c, rows) for c in remaining_primary])
        major_electives.append(c2)
    else:
        print(f"  Only one course available in '{primary_name}' from your transcript — counting {c1} only.")

    # --- Secondary trail: 1 course ---
    secondary_options = [t for t in trail_taken if t != primary_name]
    if secondary_options:
        secondary_name = _prompt_pick("\nSelect your SECONDARY trail (1 course from here):", secondary_options)
        secondary_pool = trail_taken[secondary_name]
        print(f"\nSelect 1 course from '{secondary_name}':")
        c3 = _prompt_pick("", secondary_pool, display=[_course_display(c, rows) for c in secondary_pool])
        major_electives.append(c3)
    else:
        print("  No secondary trail courses found in transcript — skipping.")

    # --- Open elective: remaining trail courses (not selected) + courses outside CSE curriculum ---
    open_pool = sorted([
        c for c in taken
        if c not in set(major_electives)
        and (c in all_trail_codes or c not in (allowed_codes or set()))
    ])
    open_elective = ""
    if open_pool:
        print("\nSelect your OPEN ELECTIVE (outside CSE curriculum + unselected major electives):")
        open_elective = _prompt_pick("", open_pool, display=[_course_display(c, rows) for c in open_pool])
    else:
        print("  No outside-curriculum courses found in transcript for open elective.")

    return major_electives, open_elective, []


def resolve_mic_aliases(rows: list[dict]) -> dict[str, str]:
    """
    For each MIC alias pair, if the transcript contains BOTH codes, return a mapping
    of the code to EXCLUDE -> the canonical code to KEEP (whichever was passed first /
    has the better grade).  If only one of the pair is present, no exclusion needed.

    Returns: dict of  excluded_code -> kept_code  (may be empty).
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    exclusions: dict[str, str] = {}
    for code_a, code_b in MIC_ALIAS_PAIRS:
        a, b = normalize_course_code(code_a), normalize_course_code(code_b)
        has_a = a in by_course and has_passing_attempt(by_course[a])
        has_b = b in by_course and has_passing_attempt(by_course[b])
        if has_a and has_b:
            # Both passed — keep the one with the better grade; exclude the other
            grade_a = GRADE_RANK.get(get_display_grade(by_course[a]), 0)
            grade_b = GRADE_RANK.get(get_display_grade(by_course[b]), 0)
            if grade_b > grade_a:
                exclusions[a] = b  # exclude A, keep B
            else:
                exclusions[b] = a  # exclude B, keep A (default on tie)
    return exclusions


def select_mic_core_choices(rows: list[dict]) -> set[str]:
    """
    For MIC University Core choice slots (Humanities / Social Sciences / Science):
    if the student's transcript has more than one passing course from a group,
    prompt the admin to pick which one counts.

    Returns a set of course codes to EXCLUDE from allowed_codes (i.e. the unchosen ones).
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    def passed_from(group: list[str]) -> list[str]:
        return [c for c in group if c in by_course and has_passing_attempt(by_course[c])]

    excluded: set[str] = set()

    print("\n" + "=" * 50)
    print("  MIC UNIVERSITY CORE — REQUIRED CHOICE SLOTS")
    print("  Only ONE course per group counts toward credits.")
    print("=" * 50)

    # --- Humanities (pick 1 of HIS101 / HIS103 / PHI101) ---
    hum_passed = passed_from(MIC_HUMANITIES_CHOICES)
    if len(hum_passed) > 1:
        print("\n  HUMANITIES — student passed multiple courses (pick one to count):")
        chosen = _prompt_pick("", hum_passed, display=[_course_display(c, rows) for c in hum_passed])
        excluded.update(c for c in hum_passed if c != chosen)
        print(f"  ✓ Humanities slot: {chosen} counted.")
    elif len(hum_passed) == 1:
        print(f"\n  Humanities: {hum_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Humanities: no passing course found.")

    # --- Social Sciences (pick 1 of POL/ECO/SOC/ANT options) ---
    soc_passed = passed_from(MIC_SOCIAL_CHOICES)
    if len(soc_passed) > 1:
        print("\n  SOCIAL SCIENCES — student passed multiple courses (pick one to count):")
        chosen = _prompt_pick("", soc_passed, display=[_course_display(c, rows) for c in soc_passed])
        excluded.update(c for c in soc_passed if c != chosen)
        print(f"  ✓ Social Sciences slot: {chosen} counted.")
    elif len(soc_passed) == 1:
        print(f"\n  Social Sciences: {soc_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Social Sciences: no passing course found.")

    # --- Science — pick one PAIR (theory + lab) ---
    # Find which pairs the student has passed (theory must be passed at minimum)
    passed_pairs = []
    for theory, lab in MIC_SCIENCE_CHOICES:
        if theory in by_course and has_passing_attempt(by_course[theory]):
            passed_pairs.append((theory, lab))

    if len(passed_pairs) > 1:
        print("\n  SCIENCE — student passed courses from multiple pairs (pick one pair to count):")
        pair_labels = [
            f"{t} + {l}  ({_course_display(t, rows).split('(')[1]}" if "(" in _course_display(t, rows)
            else f"{t} + {l}"
            for t, l in passed_pairs
        ]
        pair_options = [f"{t}+{l}" for t, l in passed_pairs]
        chosen_str = _prompt_pick("", pair_options, display=[
            f"{t}  +  {l}  (theory: {_course_display(t, rows).split('(')[-1].rstrip(')')})"
            for t, l in passed_pairs
        ])
        chosen_theory, chosen_lab = chosen_str.split("+")
        for theory, lab in passed_pairs:
            if theory != chosen_theory:
                excluded.add(theory)
                excluded.add(lab)
        print(f"  ✓ Science slot: {chosen_theory} + {chosen_lab} counted.")
    elif len(passed_pairs) == 1:
        t, l = passed_pairs[0]
        print(f"\n  Science: {t} + {l} — only option, auto-selected.")
    else:
        print("\n  Science: no passing theory course found.")

    print()
    return excluded


def select_electives_mic(rows: list[dict]) -> tuple[list[str], str]:
    """
    MIC elective selection driven by transcript.
    Returns (major_electives, open_elective) where major_electives has up to 3 courses.
    Free electives are treated as open electives (first one shown as open, rest as major).
    """
    taken = set(_get_taken_courses(rows))

    print("\n" + "=" * 50)
    print("  MIC ELECTIVE SELECTION")
    print("  Showing courses from your transcript only.")
    print("  Rule: 3 major electives + 3 free electives")
    print("=" * 50)

    # --- Overview: show only truly free elective candidates ---
    # Exclude courses that are already required Major Core — they cannot double-count as electives.
    _major_core_required = MIC_REQUIRED_CATEGORIES.get("Major Core", set())
    major_pool = [c for c in MIC_ELECTIVES if c in taken and c not in _major_core_required]
    all_non_major = sorted(c for c in taken if c not in set(major_pool))
    free_available = [c for c in all_non_major if _mic_course_category(c) is None]

    print("\n  Available major elective courses from your transcript:\n")
    if major_pool:
        for c in major_pool:
            print(f"    {_course_display(c, rows)}")
    else:
        print("    (none)")

    print(f"\n  [Free Elective candidates]")
    print(f"  (outside-curriculum courses + unselected major electives)\n")
    all_free_preview = free_available + major_pool
    if all_free_preview:
        for c in all_free_preview:
            print(f"    {_course_display(c, rows)}")
    else:
        print("    (none — all passed courses are already serving required categories)")
    print()

    major_electives: list[str] = []

    major_pool = [c for c in MIC_ELECTIVES if c in taken and c not in _major_core_required]
    remaining = list(major_pool)
    if not remaining:
        print("  No MIC elective courses found in transcript.")
    else:
        for i in range(1, 4):
            if not remaining:
                print(f"  No more elective courses available (selected {i - 1} of 3).")
                break
            course = _prompt_pick(f"\nSelect major elective {i} of 3:", remaining,
                                  display=[_course_display(c, rows) for c in remaining])
            major_electives.append(course)
            remaining = [c for c in remaining if c != course]

    # Remaining MIC electives not chosen as major electives are also free elective candidates
    remaining_major_pool = [c for c in major_pool if c not in set(major_electives)]
    free_pool = free_available + [c for c in remaining_major_pool if c not in free_available]
    free_pool = [c for c in free_pool if c not in set(major_electives)]
    open_elective = ""
    free_extras: list[str] = []
    if not free_pool:
        print("\n  No free elective courses available in transcript.")
    else:
        print(f"\nSelect 3 FREE ELECTIVES:\n")
        for i in range(1, 4):
            if not free_pool:
                print(f"  No more courses available (selected {i - 1} of 3).")
                break
            course = _prompt_pick(f"Free elective {i} of 3:", free_pool,
                                  display=[_course_display(c, rows) for c in free_pool])
            if i == 1:
                open_elective = course
            else:
                free_extras.append(course)
            free_pool = [c for c in free_pool if c != course]

    return major_electives, open_elective, free_extras


def select_electives(program_key: str, rows: list[dict], allowed_codes: Optional[Set[str]] = None) -> tuple[list[str], str]:
    """Dispatch elective selection by program. Returns (major_electives, open_elective)."""
    if program_key == "CSE":
        return select_electives_cse(rows, allowed_codes=allowed_codes)
    elif program_key == "MIC":
        return select_electives_mic(rows)
    return [], "", []


def print_elective_summary(major_electives: list[str], open_elective: str, program_key: str, free_electives: Optional[list[str]] = None) -> None:
    """Print a confirmation of selected electives before running the audit."""
    print("\n" + "-" * 50)
    print("  SELECTED ELECTIVES (will be included in tally)")
    print("-" * 50)
    for code in major_electives:
        print(f"  • {code}  [Major Elective]")
    for code in (free_electives or []):
        print(f"  • {code}  [Free Elective]")
    if open_elective:
        label = "Free Elective" if program_key == "MIC" else "Open Elective"
        print(f"  • {open_elective}  [{label}]")
    print("-" * 50 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Level 1: Credit Tally Engine — total valid credits from transcript."
    )
    parser.add_argument("transcript", type=Path, help="Path to transcript CSV")
    parser.add_argument("program_name", type=str, help="Program name: CSE or MIC — determines required credits, curriculum filter, and elective selection")
    parser.add_argument("program_knowledge", type=Path, help="Path to program knowledge markdown file (program.md)")
    args = parser.parse_args()

    if not args.transcript.exists():
        print(f"Error: transcript file not found: {args.transcript}", file=sys.stderr)
        return 1

    program_codes, program_credits = load_program_courses(args.program_knowledge)
    program_key = (args.program_name or "").strip().upper()
    allowed_codes = program_codes.get(program_key) if program_key in ("CSE", "MIC") else None
    credits_by_program = program_credits if program_key in ("CSE", "MIC") else None

    # Gate elective courses behind selection — remove from base allowed set so unselected ones don't count.
    # CRITICAL: only remove courses that are PURELY electives — i.e. not also required Major Core.
    # MIC317, MIC201, MIC416 etc. appear in both MIC_ELECTIVES and Major Core; they must stay in
    # allowed_codes so they are always counted as required courses regardless of elective selection.
    if program_key == "MIC" and allowed_codes is not None:
        _mic_core_all = set().union(*MIC_REQUIRED_CATEGORIES.values())
        _purely_elective = set(MIC_ELECTIVES) - _mic_core_all
        allowed_codes = allowed_codes - _purely_elective

    rows = load_transcript(args.transcript)

    # --- MIC: Core Choice Selection (Humanities / Social Sciences / Science) ---
    # Must run BEFORE elective selection and credit tally so excluded choices
    # are stripped from allowed_codes first.
    if program_key == "MIC":
        core_excluded = select_mic_core_choices(rows)
        alias_exclusions = resolve_mic_aliases(rows)
        if alias_exclusions:
            print("\n  SHLS Core alias resolution (equivalent course pairs):")
            for excl, kept in alias_exclusions.items():
                print(f"    {excl} excluded — {kept} already satisfies this slot (better/equal grade).")
            print()
        if allowed_codes is not None:
            allowed_codes = allowed_codes - core_excluded - set(alias_exclusions.keys())

    # --- Elective Selection ---
    major_electives: list[str] = []
    open_elective: str = ""
    if program_key in ("CSE", "MIC"):
        major_electives, open_elective, free_electives = select_electives(program_key, rows, allowed_codes=allowed_codes)
        print_elective_summary(major_electives, open_elective, program_key, free_electives=free_electives)
        # Merge selected electives into allowed curriculum so they count toward the tally
        if allowed_codes is not None:
            all_selected = set(major_electives) | set(free_electives) | ({open_elective} if open_elective else set())
            allowed_codes = allowed_codes | all_selected

    total, per_course, by_course = compute_total_valid_credits(
        rows,
        allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=program_key if program_key in ("CSE", "MIC") else None,
    )
    required = get_required_credits(args.program_name)
    print_report(
        args.transcript,
        args.program_name,
        total,
        per_course,
        by_course,
        required,
        allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=program_key if program_key in ("CSE", "MIC") else None,
        major_electives=major_electives,
        open_elective=open_elective,
        free_electives=free_electives,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())