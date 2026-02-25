#!/usr/bin/env python3
"""
Level 3: Audit & Deficiency Reporter
Builds on L2: compares student history against program rules and reports
  - Missing mandatory courses (by category)
  - Credit shortfall (precise float; not int-truncated)
  - Probation (CGPA < 2.0)
  - Prerequisite failures
  - Retakes: only best attempt per course counts (same rule as L2)

FIXES applied (vs original):
  #1  credit_shortfall: removed int() truncation — e.g., 127.5 credits no longer
      shows a shortfall of 3 when only 2.5 are missing.
  #6  Program validation inherited from run_audit() in audit_l2.
  #9  Passes report_level=3 to print_report() so the header reads
      "LEVEL 3 ▸ CGPA & CREDIT TALLY REPORT" — not "LEVEL 2".
  All L1/L2 fixes inherited automatically via imports.

Usage: python3 audit_l3.py transcript.csv program_name program_knowledge.md [--no-interact]
"""

import argparse
import sys
from pathlib import Path
from typing import Set

import audit_l1 as _l1
from audit_l1 import (
    _btop, _bsep, _bbot, _bline, _BW,
    _TTOP, _TROW_SEP, _TBOT, _THDR, _trow, _tsep,
    normalize_course_code,
    CSE_TRAILS, CSE_GED_CHOICE_GROUPS, CSE_INTERNSHIP_RESEARCH, CSE_MINOR_COURSES,
    MIC_ALIAS_PAIRS, MIC_LANGUAGE_CHOICES, MIC_HUMANITIES_CHOICES,
    MIC_SOCIAL_CHOICES, MIC_SCIENCE_CHOICES, MIC_REQUIRED_CATEGORIES,
    get_ncl_labs,
    WAIVER_CREDITS_EACH,
)
from audit_l2 import (
    run_audit,
    print_report,
)


# ══════════════════════════════════════════════════════════════════════════════
#  Deficiency computation
# ══════════════════════════════════════════════════════════════════════════════
def compute_deficiencies(result: dict) -> dict:
    """
    Compare student state against program requirements.
    Returns a dict with keys:
      eligible          : bool
      credit_shortfall  : float   (FIX #1: not int-truncated)
      probation         : bool
      missing_mandatory : list of (category_label, list_of_codes_or_messages)
      prereq_failures_list : list of (course, reason)
      retake_note       : str
    """
    program_key      = result.get("program_key")
    passed_set: Set[str] = result.get("passed_set") or set()
    waived           = result.get("waived_courses") or set()
    waived_n         = {normalize_course_code(c) for c in waived}
    required_credits = result.get("required_credits") or 0
    credit_completed = result.get("credit_completed") or 0.0
    cgpa             = result.get("cgpa") or 0.0
    prereq_failures  = result.get("prereq_failures") or {}
    allowed_codes    = result.get("allowed_codes") or set()
    program_codes    = result.get("program_codes") or {}
    major_electives  = result.get("major_electives") or []
    open_elective    = result.get("open_elective") or ""
    free_electives   = result.get("free_electives") or []

    # FIX #1: preserve float precision — remove int() truncation
    credit_shortfall = max(0.0, required_credits - credit_completed) if required_credits else 0.0
    probation        = cgpa < 2.0

    missing_mandatory: list[tuple[str,list[str]]] = []

    prereq_failed_n = {normalize_course_code(c) for c in (prereq_failures or {}).keys()}

    if program_key == "CSE":
        cse_codes   = program_codes.get("CSE") or set()
        all_trail   = {c for trail in CSE_TRAILS.values() for c in trail}
        choice_codes= {c for group in CSE_GED_CHOICE_GROUPS for c in group}
        ncl         = get_ncl_labs("CSE")
        required_single = (cse_codes - all_trail - choice_codes
                           - CSE_INTERNSHIP_RESEARCH - ncl - CSE_MINOR_COURSES)
        missing_single = sorted(
            normalize_course_code(c) for c in required_single
            if normalize_course_code(c) not in waived_n
            and normalize_course_code(c) not in passed_set
            and normalize_course_code(c) not in prereq_failed_n  # already in prereq_failures
        )
        if missing_single:
            missing_mandatory.append(("Required core courses", missing_single))

        for group in CSE_GED_CHOICE_GROUPS:
            if not any(c in passed_set for c in group):
                missing_mandatory.append(("GED choice group (one course required)", group.copy()))

        if not (CSE_INTERNSHIP_RESEARCH & passed_set):
            missing_mandatory.append(("Internship / Research (1 credit)", list(CSE_INTERNSHIP_RESEARCH)))

        num_trail = len([c for c in major_electives if normalize_course_code(c) in all_trail])
        if num_trail < 3:
            missing_mandatory.append(("Major electives (trail)", [f"Need {3-num_trail} more trail elective(s)"]))
        if not open_elective:
            missing_mandatory.append(("Open elective", ["Need 1 open elective (3 credits)"]))

    elif program_key == "MIC":
        satisfied: Set[str] = passed_set | waived_n
        for a, b in MIC_ALIAS_PAIRS:
            if a in passed_set or b in passed_set:
                satisfied.add(a); satisfied.add(b)
        for group in [MIC_LANGUAGE_CHOICES, MIC_HUMANITIES_CHOICES, MIC_SOCIAL_CHOICES]:
            if any(c in passed_set for c in group):
                satisfied.update(group)
        science_ok = any(
            theory in passed_set and lab in passed_set
            for theory, lab in MIC_SCIENCE_CHOICES
        )
        if science_ok:
            for theory, lab in MIC_SCIENCE_CHOICES:
                satisfied.add(theory); satisfied.add(lab)

        required_all = set().union(*MIC_REQUIRED_CATEGORIES.values())
        missing_codes = required_all - satisfied - prereq_failed_n  # prereq failures listed separately
        if missing_codes:
            # Change 4: consolidate choice-group alternatives into "A/B" notation so the
            # deficiency report shows one slot ("BEN205/ENG111") rather than two lines.
            _CHOICE_GROUPS: list[list[str]] = (
                [list(MIC_LANGUAGE_CHOICES), list(MIC_HUMANITIES_CHOICES), list(MIC_SOCIAL_CHOICES)]
                + [[a, b] for a, b in MIC_ALIAS_PAIRS]
                + [[t, l] for t, l in MIC_SCIENCE_CHOICES]
            )
            def _consolidate_mic(codes_set: set) -> list[str]:
                shown: set = set()
                result: list[str] = []
                for grp in _CHOICE_GROUPS:
                    overlap = [c for c in grp if c in codes_set and c not in shown]
                    if len(overlap) > 1:
                        result.append("/".join(overlap))   # e.g. "BEN205/ENG111"
                        shown.update(overlap)
                    elif len(overlap) == 1:
                        result.append(overlap[0])
                        shown.update(overlap)
                for c in sorted(codes_set - shown):
                    result.append(c)
                return result

            by_cat: dict[str, list[str]] = {}
            for cat, codes in MIC_REQUIRED_CATEGORIES.items():
                m_set = {c for c in codes if c in missing_codes}
                if m_set:
                    by_cat[cat] = _consolidate_mic(m_set)
            for cat, codes in sorted(by_cat.items()):
                missing_mandatory.append((cat, codes))

        major_set = {normalize_course_code(c) for c in major_electives}
        # MIC: open_elective is free elective #1; free_electives holds #2 and #3.
        # Must combine both to get the true free elective count.
        free_set  = {normalize_course_code(c) for c in free_electives}
        if open_elective:
            free_set.add(normalize_course_code(open_elective))
        if len(major_set) < 3:
            missing_mandatory.append(("Major electives", [f"Need {3-len(major_set)} more major elective(s)"]))
        if len(free_set) < 3:
            missing_mandatory.append(("Free electives",  [f"Need {3-len(free_set)} more free elective(s)"]))

    prereq_failures_list = list((prereq_failures or {}).items())

    credits_ok   = credit_completed >= (required_credits or 0)
    eligible     = bool(credits_ok and not probation and not missing_mandatory and not prereq_failures_list)

    return {
        "eligible":            eligible,
        "credit_shortfall":    credit_shortfall,
        "probation":           probation,
        "missing_mandatory":   missing_mandatory,
        "prereq_failures_list": prereq_failures_list,
        "retake_note":
            "Retake policy: only the best attempt per course counts toward credits and CGPA.",
    }

# ══════════════════════════════════════════════════════════════════════════════
#  Deficiency report printing
# ══════════════════════════════════════════════════════════════════════════════
def print_deficiency_report(result: dict, deficiencies: dict) -> None:
    eligible = deficiencies["eligible"]
    status   = "✓  ELIGIBLE FOR GRADUATION" if eligible else "✗  NOT ELIGIBLE FOR GRADUATION"

    print()
    print(_btop())
    print(_bline("LEVEL 3 ▸ DEFICIENCY REPORT"))
    print(_bsep())
    print(_bline(f"Transcript  :  {result['transcript_path'].name}"))
    print(_bline(f"Program     :  {result['program_name']}"))
    print(_bsep())
    print(_bline(f"Graduation Status  :  {status}"))
    print(_bsep())

    if eligible:
        print(_bline("  All requirements satisfied. Student is cleared for graduation."))
    else:
        # Credit shortfall
        sf = deficiencies["credit_shortfall"]
        if sf > 0:
            print(_bline(f"  ▸ Credit shortfall     :  {sf:.1f} credit(s) below the required total"))

        # Probation
        if deficiencies["probation"]:
            print(_bline("  ▸ Probation            :  CGPA is below the 2.0 minimum required for graduation"))

        # Missing mandatory courses / groups
        for cat, items in deficiencies["missing_mandatory"]:
            items_str = ", ".join(items)
            label = f"  ▸ Missing [{cat}]"
            # Fit into banner width; wrap if too long
            full = f"{label}  :  {items_str}"
            if len(full) <= _BW - 2:
                print(_bline(full))
            else:
                print(_bline(label))
                # print items in chunks
                chunk = ""
                for item in items:
                    candidate = (chunk + ("  " if chunk else "      ") + item)
                    if len(candidate) <= _BW - 4:
                        chunk = candidate
                    else:
                        if chunk: print(_bline(chunk))
                        chunk = "      " + item
                if chunk: print(_bline(chunk))

        # Prerequisite failures — course first, strip redundant prefix
        if deficiencies["prereq_failures_list"]:
            print(_bline("  ▸ Prerequisite failures:"))
            for course, reason in deficiencies["prereq_failures_list"]:
                detail = reason.removeprefix("prereq not met: ")
                print(_bline(f"      {course}  —  needs: {detail}"[:_BW - 2]))

    print(_bsep())
    print(_bline(f"  {deficiencies['retake_note']}"))
    print(_bbot())
    print()

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Level 3: Audit & Deficiency Reporter."
    )
    parser.add_argument("transcript",        type=Path)
    parser.add_argument("program_name",      type=str)
    parser.add_argument("program_knowledge", type=Path)
    parser.add_argument("--no-interact",     action="store_true",
                        help="Non-interactive: auto-select best options (AI agent / pipeline mode)")
    args = parser.parse_args()

    # Propagate no-interact flag into shared module
    _l1.NO_INTERACT = args.no_interact

    if not args.transcript.exists():
        print(f"  Error: transcript not found: {args.transcript}", file=sys.stderr)
        return 1

    # FIX #6: validate program name
    program_key = (args.program_name or "").strip().upper()
    if program_key not in ("CSE","MIC"):
        print(f"\n  Error: unsupported program '{args.program_name}'.", file=sys.stderr)
        print(  "  Supported programs: CSE, MIC", file=sys.stderr)
        return 1

    try:
        result = run_audit(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"  Error: {e}", file=sys.stderr)
        return 1

    # FIX #9: pass report_level=3 so the shared print_report header says "LEVEL 3"
    print_report(
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
        report_level=3,   # ← FIX #9
    )

    deficiencies = compute_deficiencies(result)
    print_deficiency_report(result, deficiencies)

    return 0 if deficiencies["eligible"] else 1


if __name__ == "__main__":
    sys.exit(main())