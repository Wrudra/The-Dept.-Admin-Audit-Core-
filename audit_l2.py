#!/usr/bin/env python3
"""
Level 2: CGPA Engine & Waiver Handler
Builds on Level 1 by adding:
  - Weighted CGPA calculation (NSU grade-point scale)
  - Formal waiver handling (ENG102, MAT112) as a separate admin step
  - Class equivalence reporting (First / Second / Third Class / Below Standard)
  - Full per-course CGPA breakdown table

FIXES applied (vs original):
  #8  L2 now imports shared logic from audit_l1 instead of duplicating ~1,000 lines.
  #9  print_report() accepts report_level param; L3 passes 3 to avoid "LEVEL 2" heading.
  #11 compute_cgpa() always normalises waived_courses before comparison.
  #12 Credit mismatch warning inherited via detect_credit_mismatches /
      print_credit_mismatch_warning; run_audit() now calls both.
  #17 compute_cgpa() _eff_cr(): non-program NSU courses (open/free electives not in
      program.md) are now capped at 3.0 credits, mirroring FIX #17 in audit_l1's
      compute_total_valid_credits(). Without this, a transcript credit of e.g. 6.0
      would inflate Credit Counted and Grade Points even though only 3.0 is counted
      toward graduation.
  #17 run_audit(): select_electives() now receives program_credits so _course_display()
      can apply the 3.0 cap in the selection menu, making the displayed credit match
      what the engine will actually count.
  All L1 fixes inherited automatically via import.

Usage: python3 audit_l2.py transcript.csv program_name program_knowledge.md [--no-interact]
"""

import argparse
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Set

# ── Import all shared logic from L1 ──────────────────────────────────────────
import audit_l1 as _l1
from audit_l1 import (
    # Visual helpers
    _btop, _bsep, _bbot, _bline, _BW,
    _TTOP, _TROW_SEP, _TBOT, _THDR, _trow, _tsep,
    _CC, _CCR, _CG, _CS,
    # Constants
    NSU_CATALOG_EXPANDED,
    CSE_TRAILS, MIC_ELECTIVES, CSE_GED_CHOICE_GROUPS,
    CSE_PREREQS, MIC_PREREQS,
    PASSING_GRADES, NO_CREDIT_GRADES, GRADE_RANK,
    CSE_NCL_LABS, MIC_NCL_LABS, get_ncl_labs,
    PROGRAM_BASE_CREDITS, WAIVERABLE_COURSES, WAIVER_CREDITS_EACH,
    CSE_INTERNSHIP_RESEARCH, CSE_MINOR_COURSES,
    CSE_BIO_INTERNSHIP_SLOT,
    MIC_REQUIRED_CATEGORIES, MIC_ALIAS_PAIRS,
    MIC_LANGUAGE_CHOICES, MIC_HUMANITIES_CHOICES, MIC_SOCIAL_CHOICES, MIC_SCIENCE_CHOICES,
    # Helpers
    normalize_course_code, parse_credits, normalize_grade,
    is_passing, has_passing_attempt, get_display_grade, valid_credits_for_course,
    build_passed_set, prereq_satisfied, compute_baseline_credits,
    load_program_courses, load_transcript,
    compute_total_valid_credits, reason_not_counted,
    _mic_course_category, resolve_mic_aliases, resolve_cse_choice_groups,
    select_mic_core_choices,
    select_electives, print_elective_summary,
    resolve_cse_bio_internship_choice,
    _prompt_yes_no, _prompt_pick, _course_display, _get_taken_courses,
    get_required_credits_for_waivers,
    detect_credit_mismatches, print_credit_mismatch_warning,
    detect_grade_anomalies, print_grade_anomaly_warning,
    NO_INTERACT,
)

# ══════════════════════════════════════════════════════════════════════════════
#  L2-specific: NSU grade-point scale and CGPA tables
# ══════════════════════════════════════════════════════════════════════════════
GRADE_POINTS: dict[str,float] = {
    "A":4.0,"A-":3.7,"B+":3.3,"B":3.0,"B-":2.7,
    "C+":2.3,"C":2.0,"C-":1.7,"D+":1.3,"D":1.0,"F":0.0,
}
CGPA_GRADES  = set(GRADE_POINTS.keys())   # W and I are NOT in this set

CLASS_EQUIVALENCE: list[tuple[float,float,str]] = [
    (3.00, 4.00, "First Class"),
    (2.50, 2.99, "Second Class"),
    (2.00, 2.49, "Third Class"),
    (0.00, 1.99, "Below Standard"),
]

# Courses explicitly excluded from the CGPA calculation per program rule
CGPA_EXCLUDED_BY_PROGRAM: dict[str,set[str]] = {
    "CSE": {"MAT116"},  # 0-credit in CSE; stated in program.md as "not counted in CGPA"
    "MIC": set(),
}

PROGRAM_REQUIRED_CREDITS = PROGRAM_BASE_CREDITS  # alias

def get_class_equivalence(cgpa: float) -> str:
    for lo, hi, label in CLASS_EQUIVALENCE:
        if lo <= cgpa <= hi: return label
    return "—"

# ══════════════════════════════════════════════════════════════════════════════
#  Waiver handler
# ══════════════════════════════════════════════════════════════════════════════
def handle_waivers(
    program_key: str,
    allowed_codes: Set[str],
    transcript_rows: Optional[list] = None,
) -> tuple[Set[str],int,Set[str],list[str]]:
    """
    Prompt admin about ENG102 / MAT112 waivers.
    Returns (allowed_codes, required_credits, waived_courses, waiver_notes).
    Waived courses count in Credit Completed only — excluded from Credit Counted & CGPA.
    """
    # Auto-detect waivers from WV grade rows in the transcript
    _transcript_wv: Set[str] = set()
    if transcript_rows:
        for _r in transcript_rows:
            if _r.get("grade") == "WV" and _r.get("course_code") in WAIVERABLE_COURSES:
                _transcript_wv.add(_r["course_code"])

    waived_courses: Set[str] = set()
    waiver_notes:   list[str] = []

    print()
    print(_btop())
    print(_bline("WAIVER CHECK"))
    print(_bline("Waived courses count toward Credit Completed only (not Credit Counted or CGPA)."))
    print(_bsep())
    print(_bline(""))

    if "ENG102" in _transcript_wv:
        waived_courses.add("ENG102")
        print(_bline("  → ENG102 waived (detected from transcript)."))
    elif _prompt_yes_no("Is ENG102 waived for this student?"):
        waived_courses.add("ENG102")
        print(_bline("  → ENG102 waived."))
    else:
        print(_bline("  → ENG102 not waived (grade will count in Credit Counted and CGPA)."))

    if "MAT112" in _transcript_wv:
        waived_courses.add("MAT112")
        print(_bline("  → MAT112 waived (detected from transcript)."))
    elif _prompt_yes_no("Is MAT112 waived for this student?"):
        waived_courses.add("MAT112")
        print(_bline("  → MAT112 waived."))
    else:
        print(_bline("  → MAT112 not waived (grade will count in Credit Counted and CGPA)."))

    num_waivers      = len(waived_courses)
    required_credits = get_required_credits_for_waivers(program_key, num_waivers)
    print(_bline(f"  Required credits for {program_key}: {required_credits}  "
                 f"({num_waivers} waiver(s) applied)"))
    print(_bbot())
    if waived_courses:
        waiver_notes.append(
            f"{', '.join(sorted(waived_courses))} waived — counted in Credit Completed only."
        )
    print()
    return allowed_codes, required_credits, waived_courses, waiver_notes

# ══════════════════════════════════════════════════════════════════════════════
#  CGPA computation
# ══════════════════════════════════════════════════════════════════════════════
def compute_cgpa(
    rows: list[dict],
    allowed_codes: Optional[Set[str]],
    program_key: str,
    program_credits:  Optional[dict[str,dict[str,float]]] = None,
    waived_courses:   Optional[Set[str]] = None,
    prereq_failures:  Optional[dict[str,str]] = None,
) -> tuple[float,float,float,dict[str,tuple[str,float,float]]]:
    """
    Compute weighted CGPA per NSU rules (verified against live NSU transcript PDF):

      CGPA = Σ (Credit_Counted_i × GradePoint_i) / Σ Credit_Counted_i

      • Only courses in the program curriculum (allowed_codes) count.
      • NCL (0-credit) labs and explicitly excluded courses (MAT116 for CSE) are skipped.
      • W and I are excluded from both numerator and denominator.
      • F contributes 0 grade points; its credits still enter the denominator.
      • Retakes: ONLY the best attempt counts — superseded attempts are fully
        discarded from both numerator and denominator (denominator = Credit Counted,
        not inflated by retake history). Evidence: 501.7 GP ÷ 130.0 Cr = 3.86 CGPA.
      • Prereq-failed courses are excluded — a passed course whose prerequisite
        was not satisfied must not inflate CGPA (mirrors credit tally behaviour).
      • Denominator = Credit Counted (one entry per course, best or F attempt only).
    Returns: (cgpa, total_grade_points, credit_counted_denom, per_course_dict)
    """
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"],[]).append(r)

    ncl          = get_ncl_labs(program_key)
    cgpa_excl    = CGPA_EXCLUDED_BY_PROGRAM.get(program_key, set())
    # FIX #11: always normalise waived_courses before any comparison
    _waived_n      = {normalize_course_code(c) for c in (waived_courses or set())}
    # Prereq-failed courses: must be excluded from CGPA, not just credit tally.
    # Without this, a passed course taken without its prereq inflates CGPA.
    _prereq_fail_n = {normalize_course_code(c) for c in (prereq_failures or {}).keys()}

    total_pts    = 0.0
    total_cr     = 0.0
    per_course_cgpa: dict[str,tuple[str,float,float]] = {}

    for code, attempts in by_course.items():
        n = normalize_course_code(code)

        if allowed_codes is not None and n not in allowed_codes: continue
        if n in _waived_n:      continue  # waived: Credit Completed only, not CGPA
        if n in ncl or n in cgpa_excl: continue
        if n in _prereq_fail_n: continue  # prereq not met: exclude from CGPA

        cgpa_att = [a for a in attempts if a["grade"] not in ("W","I")]
        if not cgpa_att: continue

        def _eff_cr(attempt: dict) -> float:
            if program_credits and program_key and n in program_credits.get(program_key,{}):
                return program_credits[program_key][n]
            # FIX #17 (cgpa): mirror cap from compute_total_valid_credits — non-program
            # NSU courses are capped at 3.0; transcript value is not authoritative.
            return min(attempt["credits"], 3.0)

        passing = [a for a in cgpa_att if is_passing(a["grade"])]
        if passing:
            best      = max(passing, key=lambda a: GRADE_RANK.get(a["grade"],0))
            grade     = best["grade"]
            credits   = _eff_cr(best)
            # Superseded retake attempts are fully discarded — they do not
            # enter the denominator.  Denominator = Credit Counted (one row
            # per course, best attempt only).  Proven by PDF: 501.7 / 130.0 = 3.86.
        else:
            # All remaining are F — use most recent
            f_att  = cgpa_att[-1]
            grade  = "F"
            credits= _eff_cr(f_att)

        if credits <= 0: continue

        gp = GRADE_POINTS.get(grade, 0.0)
        total_pts += gp * credits
        total_cr  += credits
        per_course_cgpa[code] = (grade, credits, gp)

    # NSU policy: denominator = Credit Counted (best attempt per course only)
    denom = total_cr
    cgpa  = float(Decimal(str(total_pts / denom)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if denom > 0 else 0.0

    return cgpa, total_pts, denom, per_course_cgpa

# ══════════════════════════════════════════════════════════════════════════════
#  L2 print_report (enhanced with CGPA section)
# ══════════════════════════════════════════════════════════════════════════════
def print_report(
    transcript_path: Path,
    program_name:    str,
    total:           float,
    per_course:      dict[str,float],
    by_course:       dict[str,list[dict]],
    required_credits: Optional[int],
    cgpa:            float,
    total_gp:        float,
    total_cr_attempted: float,
    per_course_cgpa: dict[str,tuple[str,float,float]],
    waiver_notes:    list[str],
    allowed_codes:   Optional[Set[str]] = None,
    program_credits: Optional[dict[str,dict[str,float]]] = None,
    program_key:     Optional[str] = None,
    major_electives: Optional[list[str]] = None,
    open_elective:   str = "",
    free_electives:  Optional[list[str]] = None,
    core_excluded:   Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waived_courses:  Optional[Set[str]] = None,
    prereq_failures: Optional[dict[str,str]] = None,
    report_level:    int = 2,   # FIX #9: L3 passes 3 to avoid "LEVEL 2" header confusion
) -> None:
    major_set = {normalize_course_code(c) for c in (major_electives or [])}
    free_set  = {normalize_course_code(c) for c in (free_electives or [])}
    open_code = normalize_course_code(open_elective) if open_elective else ""
    ncl       = get_ncl_labs(program_key)
    _waived   = waived_courses or set()
    _waived_n = {normalize_course_code(c) for c in _waived}
    credit_completed = total + WAIVER_CREDITS_EACH * len(_waived)
    class_eq  = get_class_equivalence(cgpa)

    # Credit Passed: all courses with passing grades A–D.
    # Includes 0-graduation-credit courses the student still had to pass (e.g. MAT116 for CSE),
    # using the transcript credit value for those courses since the 0 is a graduation rule,
    # not a reflection of actual course weight.
    _cgpa_excl = CGPA_EXCLUDED_BY_PROGRAM.get(program_key, set())
    _zero_passed_extra = 0.0
    for _n in _cgpa_excl:
        _attempts = by_course.get(_n, [])
        if not has_passing_attempt(_attempts):
            continue
        _passing = [a for a in _attempts if is_passing(a["grade"])]
        _best    = max(_passing, key=lambda a: GRADE_RANK.get(a["grade"], 0))
        _zero_passed_extra += _best["credits"]
    credit_passed = total + _zero_passed_extra

    # ── Banner ────────────────────────────────────────────────────────────────
    title = f"LEVEL {report_level} ▸ CGPA & CREDIT TALLY REPORT"
    print()
    print(_btop())
    print(_bline(title))
    print(_bsep())
    print(_bline(f"Transcript  :  {transcript_path.name}"))
    print(_bline(f"Program     :  {program_name}"))
    for note in waiver_notes:
        print(_bline(f"Waiver      :  {note}"))
    print(_bsep())
    credit_ok = credit_completed >= (required_credits or 0)
    cgpa_ok   = cgpa >= 2.0
    if required_credits is not None:
        cr_flag  = "✓ MET" if credit_ok else "✗ NOT MET"
        print(_bline(f"CREDIT PASSED     :  {credit_passed:.1f}   (passing grades A–D; counts toward graduation)"))
        print(_bline(f"CREDIT COUNTED    :  {total_cr_attempted:.1f}   (A–F grades in curriculum; CGPA denominator)"))
        print(_bline(f"CREDIT COMPLETED  :  {credit_completed:.1f} / {required_credits} required   [{cr_flag}]"))
    else:
        print(_bline(f"CREDIT PASSED     :  {credit_passed:.1f}   (passing grades A–D; counts toward graduation)"))
        print(_bline(f"CREDIT COUNTED    :  {total_cr_attempted:.1f}   (A–F grades in curriculum; CGPA denominator)"))
        print(_bline(f"CREDIT COMPLETED  :  {credit_completed:.1f}"))
    cgpa_flag = "✓ MET (≥ 2.0)" if cgpa_ok else "✗ PROBATION — below 2.0 minimum"
    print(_bline(f"CGPA              :  {cgpa:.2f}   [{class_eq}]   [{cgpa_flag}]"))
    print(_bline(f"Grade Points      :  {total_gp:.2f}  ÷  {total_cr_attempted:.1f} Credit Counted"))
    print(_bbot())
    print()

    # ── Credit tally table ────────────────────────────────────────────────────
    def _status(code: str) -> str:
        n = normalize_course_code(code)
        if n == open_code:
            return "Counted  [Free Elective]" if program_key=="MIC" else "Counted  [Open Elective]"
        if n in free_set:  return "Counted  [Free Elective]"
        if n in major_set: return "Counted  [Major Elective]"
        return "Counted"

    counted  = [(c,cr) for c,cr in sorted(per_course.items()) if cr>0  and normalize_course_code(c) not in ncl]
    excluded = [(c,cr) for c,cr in sorted(per_course.items()) if cr==0 and normalize_course_code(c) not in ncl]

    # Retake ghosts: individual non-counting attempts for courses that ARE counted.
    # Covers F/W/I attempts before a passing retake, and lower-grade passing
    # attempts superseded by a better grade.  Each surfaces as its own row so
    # the admin can see the full attempt history without digging into raw CSV.
    _retake_ghosts: list[tuple[str,str,str]] = []  # (code, attempt_grade, reason)
    for code in sorted(per_course):
        n = normalize_course_code(code)
        if per_course[code] == 0 or n in ncl:
            continue  # already in excluded, or NCL — never displayed
        attempts = by_course.get(code, [])
        if len(attempts) <= 1:
            continue  # single attempt — nothing to surface
        passing = [a for a in attempts if is_passing(a["grade"])]
        best    = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0)) if passing else None
        best_gr = best["grade"] if best else "—"
        for a in attempts:
            if a is best:
                continue
            if is_passing(a["grade"]):
                _retake_ghosts.append((code, a["grade"],
                    f"superseded by retake — {best_gr} counts"))
            else:
                _label = {"F": "failure (F)", "W": "withdrawal (W)",
                          "I": "incomplete (I)"}.get(a["grade"], f"grade {a['grade']}")
                _retake_ghosts.append((code, a["grade"],
                    f"{_label} — passed on retake ({best_gr})"))

    print("  Courses counted toward graduation:")
    print(_TTOP); print(_THDR); print(_TROW_SEP)
    for code, cr in counted:
        grade = get_display_grade(by_course[code])
        print(_trow(code, cr, grade, _status(code)))
    print(_TBOT)
    print()

    if excluded or _retake_ghosts:
        print("  Courses not counted (0 credits):")
        print(_TTOP); print(_THDR); print(_TROW_SEP)
        _nc_rows: list[tuple[str,str,str]] = []
        for code, _ in excluded:
            grade  = get_display_grade(by_course[code])
            reason = reason_not_counted(
                by_course[code], course_code=code, program_name=program_name,
                allowed_codes=allowed_codes, program_credits=program_credits,
                program_key=program_key, core_excluded=core_excluded,
                unselected_electives=unselected_electives, waived_courses=waived_courses,
                prereq_failure=(prereq_failures or {}).get(normalize_course_code(code)),
            )
            _nc_rows.append((code, grade, reason))
        for code, grade, reason in _retake_ghosts:
            _nc_rows.append((code, grade, reason))
        for code, grade, reason in sorted(_nc_rows, key=lambda x: x[0]):
            print(_trow(code, "—", grade, reason))
        print(_TBOT)
        print()


    print(_btop())
    print(_bline(f"Credit Passed                :  {credit_passed:.1f}   (passing grades A–D; toward graduation)"))
    print(_bline(f"Credit Counted               :  {total_cr_attempted:.1f}   (A–F grades; CGPA denominator — includes F where applicable)"))
    print(_bline(f"Total Grade Points           :  {total_gp:.2f}"))
    print(_bline(f"CGPA                         :  {cgpa:.2f}   ({class_eq})"))
    standing = ("⚠  PROBATION — CGPA is below the 2.0 minimum required for graduation"
                if cgpa < 2.0 else class_eq)
    print(_bline(f"Academic Standing            :  {standing}"))
    print(_bbot())
    print()

# ══════════════════════════════════════════════════════════════════════════════
#  Shared audit runner (used by L3 as well)
# ══════════════════════════════════════════════════════════════════════════════
def run_audit(args) -> dict:
    """
    Run the full L2 audit (waivers → choices → electives → credit tally → CGPA).
    Returns a result dict that L3 can feed into compute_deficiencies() and print_report().
    """
    if not args.transcript.exists():
        raise FileNotFoundError(f"Transcript not found: {args.transcript}")

    program_key       = (args.program_name or "").strip().upper()
    # FIX #6: validate program (guard also in main(), but guard here for library use)
    if program_key not in ("CSE","MIC"):
        raise ValueError(f"Unsupported program '{args.program_name}'. Supported: CSE, MIC")

    program_codes, program_credits = load_program_courses(args.program_knowledge)
    allowed_codes     = set(program_codes.get(program_key, set()))
    credits_by_program = program_credits

    if program_key == "MIC":
        _mic_core_all    = set().union(*MIC_REQUIRED_CATEGORIES.values())
        _purely_elective = set(MIC_ELECTIVES) - _mic_core_all
        allowed_codes    = allowed_codes - _purely_elective

    allowed_codes, required_credits, waived_courses, waiver_notes = handle_waivers(
        program_key, allowed_codes,
        transcript_rows=load_transcript(args.transcript),
    )

    rows = load_transcript(args.transcript)

    # Grade anomaly check: warn immediately after loading — before any computation
    grade_anomalies = detect_grade_anomalies(rows)
    print_grade_anomaly_warning(grade_anomalies)

    core_excluded: Set[str] = set()
    if program_key == "MIC":
        core_excluded = select_mic_core_choices(rows)
        alias_excl    = resolve_mic_aliases(rows)
        if alias_excl:
            print("\n  SHLS Core alias resolution (equivalent course pairs):")
            for excl, kept in alias_excl.items():
                print(f"    {excl} excluded — {kept} already satisfies this slot.")
            print()
        core_excluded = core_excluded | set(alias_excl.keys())
        allowed_codes = allowed_codes - core_excluded

    if program_key == "CSE":
        cse_excl = resolve_cse_choice_groups(rows)
        if cse_excl:
            print("\n  CSE GED choice resolution (one course per slot):")
            for c in sorted(cse_excl):
                print(f"    {c} excluded — choice slot filled by another course from the same group.")
            print()
        core_excluded = core_excluded | cse_excl
        allowed_codes = allowed_codes - cse_excl
        bio_intern_excl = resolve_cse_bio_internship_choice(rows)
        core_excluded = core_excluded | bio_intern_excl
        allowed_codes = allowed_codes - bio_intern_excl

    all_elective_candidates: Set[str] = (
        {c for trail in CSE_TRAILS.values() for c in trail} if program_key=="CSE"
        else set(MIC_ELECTIVES)
    )

    major_electives, open_elective, free_electives, trail_alias_excl, selected_minor_courses = select_electives(
        program_key, rows, allowed_codes=allowed_codes, waived_courses=waived_courses,
        core_excluded=core_excluded, program_credits=credits_by_program)
    all_selected = set(major_electives)|set(free_electives)|({open_elective} if open_elective else set())
    unselected_electives = all_elective_candidates - all_selected
    # FIX: also subtract unselected_electives — trail courses not chosen must not count toward credits
    allowed_codes = (allowed_codes | all_selected) - trail_alias_excl - unselected_electives
    # FIX #18: subtract minor courses that were neither declared nor chosen as open elective
    if program_key == "CSE":
        open_n_str = normalize_course_code(open_elective) if open_elective else ""
        minor_unused = CSE_MINOR_COURSES - selected_minor_courses - ({open_n_str} if open_n_str else set())
        allowed_codes -= minor_unused

    # Credit mismatch check: warn if transcript credits differ from program.md
    credit_mismatches = detect_credit_mismatches(
        rows, credits_by_program, program_key, allowed_codes=allowed_codes)
    print_credit_mismatch_warning(credit_mismatches)

    # FIX #19: merge both prereq maps so cross-program electives (e.g. MIC412/413 selected as
    # a CSE open elective) are validated against their own program's prereq chain.
    # Own-program entries take precedence on any key collision.
    _other_prereqs = MIC_PREREQS if program_key == "CSE" else CSE_PREREQS
    _own_prereqs   = CSE_PREREQS if program_key == "CSE" else MIC_PREREQS
    prereq_map = {**_other_prereqs, **_own_prereqs}
    passed_set = build_passed_set(rows, prereq_map=prereq_map, waived_courses=waived_courses)
    baseline   = compute_baseline_credits(rows, allowed_codes, credits_by_program, program_key)

    total, per_course, by_course, prereq_failures = compute_total_valid_credits(
        rows, allowed_codes=allowed_codes, program_credits=credits_by_program,
        program_key=program_key, prereq_map=prereq_map, passed_set=passed_set,
        waived_courses=waived_courses, earned_credits=baseline,
    )

    # Print elective summary AFTER prereq computation so it can warn about blocked selections
    print_elective_summary(major_electives, open_elective, program_key,
                           free_electives=free_electives, rows=rows,
                           prereq_failures=prereq_failures,
                           selected_minor_courses=selected_minor_courses)

    cgpa, total_gp, total_cr_attempted, per_course_cgpa = compute_cgpa(
        rows, allowed_codes=allowed_codes, program_key=program_key,
        program_credits=credits_by_program, waived_courses=waived_courses,
        prereq_failures=prereq_failures,
    )

    credit_completed = total + WAIVER_CREDITS_EACH * len(waived_courses)

    return {
        "transcript_path":    args.transcript,
        "program_name":       args.program_name,
        "total":              total,
        "per_course":         per_course,
        "by_course":          by_course,
        "required_credits":   required_credits,
        "cgpa":               cgpa,
        "total_gp":           total_gp,
        "total_cr_attempted": total_cr_attempted,
        "per_course_cgpa":    per_course_cgpa,
        "waiver_notes":       waiver_notes,
        "allowed_codes":      allowed_codes,
        "program_credits":    credits_by_program,
        "program_key":        program_key,
        "major_electives":    major_electives,
        "open_elective":      open_elective,
        "free_electives":     free_electives,
        "core_excluded":      core_excluded,
        "unselected_electives": unselected_electives,
        "waived_courses":     waived_courses,
        "prereq_failures":    prereq_failures,
        "passed_set":         passed_set,
        "credit_completed":   credit_completed,
        "selected_minor_courses": selected_minor_courses,
        "rows":               rows,
        "program_codes":      program_codes,
    }

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Level 2: CGPA Engine & Waiver Handler."
    )
    parser.add_argument("transcript",        type=Path)
    parser.add_argument("program_name",      type=str)
    parser.add_argument("program_knowledge", type=Path)
    parser.add_argument("--no-interact",     action="store_true",
                        help="Non-interactive: auto-select best options (AI agent / pipeline mode)")
    args = parser.parse_args()

    # Propagate the flag into the shared module
    _l1.NO_INTERACT = args.no_interact

    # FIX #6: validate program early
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
        report_level=2,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())