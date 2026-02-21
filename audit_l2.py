#!/usr/bin/env python3
"""
Level 2: CGPA Engine & Waiver Handler
Builds on L1 (credit tally) and adds:
  - Weighted CGPA calculation per NSU rules
  - Waiver handling (ENG102 for CSE)
  - Class equivalence reporting
Usage: ./audit_l2.py transcript.csv program_name program_knowledge.md
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional, Set

# ---------------------------------------------------------------------------
# Constants (inherited from L1)
# ---------------------------------------------------------------------------

CSE_TRAILS: dict[str, list[str]] = {
    "Algorithms and Computation": ["CSE257", "CSE417", "CSE326", "CSE426", "CSE273", "CSE473"],
    "Software Engineering":       ["CSE411"],
    "Networks":                   ["CSE422", "CSE562", "CSE338", "CSE438", "CSE482", "CSE485", "CSE486"],
    "Computer Architecture and VLSI": ["CSE435", "CSE413", "CSE414"],
    "Artificial Intelligence":    ["CSE440", "CSE445", "CSE465", "CSE467", "CSE419", "CSE598"],
}

MIC_ELECTIVES: list[str] = [
    "MIC201", "MIC318", "MIC404", "MIC311", "MIC309", "MIC416", "MIC417", "MIC317", "MIC418"
]

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
        "MIC202", "MIC206", "MIC307", "MIC314",
        "MIC315", "MIC315L", "MIC316", "MIC316L", "MIC317", "MIC317L",
        "MIC401", "MIC412", "MIC413", "MIC413L",
        "MIC414", "MIC414L", "MIC415", "MIC415L", "MIC498",
    },
}

# NSU grade scale
GRADE_RANK = {
    "A": 10, "A-": 9, "B+": 8, "B": 7, "B-": 6,
    "C+": 5, "C": 4, "C-": 3, "D+": 2, "D": 1,
}
PASSING_GRADES = set(GRADE_RANK.keys())
NO_CREDIT_GRADES = {"F", "W", "I"}

# NSU grade points (from program.md grading scale)
GRADE_POINTS: dict[str, float] = {
    "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "F": 0.0,
}
# Grades that count toward CGPA denominator (W and I do NOT)
CGPA_GRADES = set(GRADE_POINTS.keys())  # A, A-, B+, ... D, F

# NSU class equivalence
CLASS_EQUIVALENCE: list[tuple[float, float, str]] = [
    (3.00, 4.00, "First Class"),
    (2.50, 2.99, "Second Class"),
    (2.00, 2.49, "Third Class"),
    (0.00, 1.99, "Below Standard"),
]

# CSE NCL labs — non-credit, excluded from CGPA
CSE_NCL_LABS = {"CSE225L", "CSE231L", "CSE311L", "CSE331L", "CSE332L", "BIO103L"}

def get_ncl_labs(program_key: Optional[str] = None) -> set:
    if program_key == "CSE":
        return CSE_NCL_LABS
    return CSE_NCL_LABS - {"BIO103L"}  # BIO103L is 1-credit for MIC

# Courses explicitly excluded from CGPA by program rule
CGPA_EXCLUDED_BY_PROGRAM: dict[str, set[str]] = {
    "CSE": {"MAT116"},  # 0-credit, explicitly stated "not counted in CGPA"
    "MIC": set(),       # no explicit CGPA exclusions for MIC
}

PROGRAM_REQUIRED_CREDITS = {"CSE": 130, "MIC": 120}

MIC_ALIAS_PAIRS: list[tuple[str, str]] = [
    ("BIO201",  "MIC110"),
    ("BIO201L", "MIC101L"),
    ("BIO202",  "MIC101"),
    ("BIO202L", "MIC101L"),
]

MIC_HUMANITIES_CHOICES: list[str] = ["HIS101", "HIS103", "PHI101"]
MIC_SOCIAL_CHOICES: list[str]     = ["POL101", "POL104", "ECO101", "ECO104", "SOC101", "ANT101"]
MIC_SCIENCE_CHOICES: list[tuple[str, str]] = [
    ("BIO103", "BIO103L"),
    ("PHY107", "PHY107L"),
]

# ---------------------------------------------------------------------------
# Shared helpers (from L1)
# ---------------------------------------------------------------------------

def normalize_course_code(raw: str) -> str:
    return re.sub(r"\s+", "", (raw or "").strip()).upper()

def parse_credits(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0

def normalize_grade(raw: str) -> str:
    return (raw or "").strip().upper()

def is_passing(grade: str) -> bool:
    return grade in PASSING_GRADES

def has_passing_attempt(attempts: list[dict]) -> bool:
    return any(is_passing(a["grade"]) for a in attempts)

def get_display_grade(attempts: list[dict]) -> str:
    if not attempts:
        return "—"
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        return best["grade"]
    return attempts[-1]["grade"] if attempts[-1]["grade"] else "—"

def valid_credits_for_course(attempts: list[dict]) -> float:
    passing = [a for a in attempts if is_passing(a["grade"])]
    if not passing:
        return 0.0
    best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
    return best["credits"]

def _prompt_pick(prompt: str, options: list[str], display: Optional[list[str]] = None) -> str:
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

def _prompt_yes_no(prompt: str) -> bool:
    while True:
        raw = input(f"  {prompt} (y/n): ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")

def _course_display(code: str, rows: list[dict]) -> str:
    attempts = [r for r in rows if normalize_course_code(r["course_code"]) == normalize_course_code(code)]
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        cr = best["credits"]
        cr_str = str(int(cr)) if cr == int(cr) else str(cr)
        return f"{code:<10}  ({cr_str} cr, {best['grade']})"
    return code

def _get_taken_courses(rows: list[dict]) -> list[str]:
    seen: dict[str, list[dict]] = {}
    for r in rows:
        seen.setdefault(r["course_code"], []).append(r)
    return [code for code, attempts in seen.items() if has_passing_attempt(attempts)]

# ---------------------------------------------------------------------------
# Program knowledge parsing (from L1)
# ---------------------------------------------------------------------------

def _extract_course_codes_from_text(text: str) -> Set[str]:
    codes: Set[str] = set()
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        first_cell = re.sub(r"\*\*", "", parts[1].strip())
        if not first_cell or first_cell.upper() in ("COURSE", "CREDITS", "NOTES") or re.match(r"^[-]+$", first_cell):
            continue
        course_part = first_cell.split(",")[0].strip()
        for segment in re.split(r"\s*/\s*|\s+and\s+", course_part, flags=re.IGNORECASE):
            for match in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*", segment.strip()):
                code = normalize_course_code(match.group(0))
                if len(code) >= 4 and code not in ("CHOOSE", "ONE", "LAB", "NONCREDIT"):
                    codes.add(code)
    return codes

def _extract_course_credits_from_text(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        first_cell = re.sub(r"\*\*", "", parts[1].strip())
        cred_cell = parts[2].strip() if len(parts) > 2 else "0"
        if not first_cell or first_cell.upper() in ("COURSE", "CREDITS", "NOTES") or re.match(r"^[-]+$", first_cell):
            continue
        if re.match(r"non-?credit", cred_cell, flags=re.IGNORECASE):
            cred_values = [0.0]
        else:
            cred_values = [float(m) for m in re.findall(r"\d+\.?\d*", cred_cell)] or [0.0]
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

def load_transcript(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return rows
        keys = {k.strip().lower().replace(" ", "_"): k for k in reader.fieldnames}
        for row in reader:
            course_code = normalize_course_code((row.get(keys.get("course_code", "Course_Code")) or "").strip())
            credits = parse_credits(row.get(keys.get("credits", "Credits")) or "0")
            grade = normalize_grade(row.get(keys.get("grade", "Grade")) or "")
            semester = (row.get(keys.get("semester", "Semester")) or "").strip()
            if not course_code and not grade and credits == 0:
                continue
            rows.append({
                "course_code": course_code or "UNKNOWN",
                "credits": credits,
                "grade": grade,
                "semester": semester,
            })
    return rows

# ---------------------------------------------------------------------------
# L1 credit tally (from L1)
# ---------------------------------------------------------------------------

def compute_total_valid_credits(
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
) -> tuple[float, dict[str, float], dict[str, list[dict]]]:
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"], []).append(r)

    ncl = get_ncl_labs(program_key)
    per_course: dict[str, float] = {}
    for code, attempts in by_course.items():
        normalized = normalize_course_code(code)
        if normalized in ncl:
            per_course[code] = 0.0
            continue
        raw_credits = valid_credits_for_course(attempts)
        if allowed_codes is not None:
            if normalized not in allowed_codes:
                per_course[code] = 0.0
            else:
                if program_credits and program_key and normalized in program_credits.get(program_key, {}):
                    override = program_credits[program_key][normalized]
                    per_course[code] = override if has_passing_attempt(attempts) else 0.0
                else:
                    per_course[code] = raw_credits
        else:
            per_course[code] = raw_credits

    return sum(per_course.values()), per_course, by_course

# ---------------------------------------------------------------------------
# L2 NEW: CGPA computation
# ---------------------------------------------------------------------------

def compute_cgpa(
    rows: list[dict],
    allowed_codes: Optional[Set[str]],
    program_key: str,
    program_credits: Optional[dict[str, dict[str, float]]] = None,
) -> tuple[float, float, float, dict[str, tuple[str, float, float]]]:
    """
    Compute weighted CGPA per NSU rules:
      - Only courses in the program curriculum count (allowed_codes)
      - NCL labs and 0-credit courses are excluded
      - W and I: excluded from both numerator and denominator
      - F: included (0 grade points, credits count in denominator)
      - Retakes: only the best grade attempt is used
      - Returns: (cgpa, total_grade_points, total_credits_attempted,
                  per_course dict: code -> (grade, credits, grade_points))
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"], []).append(r)

    ncl = get_ncl_labs(program_key)
    cgpa_excluded = CGPA_EXCLUDED_BY_PROGRAM.get(program_key, set())

    total_points = 0.0
    total_credits = 0.0
    per_course_cgpa: dict[str, tuple[str, float, float]] = {}

    for code, attempts in by_course.items():
        normalized = normalize_course_code(code)

        # Must be in the required curriculum
        if allowed_codes is not None and normalized not in allowed_codes:
            continue

        # NCL labs and explicitly CGPA-excluded courses (MAT116 for CSE) don't participate
        if normalized in ncl or normalized in cgpa_excluded:
            continue

        # W and I: skip entirely — they don't affect CGPA
        cgpa_attempts = [a for a in attempts if a["grade"] not in ("W", "I")]
        if not cgpa_attempts:
            continue

        # Determine effective credits (use program override if defined)
        def effective_credits(attempt: dict) -> float:
            if program_credits and program_key and normalized in program_credits.get(program_key, {}):
                return program_credits[program_key][normalized]
            return attempt["credits"]

        # Retake rule: use best passing grade if any; otherwise the F (worst case)
        passing = [a for a in cgpa_attempts if is_passing(a["grade"])]
        if passing:
            best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0))
            grade = best["grade"]
            credits = effective_credits(best)
        else:
            # All remaining attempts are F — use most recent
            f_attempt = cgpa_attempts[-1]
            grade = "F"
            credits = effective_credits(f_attempt)

        # 0-credit courses don't participate in CGPA
        if credits <= 0:
            continue

        gp = GRADE_POINTS.get(grade, 0.0)
        total_points += gp * credits
        total_credits += credits
        per_course_cgpa[code] = (grade, credits, gp)

    cgpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    return cgpa, total_points, total_credits, per_course_cgpa


def get_class_equivalence(cgpa: float) -> str:
    for low, high, label in CLASS_EQUIVALENCE:
        if low <= cgpa <= high:
            return label
    return "—"

# ---------------------------------------------------------------------------
# MIC choice / alias helpers (from L1)
# ---------------------------------------------------------------------------

def resolve_mic_aliases(rows: list[dict]) -> dict[str, str]:
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)
    exclusions: dict[str, str] = {}
    for code_a, code_b in MIC_ALIAS_PAIRS:
        a, b = normalize_course_code(code_a), normalize_course_code(code_b)
        has_a = a in by_course and has_passing_attempt(by_course[a])
        has_b = b in by_course and has_passing_attempt(by_course[b])
        if has_a and has_b:
            grade_a = GRADE_RANK.get(get_display_grade(by_course[a]), 0)
            grade_b = GRADE_RANK.get(get_display_grade(by_course[b]), 0)
            if grade_b > grade_a:
                exclusions[a] = b
            else:
                exclusions[b] = a
    return exclusions

def select_mic_core_choices(rows: list[dict]) -> set[str]:
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

    passed_pairs = []
    for theory, lab in MIC_SCIENCE_CHOICES:
        if theory in by_course and has_passing_attempt(by_course[theory]):
            passed_pairs.append((theory, lab))

    if len(passed_pairs) > 1:
        print("\n  SCIENCE — student passed courses from multiple pairs (pick one pair to count):")
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

# ---------------------------------------------------------------------------
# Elective selection (from L1)
# ---------------------------------------------------------------------------

def _mic_course_category(code: str) -> Optional[str]:
    normalized = normalize_course_code(code)
    for category, codes in MIC_REQUIRED_CATEGORIES.items():
        if normalized in codes:
            return category
    return None

def select_electives_cse(rows: list[dict], allowed_codes: Optional[Set[str]] = None) -> tuple[list[str], str, list[str]]:
    taken = set(_get_taken_courses(rows))
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

    print("\n  Available elective courses from your transcript:\n")
    for trail_name, codes in trail_taken.items():
        print(f"  [{trail_name}]")
        for c in codes:
            print(f"    {_course_display(c, rows)}")
    all_trail_codes = {c for trail in CSE_TRAILS.values() for c in trail}
    open_preview = sorted([c for c in taken if c in all_trail_codes or c not in (allowed_codes or set())])
    if open_preview:
        print(f"\n  [Open Elective candidates]  (trail courses + outside curriculum)")
        for c in open_preview:
            print(f"    {_course_display(c, rows)}")
    print()

    major_electives: list[str] = []

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
        print(f"  Only one course available in '{primary_name}' — counting {c1} only.")

    secondary_options = [t for t in trail_taken if t != primary_name]
    open_elective = ""
    if secondary_options:
        secondary_name = _prompt_pick("\nSelect your SECONDARY trail (1 course from here):", secondary_options)
        secondary_pool = trail_taken[secondary_name]
        print(f"\nSelect 1 course from '{secondary_name}':")
        c3 = _prompt_pick("", secondary_pool, display=[_course_display(c, rows) for c in secondary_pool])
        major_electives.append(c3)

    open_pool = sorted([
        c for c in taken
        if c not in set(major_electives)
        and (c in all_trail_codes or c not in (allowed_codes or set()))
    ])
    if open_pool:
        print("\nSelect your OPEN ELECTIVE (outside CSE curriculum + unselected major electives):")
        open_elective = _prompt_pick("", open_pool, display=[_course_display(c, rows) for c in open_pool])
    else:
        print("  No outside-curriculum courses found in transcript for open elective.")

    return major_electives, open_elective, []

def select_electives_mic(rows: list[dict]) -> tuple[list[str], str, list[str]]:
    taken = set(_get_taken_courses(rows))
    _major_core_required = MIC_REQUIRED_CATEGORIES.get("Major Core", set())
    major_pool = [c for c in MIC_ELECTIVES if c in taken and c not in _major_core_required]

    print("\n" + "=" * 50)
    print("  MIC ELECTIVE SELECTION")
    print("  Showing courses from your transcript only.")
    print("  Rule: 3 major electives + 3 free electives")
    print("=" * 50)

    free_available = [c for c in taken if c not in set(major_pool) and _mic_course_category(c) is None]
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

def select_electives(program_key: str, rows: list[dict], allowed_codes: Optional[Set[str]] = None) -> tuple[list[str], str, list[str]]:
    if program_key == "CSE":
        return select_electives_cse(rows, allowed_codes=allowed_codes)
    elif program_key == "MIC":
        return select_electives_mic(rows)
    return [], "", []

def print_elective_summary(major_electives: list[str], open_elective: str, program_key: str, free_electives: Optional[list[str]] = None) -> None:
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

# ---------------------------------------------------------------------------
# L2 NEW: Waiver handler
# ---------------------------------------------------------------------------

def handle_waivers(program_key: str, allowed_codes: Set[str], required_credits: int) -> tuple[Set[str], int, list[str]]:
    """
    Prompt admin about applicable waivers. Returns updated
    (allowed_codes, required_credits, waiver_notes).
    """
    waiver_notes: list[str] = []

    if program_key == "CSE":
        print("\n" + "=" * 50)
        print("  WAIVER CHECK")
        print("=" * 50)
        eng102_waived = _prompt_yes_no("Is ENG102 waived for this student?")
        if eng102_waived:
            allowed_codes = allowed_codes - {"ENG102"}
            required_credits -= 3  # 130 → 127
            waiver_notes.append("ENG102 waived — required credits reduced from 130 to 127.")
            print("  ✓ ENG102 waiver applied. Required credits: 127.")
        else:
            print("  No waivers applied.")
        print()

    return allowed_codes, required_credits, waiver_notes

# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def reason_not_counted(
    attempts: list[dict],
    course_code: str = "",
    program_name: str = "",
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
) -> str:
    if not attempts:
        return "no attempts on transcript"
    normalized = normalize_course_code(course_code) if course_code else ""

    if waived_courses and normalized in waived_courses:
        return "waived — excluded from requirements"

    if core_excluded and normalized in core_excluded:
        return "choice slot filled by another course"

    if unselected_electives and normalized in unselected_electives:
        return "elective not selected"

    if allowed_codes is not None and program_name and course_code:
        if normalized not in allowed_codes:
            return f"not in {program_name} curriculum"

    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: (GRADE_RANK.get(a["grade"], 0), a["credits"]))
        program_defined_credit = (
            program_credits[program_key].get(normalized)
            if program_credits and program_key and normalized in program_credits.get(program_key, {})
            else None
        )
        effective_credit = program_defined_credit if program_defined_credit is not None else best["credits"]
        if effective_credit == 0:
            label = "non-credit lab" if normalized.endswith("L") else "0-credit course"
            return f"{label} (credits not applied toward graduation)"
        return "error: has passing attempt but counted 0"

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
    return " and ".join(parts) + "; no passing retake"


def print_report(
    transcript_path: Path,
    program_name: str,
    total: float,
    per_course: dict[str, float],
    by_course: dict[str, list[dict]],
    required_credits: Optional[int],
    cgpa: float,
    total_gp: float,
    total_cr_attempted: float,
    per_course_cgpa: dict[str, tuple[str, float, float]],
    waiver_notes: list[str],
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str, dict[str, float]]] = None,
    program_key: Optional[str] = None,
    major_electives: Optional[list[str]] = None,
    open_elective: str = "",
    free_electives: Optional[list[str]] = None,
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
) -> None:
    major_set = set(normalize_course_code(c) for c in (major_electives or []))
    free_set  = set(normalize_course_code(c) for c in (free_electives or []))
    open_code = normalize_course_code(open_elective) if open_elective else ""
    ncl = get_ncl_labs(program_key)
    width = 56

    print("=" * width)
    print("  LEVEL 2: CGPA & CREDIT TALLY REPORT")
    print("=" * width)
    print(f"  Transcript : {transcript_path.name}")
    print(f"  Program    : {program_name}")
    if waiver_notes:
        for note in waiver_notes:
            print(f"  Waiver     : {note}")
    print("-" * width)

    # --- Credit summary ---
    credit_ok = total >= (required_credits or 0)
    if required_credits is not None:
        status_cr = "✓ MET" if credit_ok else "✗ NOT MET"
        print(f"  TOTAL VALID CREDITS : {total:.1f} / {required_credits}  [{status_cr}]")
    else:
        print(f"  TOTAL VALID CREDITS : {total:.1f}")

    # --- CGPA summary ---
    class_eq = get_class_equivalence(cgpa)
    cgpa_ok = cgpa >= 2.0
    status_gpa = "✓ MET" if cgpa_ok else "✗ BELOW MINIMUM (2.0 required)"
    print(f"  CGPA                : {cgpa:.2f}  [{class_eq}]  [{status_gpa}]")
    print(f"  Grade Points Earned : {total_gp:.2f}  |  Credits Attempted : {total_cr_attempted:.1f}")
    print("-" * width)

    # --- Per-course credit table ---
    col_code, col_cr, col_grade, col_status = 14, 10, 8, 45
    sep = ("  +" + "-" * (col_code + 2) + "+" + "-" * (col_cr + 2) + "+"
           + "-" * (col_grade + 2) + "+" + "-" * (col_status + 2) + "+")
    header = "  | {:^{}} | {:^{}} | {:^{}} | {:^{}} |".format(
        "Course", col_code, "Credits", col_cr, "Grade", col_grade, "Status", col_status)

    counted = [(c, cr) for c, cr in sorted(per_course.items())
               if cr > 0 and normalize_course_code(c) not in ncl]
    excluded = [(c, cr) for c, cr in sorted(per_course.items())
                if cr == 0 and normalize_course_code(c) not in ncl]

    print("  Counted (credits toward graduation):\n")
    print(sep); print(header); print(sep)
    for code, cr in counted:
        grade = get_display_grade(by_course[code])
        normalized = normalize_course_code(code)
        if normalized == open_code:
            label = "Free Elective" if program_key == "MIC" else "Open Elective"
            status = f"Counted [{label}]"
        elif normalized in free_set:
            status = "Counted [Free Elective]"
        elif normalized in major_set:
            status = "Counted [Major Elective]"
        else:
            status = "Counted"
        status = status[:col_status] if len(status) <= col_status else status[:col_status-3] + "..."
        print("  | {:<{}} | {:>{}.1f} | {:<{}} | {:<{}} |".format(
            code, col_code, cr, col_cr, grade, col_grade, status, col_status))
    print(sep)
    print()

    if excluded:
        print("  Not counted (0 credits):\n")
        print(sep); print(header); print(sep)
        for code, _ in excluded:
            grade = get_display_grade(by_course[code])
            reason = reason_not_counted(
                by_course[code], course_code=code, program_name=program_name,
                allowed_codes=allowed_codes, program_credits=program_credits,
                program_key=program_key, core_excluded=core_excluded,
                unselected_electives=unselected_electives, waived_courses=waived_courses,
            )
            reason = reason[:col_status] if len(reason) <= col_status else reason[:col_status-3] + "..."
            print("  | {:<{}} | {:^{}} | {:<{}} | {:<{}} |".format(
                code, col_code, "—", col_cr, grade, col_grade, reason, col_status))
        print(sep)
        print()

    # --- CGPA breakdown table ---
    print("  CGPA Breakdown (courses contributing to CGPA):\n")
    col_gp = 8
    sep2 = ("  +" + "-" * (col_code + 2) + "+" + "-" * (col_grade + 2) + "+"
            + "-" * (col_cr + 2) + "+" + "-" * (col_gp + 2) + "+" + "-" * 14 + "+")
    header2 = "  | {:^{}} | {:^{}} | {:^{}} | {:^{}} | {:^14} |".format(
        "Course", col_code, "Grade", col_grade, "Credits", col_cr, "Pts/Cr", col_gp, "Grade Points")
    print(sep2); print(header2); print(sep2)
    for code, (grade, credits, gp) in sorted(per_course_cgpa.items()):
        earned = gp * credits
        print("  | {:<{}} | {:<{}} | {:>{}.1f} | {:>{}.1f} | {:>14.2f} |".format(
            code, col_code, grade, col_grade, credits, col_cr, gp, col_gp, earned))
    print(sep2)
    print(f"\n  Total Grade Points : {total_gp:.2f}")
    print(f"  Credits Attempted  : {total_cr_attempted:.1f}")
    print(f"  CGPA               : {cgpa:.2f}  ({class_eq})")

    if cgpa >= 3.00:
        standing = "First Class"
    elif cgpa >= 2.50:
        standing = "Second Class"
    elif cgpa >= 2.00:
        standing = "Third Class"
    else:
        standing = "⚠  PROBATION — CGPA below 2.0 minimum"
    print(f"  Standing           : {standing}")
    print("\n" + "=" * width)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Level 2: CGPA Engine & Waiver Handler."
    )
    parser.add_argument("transcript", type=Path)
    parser.add_argument("program_name", type=str)
    parser.add_argument("program_knowledge", type=Path)
    args = parser.parse_args()

    if not args.transcript.exists():
        print(f"Error: transcript not found: {args.transcript}", file=sys.stderr)
        return 1

    program_codes, program_credits = load_program_courses(args.program_knowledge)
    program_key = (args.program_name or "").strip().upper()
    allowed_codes = program_codes.get(program_key) if program_key in ("CSE", "MIC") else None
    credits_by_program = program_credits if program_key in ("CSE", "MIC") else None
    required_credits = PROGRAM_REQUIRED_CREDITS.get(program_key)

    # Gate purely-elective MIC courses behind selection
    if program_key == "MIC" and allowed_codes is not None:
        _mic_core_all = set().union(*MIC_REQUIRED_CATEGORIES.values())
        _purely_elective = set(MIC_ELECTIVES) - _mic_core_all
        allowed_codes = allowed_codes - _purely_elective

    rows = load_transcript(args.transcript)

    # --- Waiver handling (L2 addition) ---
    waived_courses: Set[str] = set()
    waiver_notes: list[str] = []
    if program_key in ("CSE", "MIC") and allowed_codes is not None:
        # Snapshot BEFORE waiver so we diff only the waiver removal — not elective gating.
        pre_waiver_allowed = set(allowed_codes)
        allowed_codes, required_credits, waiver_notes = handle_waivers(
            program_key, allowed_codes, required_credits or 0
        )
        # Only courses actually removed by the waiver prompt count as waived.
        waived_courses = pre_waiver_allowed - allowed_codes

    # --- MIC core choices ---
    core_excluded: Set[str] = set()
    if program_key == "MIC":
        core_excluded = select_mic_core_choices(rows)
        alias_exclusions = resolve_mic_aliases(rows)
        if alias_exclusions:
            print("\n  SHLS Core alias resolution (equivalent course pairs):")
            for excl, kept in alias_exclusions.items():
                print(f"    {excl} excluded — {kept} already satisfies this slot.")
            print()
        core_excluded = core_excluded | set(alias_exclusions.keys())
        if allowed_codes is not None:
            allowed_codes = allowed_codes - core_excluded

    # Track elective candidates for labelling
    all_elective_candidates: Set[str] = set()
    if program_key == "CSE":
        all_elective_candidates = {c for trail in CSE_TRAILS.values() for c in trail}
    elif program_key == "MIC":
        all_elective_candidates = set(MIC_ELECTIVES)

    # --- Elective selection ---
    major_electives: list[str] = []
    open_elective: str = ""
    free_electives: list[str] = []
    if program_key in ("CSE", "MIC"):
        major_electives, open_elective, free_electives = select_electives(
            program_key, rows, allowed_codes=allowed_codes
        )
        print_elective_summary(major_electives, open_elective, program_key, free_electives=free_electives)
        if allowed_codes is not None:
            all_selected = set(major_electives) | set(free_electives) | ({open_elective} if open_elective else set())
            allowed_codes = allowed_codes | all_selected

    all_selected_electives = set(major_electives) | set(free_electives) | ({open_elective} if open_elective else set())
    unselected_electives = all_elective_candidates - all_selected_electives

    # --- L1: credit tally ---
    total, per_course, by_course = compute_total_valid_credits(
        rows, allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=program_key if program_key in ("CSE", "MIC") else None,
    )

    # --- L2: CGPA ---
    cgpa, total_gp, total_cr_attempted, per_course_cgpa = compute_cgpa(
        rows, allowed_codes=allowed_codes,
        program_key=program_key,
        program_credits=credits_by_program,
    )

    # --- Report ---
    print_report(
        args.transcript, args.program_name,
        total, per_course, by_course, required_credits,
        cgpa, total_gp, total_cr_attempted, per_course_cgpa,
        waiver_notes,
        allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=program_key if program_key in ("CSE", "MIC") else None,
        major_electives=major_electives,
        open_elective=open_elective,
        free_electives=free_electives,
        core_excluded=core_excluded,
        unselected_electives=unselected_electives,
        waived_courses=waived_courses,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())