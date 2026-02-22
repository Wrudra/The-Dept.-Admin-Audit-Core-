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

# ── NSU Offered Course Catalog ──────────────────────────────────────────────
# Only courses in this set are eligible as open/free electives.
# Source: NSU Offered Course List (Spring 2026), scraped from the RDS portal.
# Cross-listed courses (e.g. CSE311/ETE335) are included under each code.
NSU_CATALOG: Set[str] = {
    "ACT201","ACT202","ACT310","ACT320","ACT360","ACT370","ACT380","ACT410","ACT430","ACT460",
    "AMCS501","AMCS504","AMCS506","AMCS507","AMCS510/MAT483","ANT101","ARC111","ARC112","ARC121","ARC122",
    "ARC123","ARC131","ARC133","ARC200","ARC213","ARC214","ARC215","ARC241","ARC242","ARC251",
    "ARC261","ARC262","ARC263","ARC264","ARC271","ARC272","ARC273","ARC281","ARC282","ARC283",
    "ARC310","ARC316","ARC317","ARC318","ARC324","ARC334","ARC343","ARC344","ARC348","ARC384",
    "ARC410","ARC418","ARC419","ARC437","ARC445","ARC453","ARC454","ARC456","ARC474","ARC492",
    "ARC500","ARC519","ARC535","ARC576","ARC596","ARC598","BBT203","BBT221","BBT230","BBT312",
    "BBT312L","BBT314","BBT314L","BBT315","BBT316","BBT316L","BBT317","BBT318","BBT335","BBT413",
    "BBT413L","BBT415","BBT415L","BBT416/MIC311","BBT417","BBT418","BBT419","BBT421","BBT423","BBT424",
    "BBT425","BBT427","BBT601","BBT608/BBT609","BBT615/BBT616","BBT623","BBT631","BBT638/BBT639","BBT645","BBT671",
    "BBT685","BBT695","BBT792","BEN205","BIO103","BIO103L","BIO201","BIO201L","BIO202","BIO202L",
    "BSC201","BUS112","BUS135","BUS172","BUS173","BUS251","BUS498","BUS499","BUS500/EMB500","BUS501",
    "BUS505","BUS511","BUS516","BUS518","BUS520","BUS525","BUS530","BUS535","BUS601","BUS620",
    "BUS635","BUS650","BUS685","BUS690","BUS698","BUS699","BUS700","CE6101","CE6303","CE6603",
    "CEE100","CEE209","CEE210","CEE211","CEE212","CEE213","CEE214","CEE250","CEE260","CEE310",
    "CEE330","CEE331","CEE335","CEE335L","CEE340","CEE350","CEE360","CEE370","CEE373","CEE415",
    "CEE430","CEE431","CEE460","CEE470","CEE474","CHE101","CHE101L","CHE201","CHE202","CHE202L",
    "CHE203","CHE203L","CHN101","CHN201","CSE101","CSE115","CSE115L","CSE145","CSE173","CSE215",
    "CSE215L","CSE225","CSE225L","CSE226","CSE231","CSE231L","CSE273","CSE311/ETE335","CSE311L/ETE335L","CSE323",
    "CSE325/CSE425","CSE327","CSE331/EEE332/EEE453/ETE332","CSE331L/EEE332L/EEE453L/ETE332L","CSE332/EEE336","CSE332L/EEE336L","CSE338/CSE438","CSE338/CSE438/EEE331/ETE331","CSE338L/CSE438L","CSE338L/CSE438L/EEE331L/ETE331L",
    "CSE373","CSE411","CSE413L/EEE413L/ETE419L","CSE435/EEE411/ETE412","CSE435L/EEE411L/ETE412L","CSE440/EEE333/ETE333","CSE445","CSE465","CSE468","CSE482/ETE334",
    "CSE482L/ETE334L","CSE495A","CSE495B","CSE532/EEE560","CSE534","CSE562","CSE583","CSE597/EEE597/ETE597","DEV503","DEV564",
    "DEV565","DEV577","DEV595","DEV596","ECO101","ECO103","ECO104","ECO134","ECO135","ECO172",
    "ECO173","ECO201","ECO204","ECO245","ECO301","ECO304","ECO309","ECO317","ECO348","ECO372",
    "ECO406","ECO415","ECO486","ECO490","ECO492","ECO496","ECO503","ECO504","ECO514","ECO614",
    "ECO695","ECO699","EEE111/ETE111","EEE111L/ETE111L","EEE141/ETE141","EEE141L/ETE141L","EEE211/ETE211","EEE211L/ETE211L","EEE221/ETE221","EEE221L/ETE221L",
    "EEE241/ETE241","EEE241L/ETE241L","EEE311/ETE311","EEE311L/ETE311L","EEE312/ETE312","EEE312L/ETE312L","EEE313/EEE410/ETE411/ETE443","EEE321/ETE321","EEE321L","EEE321L/ETE321L",
    "EEE342/ETE418","EEE342L/ETE418L","EEE361/ETE361","EEE362","EEE362L","EEE363","EEE363L","EEE452","EEE461","EEE462",
    "EEE464","EEE465","EEE528","EEE542","EEE551","EMB500","EMB501","EMB502","EMB510","EMB520",
    "EMB601","EMB602","EMB620","EMB650","EMB660","EMB670","EMB690","EMPG500","EMPG515","EMPG520",
    "EMPG530","EMPG565","EMPG570","EMPH601","EMPH605","EMPH609","EMPH611","EMPH631","EMPH642","EMPH644",
    "EMPH653","EMPH663","EMPH671","EMPH672","EMPH681","EMPH704","EMPH706","EMPH711","EMPH712","EMPH713",
    "EMPH742","EMPH745","EMPH771","EMPH781","EMPH805","EMPH806","EMPH842","ENG102","ENG103","ENG105",
    "ENG111","ENG115","ENG210","ENG216","ENG220","ENG230","ENG260","ENG302","ENG307","ENG312",
    "ENG334/ENG461","ENG337/ENG466","ENG341","ENG346","ENG351","ENG361","ENG377","ENG381","ENG401","ENG417",
    "ENG431","ENG441","ENG446","ENG481","ENG501","ENG511","ENG513","ENG519","ENG520","ENG522",
    "ENG524","ENG553","ENG555","ENG558","ENG560","ENG570","ENG572","ENG574","ENG576","ENG580",
    "ENG581","ENG602","ENG605","ENG606","ENG611","ENG613","ENG618","ENG631","ENG632","ENG636",
    "ENG637","ENV102","ENV107","ENV107L","ENV172","ENV203/GEO205","ENV204","ENV205","ENV206","ENV207",
    "ENV208","ENV209","ENV214","ENV215","ENV260","ENV303","ENV307","ENV311","ENV316","ENV318",
    "ENV373","ENV402","ENV405","ENV414","ENV419","ENV430","ENV432","ENV455","ENV498","ENV499",
    "ENV501","ENV502","ENV602","ENV624","ENV627","ENV635","ENV652","ENV685","ENV697","ETH201",
    "FIN254","FIN410","FIN433","FIN435","FIN440","FIN444","FIN455","FIN464","FIN480","FIN635",
    "FIN637","FIN639","FIN642","FIN643","FIN644","FIN645","HAS501","HAS503","HAS505","HAS506",
    "HAS508","HAS515","HIS101","HIS102","HIS103","HIS205","HRM340","HRM360","HRM370","HRM380",
    "HRM450","HRM470","HRM602","HRM604","HRM610","HRM645","HRM650","HRM660","INB350","INB372",
    "INB400","INB410","INB415","INB480","INB490","LAW101","LAW107","LAW200","LAW201","LAW211",
    "LAW213","LAW301","LAW303","LAW305","LAW306","LAW313","LAW314","LAW405","LAW415","LAW416/LLB208",
    "LAW417","LAW418","LAW419","LAW420","LAW421","LAW423","LAW424","LAW426","LAW427/LLB206","LBA104",
    "LLB101","LLB102","LLB103","LLB104","LLB201","LLB202","LLB203","LLB205","LLM501","LLM506",
    "LLM509","LLM511","LLM513","LLM514","LLM515","LLM516","LLM517","LLM520","LLM523","LLM525",
    "LLM528","MAT112","MAT116","MAT120","MAT125","MAT130","MAT250","MAT350","MAT361","MAT480","MCJ101",
    "MCJ102","MCJ103","MCJ104","MCJ104L","MCJ201","MCJ202","MCJ203","MCJ203L","MCJ204","MCJ205",
    "MCJ302","MCJ303","MCJ305","MCJ305L","MCJ401","MCJ401L","MCJ403","MCJ403L","MGT212","MGT314",
    "MGT321","MGT330","MGT351","MGT360","MGT368","MGT460","MGT470/MIS410","MGT489","MGT490","MGT610",
    "MGT656","MGT680/SCM601","MIC201","MIC202","MIC203","MIC206","MIC207","MIC307","MIC309","MIC314",
    "MIC315","MIC315L","MIC316","MIC316L","MIC317","MIC317L","MIC318","MIC401","MIC404","MIC412",
    "MIC413","MIC413L","MIC414","MIC414L","MIC415","MIC415L","MIS107","MIS207","MIS210","MIS310",
    "MIS320","MIS470","MIS653","MIS654","MIS661","MKT202","MKT330","MKT337","MKT344","MKT355",
    "MKT382","MKT412","MKT417","MKT450","MKT460","MKT465","MKT470","MKT475","MKT621","MKT623",
    "MKT624","MKT625","MKT627","MKT628","MKT630","MKT633","MKT634","MKT635","MKT636","PAD201",
    "PBH101","PBH101L","PBH602","PBH605","PBH609","PBH611","PBH631","PBH642","PBH644","PBH653",
    "PBH663","PBH671","PBH672","PBH681","PBH701","PBH704","PBH706","PBH711","PBH712","PBH713",
    "PBH714","PBH742","PBH745","PBH761","PBH771","PBH781","PBH782","PBH805","PBH806","PBH842",
    # Capstone / internship courses (CSE)
    "CSE299","CSE499A","CSE499B","CSE498R","CSE498I",
    # School Core — EEE154 (1-credit theory)
    "EEE154",
    # MIC alias codes (SHLS Core equivalent pairs)
    "MIC101","MIC101L","MIC110","MIC110L",
    # MIC electives not previously listed
    "MIC416","MIC417","MIC418","MIC498",
    # Minor in Math additional courses
    "MAT370","MAT485",
    # Minor in Physics courses
    "PHY230","PHY240","PHY250","PHY260",
    "PHI101","PHI104","PHI401","PHR110","PHR112","PHR113","PHR114","PHR114L","PHR120","PHR120L",
    "PHR121","PHR122","PHR122L","PHR123","PHR124","PHR124L","PHR210","PHR210L","PHR211","PHR211L",
    "PHR212","PHR212L","PHR213","PHR214","PHR215","PHR215L","PHR221","PHR221L","PHR222","PHR222L",
    "PHR223","PHR223L","PHR224","PHR224L","PHR225","PHR226","PHR227","PHR300","PHR310","PHR310L",
    "PHR312","PHR312L","PHR313","PHR313L","PHR314","PHR314L","PHR322","PHR322L","PHR324","PHR325",
    "PHR326","PHR327","PHR400","PHR410","PHR411","PHR411L","PHR415","PHR418","PHR424","PHR425",
    "PHR426","PHR427","PHR428","PHR431","PHR500","PHR5001","PHR5002","PHR5003","PHR5011","PHR5012",
    "PHR5013","PHR5015","PHR5021","PHR5023","PHR510","PHR5101","PHR5106","PHR5107","PHR5108","PHR511",
    "PHR5110","PHR5111","PHR5112","PHR5113","PHR512","PHR513","PHR514","PHR515","PHR516","PHR520",
    "PHR5201","PHR5208","PHR5209","PHR521","PHR522","PHY107","PHY107L","PHY108","PHY108L","POL101",
    "POL104","POL202","PPG555","PPG560","PSY101","PSY101L","SCM310","SCM320","SCM450","SCM603",
    "SCM605","SCM607","SCM608","SOC101","SOC103","SOC201","TNM201","WMS201",
}

# Expanded catalog: splits cross-listed entries ("CSE332L/EEE336L" -> "CSE332L", "EEE336L")
# so that any individual code lookup works correctly regardless of how the catalog stores it.
NSU_CATALOG_EXPANDED: Set[str] = {
    part.strip()
    for entry in NSU_CATALOG
    for part in entry.split("/")
}

# CSE Major Elective Trails (from program.md)
CSE_TRAILS: dict[str, list[str]] = {
    "Algorithms and Computation": ["CSE257", "CSE417", "CSE326", "CSE426", "CSE273", "CSE473"],
    "Software Engineering":       ["CSE411"],
    "Networks":                   ["CSE422", "CSE562", "CSE338", "CSE438", "CSE482", "CSE485", "CSE486"],
    "Computer Architecture and VLSI": ["CSE435", "CSE413", "CSE414"],
    "Artificial Intelligence":    ["CSE440", "CSE445", "CSE465", "CSE467", "CSE419", "CSE598"],
}

# MIC Elective courses (from program.md)
MIC_ELECTIVES: list[str] = ["MIC201", "MIC318", "MIC404", "MIC311", "MIC309", "MIC416", "MIC417", "MIC418"]

# ── Prerequisite Maps ───────────────────────────────────────────────────────
# Structure: dict[course_code, list[frozenset[str]]]
# Each frozenset is an OR-group — at least ONE option in the set must be passed.
# ALL frozensets in the list must be satisfied (AND relationship).
# Special tokens:
#   "WAIVER_ENG102" → satisfied when ENG102 is in waived_courses
#   "CREDITS_60"    → satisfied when earned_credits >= 60
#   "CREDITS_100"   → satisfied when earned_credits >= 100

CSE_PREREQS: dict[str, list] = {
    # GED / University Core
    "ENG103":  [frozenset({"ENG102", "WAIVER_ENG102"})],
    "ENG111":  [frozenset({"ENG103"})],
    "BEN205":  [frozenset({"ENG103"})],
    # School Core — MAT chain
    "MAT120":  [frozenset({"MAT116"})],
    "MAT125":  [frozenset({"MAT116"})],
    "MAT130":  [frozenset({"MAT120"})],
    "MAT250":  [frozenset({"MAT130"})],
    "MAT350":  [frozenset({"MAT250"})],
    "MAT361":  [frozenset({"MAT250"})],
    # School Core — PHY / CHE
    "PHY107":  [frozenset({"MAT120"})],
    "PHY108":  [frozenset({"MAT130"}), frozenset({"PHY107"})],
    "CHE101":  [frozenset({"MAT350"})],
    # CSE Core
    "CSE173":  [frozenset({"CSE115"})],
    "CSE215":  [frozenset({"CSE173"})],
    "CSE215L": [frozenset({"CSE173"})],
    "CSE225":  [frozenset({"CSE215"})],
    "CSE225L": [frozenset({"CSE215"})],
    "CSE231":  [frozenset({"CSE173"})],
    "CSE231L": [frozenset({"CSE173"})],
    "EEE141":  [frozenset({"PHY107"}), frozenset({"MAT120"})],
    "EEE141L": [frozenset({"PHY107"}), frozenset({"MAT120"})],
    "EEE111":  [frozenset({"EEE141"})],
    "EEE111L": [frozenset({"EEE141"})],
    "CSE311":  [frozenset({"CSE225"})],
    "CSE311L": [frozenset({"CSE225"})],
    "CSE332":  [frozenset({"CSE231"})],
    "CSE332L": [frozenset({"CSE231"})],
    "CSE323":  [frozenset({"CSE332"})],
    "CSE373":  [frozenset({"CSE225"}), frozenset({"MAT361"})],
    "CSE327":  [frozenset({"CSE311"})],
    "CSE331":  [frozenset({"CSE323"})],
    "CSE331L": [frozenset({"CSE323"})],
    "CSE425":  [frozenset({"CSE327"})],
    # Capstone — credit-threshold and sequential
    "CSE299":  [frozenset({"CREDITS_60"})],
    "CSE499A": [frozenset({"CREDITS_100"})],
    "CSE499B": [frozenset({"CSE499A"})],
}

MIC_PREREQS: dict[str, list] = {
    # University Core — Languages
    "ENG105":  [frozenset({"ENG103"})],
    "BEN205":  [frozenset({"ENG103"})],
    "ENG111":  [frozenset({"ENG103"})],
    # SHLS Core — CHE chain
    "CHE201":  [frozenset({"CHE101"})],
    "CHE202":  [frozenset({"CHE101"})],
    "CHE202L": [frozenset({"CHE101L"})],
    # SHLS Core — BIO chain (alias pairs: BIO201≡MIC110, BIO202≡MIC101)
    "BIO201":  [frozenset({"BIO103"})],
    "MIC110":  [frozenset({"BIO103"})],
    "BIO201L": [frozenset({"BIO103L"})],
    "MIC110L": [frozenset({"BIO103L"})],
    "BIO202":  [frozenset({"BIO103"})],
    "MIC101":  [frozenset({"BIO103"})],
    "BIO202L": [frozenset({"BIO103L"})],
    "MIC101L": [frozenset({"BIO103L"})],
    "MIC203":  [frozenset({"BIO103L"}), frozenset({"BIO202", "MIC101"})],
    "BBT203":  [frozenset({"BIO201", "MIC110"}), frozenset({"BUS172"})],
    # Major Core
    "MIC202":  [frozenset({"CHE101"}), frozenset({"BIO202", "MIC101"})],
    "MIC307":  [frozenset({"MIC203"}), frozenset({"CHE202"})],
    "MIC314":  [frozenset({"BIO201", "MIC110"}), frozenset({"MIC202"})],
    "MIC315":  [frozenset({"MIC203"}), frozenset({"MIC202"})],
    "MIC315L": [frozenset({"BIO202L", "MIC101L"}), frozenset({"MIC315"})],
    "MIC316":  [frozenset({"MIC307"})],
    "MIC316L": [frozenset({"MIC307"})],
    "MIC317":  [frozenset({"MIC307"}), frozenset({"MIC315"})],
    "MIC317L": [frozenset({"BIO202L", "MIC101L"}), frozenset({"MIC317"})],
    "MIC206":  [frozenset({"MIC316"})],
    "MIC207":  [frozenset({"MIC316"})],
    "MIC401":  [frozenset({"MIC316"}), frozenset({"MIC309"})],
    "MIC412":  [frozenset({"MIC315"}), frozenset({"MIC316"})],
    "MIC413":  [frozenset({"MIC316"}), frozenset({"MIC317"})],
    "MIC413L": [frozenset({"BIO202L", "MIC101L"}), frozenset({"MIC413"})],
    "MIC414":  [frozenset({"MIC202"}), frozenset({"MIC203"})],
    "MIC414L": [frozenset({"BIO202L", "MIC101L"}), frozenset({"MIC414"})],
    "MIC415":  [frozenset({"MIC202"}), frozenset({"MIC203"})],
    "MIC415L": [frozenset({"BIO202L", "MIC101L"}), frozenset({"MIC415"})],
    "MIC498":  [
        frozenset({"MIC316"}),
        frozenset({"MIC315L"}), frozenset({"MIC316L"}), frozenset({"MIC317L"}),
        frozenset({"MIC413L"}), frozenset({"MIC414L"}), frozenset({"MIC415L"}),
    ],
    # Electives
    "MIC201":  [frozenset({"BIO202", "MIC101"})],
    "MIC309":  [frozenset({"MIC203"}), frozenset({"MIC207"})],
    "MIC311":  [frozenset({"MIC316"})],
    "MIC318":  [frozenset({"MIC203"}), frozenset({"MIC201"})],
    "MIC404":  [frozenset({"MIC307"})],
    "MIC416":  [frozenset({"MIC316"})],
    "MIC417":  [frozenset({"MIC317"})],
    "MIC418":  [frozenset({"MIC416"})],
}


def build_passed_set(rows: list[dict]) -> Set[str]:
    """Return normalized course codes that have at least one passing grade on the transcript."""
    seen: dict[str, list[dict]] = {}
    for r in rows:
        seen.setdefault(normalize_course_code(r["course_code"]), []).append(r)
    return {code for code, attempts in seen.items() if has_passing_attempt(attempts)}


def prereq_satisfied(
    course: str,
    passed_set: Set[str],
    prereq_map: dict[str, list],
    waived_courses: Optional[Set[str]] = None,
    earned_credits: float = 0.0,
) -> tuple[bool, str]:
    """
    Check if every prerequisite AND-group for a course is satisfied.
    Returns (True, "") on success, (False, "reason string") on failure.

    Logic:
      - Each frozenset in the spec is an OR-group: ONE of its members must be in passed_set.
      - All frozensets must pass (AND across groups).
      - Special tokens: WAIVER_ENG102, CREDITS_60, CREDITS_100.
    """
    normalized = normalize_course_code(course)
    spec = prereq_map.get(normalized)
    if not spec:
        return True, ""

    _waived = {normalize_course_code(c) for c in (waived_courses or set())}
    missing_labels: list[str] = []

    for or_group in spec:
        # Credit-threshold tokens
        if "CREDITS_60" in or_group:
            if earned_credits >= 60:
                continue
            missing_labels.append(f"60 credits (have {earned_credits:.0f})")
            continue
        if "CREDITS_100" in or_group:
            if earned_credits >= 100:
                continue
            missing_labels.append(f"100 credits (have {earned_credits:.0f})")
            continue

        # Check if any option in the OR-group is satisfied
        group_satisfied = False
        for opt in or_group:
            opt_norm = normalize_course_code(opt)
            if opt_norm == "WAIVER_ENG102":
                if "ENG102" in _waived:
                    group_satisfied = True
                    break
            elif opt_norm in passed_set or opt_norm in _waived:
                group_satisfied = True
                break

        if not group_satisfied:
            real_opts = sorted(o for o in or_group if o != "WAIVER_ENG102")
            if len(real_opts) == 1:
                missing_labels.append(real_opts[0])
            else:
                missing_labels.append("(" + " or ".join(real_opts) + ")")

    if missing_labels:
        return False, "prereq not met: " + ", ".join(missing_labels)
    return True, ""


def compute_baseline_credits(
    rows: list[dict],
    allowed_codes: Optional[Set[str]],
    program_credits: Optional[dict[str, dict[str, float]]],
    program_key: Optional[str],
) -> float:
    """
    Quick credit tally excluding capstone courses, used to evaluate
    CREDITS_60 / CREDITS_100 prerequisite thresholds before the full audit.
    """
    CAPSTONE = {"CSE299", "CSE499A", "CSE499B"}
    ncl = get_ncl_labs(program_key)
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"], []).append(r)
    total = 0.0
    for code, attempts in by_course.items():
        normalized = normalize_course_code(code)
        if normalized in CAPSTONE or normalized in ncl:
            continue
        if allowed_codes is not None and normalized not in allowed_codes:
            continue
        if not has_passing_attempt(attempts):
            continue
        if program_credits and program_key and normalized in program_credits.get(program_key, {}):
            total += program_credits[program_key][normalized]
        else:
            total += valid_credits_for_course(attempts)
    return total

# MIC required course categories — used to flag courses already serving a requirement
MIC_REQUIRED_CATEGORIES: dict[str, set[str]] = {
    "University Core": {
        "ENG102", "ENG103", "ENG105",
        "BEN205", "ENG111",               # BEN205 / ENG111 choice slot
        "HIS101", "HIS103", "PHI101",
        "POL101", "POL104", "ECO101", "ECO104", "SOC101", "ANT101",
        "MIS107", "MAT116", "BUS172",
        "BIO103", "BIO103L", "PHY107", "PHY107L",
    },
    "SHLS Core": {
        "BBT203",
        "CHE101", "CHE101L", "CHE201", "CHE202", "CHE202L",
        "BIO201", "MIC110",               # theory equivalents (alias pair)
        "BIO201L", "MIC110L",             # lab equivalents (alias pair)
        "BIO202", "MIC101",               # theory equivalents (alias pair)
        "BIO202L", "MIC101L",             # lab equivalents (alias pair)
        "MIC203",
    },
    "Major Core": {
        "MIC202", "MIC206", "MIC207", "MIC307", "MIC314",
        "MIC315", "MIC315L", "MIC316", "MIC316L", "MIC317", "MIC317L",
        "MIC401", "MIC412", "MIC413", "MIC413L",
        "MIC414", "MIC414L", "MIC415", "MIC415L", "MIC498",
    },
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

# Base required credits when both ENG102 and MAT112 are waived (from program.md)
PROGRAM_BASE_CREDITS = {"CSE": 130, "MIC": 120}
# Waiverable courses (3 credits each); required = base + (2 - num_waivers) * 3
WAIVERABLE_COURSES = frozenset({"ENG102", "MAT112"})
WAIVER_CREDITS_EACH = 3
# CSE Internship/Research: 1 credit mandatory, not open elective (program.md)
CSE_INTERNSHIP_RESEARCH = frozenset({"CSE498R", "CSE498I"})


def get_required_credits_for_waivers(program_key: str, num_waivers: int) -> int:
    """Required credits based on waiver count (0, 1, or 2 for ENG102 and MAT112)."""
    base = PROGRAM_BASE_CREDITS.get(program_key)
    if base is None:
        return 130  # fallback
    return base + (2 - min(2, max(0, num_waivers))) * WAIVER_CREDITS_EACH

# MIC SHLS Core alias pairs: these course codes mean the SAME thing.
# Taking either one satisfies that requirement slot — only one should be counted.
MIC_ALIAS_PAIRS: list[tuple[str, str]] = [
    ("BIO201",  "MIC110"),    # Intro to Biochem & Biotech theory equivalents
    ("BIO201L", "MIC110L"),   # Intro to Biochem & Biotech lab equivalents
    ("BIO202",  "MIC101"),    # Basic Microbiology theory equivalents
    ("BIO202L", "MIC101L"),   # Basic Microbiology lab equivalents
]

# MIC University Core choice groups — student may have taken more than one;
# admin must select which single course (or course pair for Science) counts.
MIC_LANGUAGE_CHOICES: list[str] = ["BEN205", "ENG111"]  # one of these fills the 4th language slot
MIC_HUMANITIES_CHOICES: list[str] = ["HIS101", "HIS103", "PHI101"]
MIC_SOCIAL_CHOICES: list[str]     = ["POL101", "POL104", "ECO101", "ECO104", "SOC101", "ANT101"]
# Science is a paired choice: theory + lab together
MIC_SCIENCE_CHOICES: list[tuple[str, str]] = [
    ("BIO103", "BIO103L"),
    ("PHY107", "PHY107L"),
]


def get_required_credits(program_name: str) -> Optional[int]:
    """Return base required credits for the program (CSE 130, MIC 120)."""
    key = (program_name or "").strip().upper()
    return PROGRAM_BASE_CREDITS.get(key)


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
    # CSE 498R/498I: 1 credit mandatory (Internship/Research), not open elective
    codes["CSE"].update(CSE_INTERNSHIP_RESEARCH)
    for c in CSE_INTERNSHIP_RESEARCH:
        credits["CSE"][c] = 1.0
    # Waiverable courses: always 3 credits when not waived (program.md)
    for pkey in ("CSE", "MIC"):
        credits[pkey]["ENG102"] = 3.0
        credits[pkey]["MAT112"] = 3.0
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
            course_code = normalize_course_code((row.get(keys.get("course_code", "Course_Code")) or "").strip())
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
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    prereq_failure: Optional[str] = None,
) -> str:
    """Return a specific reason why this course contributes 0 credits."""
    if not attempts:
        return "no attempts on transcript"
    normalized = normalize_course_code(course_code) if course_code else ""
    if waived_courses and normalized in waived_courses:
        return "waived — counted in Credit Completed only (not in Credit Counted or CGPA)"
    if allowed_codes is not None and program_name and course_code:
        if normalized not in allowed_codes:
            if core_excluded and normalized in core_excluded:
                return "choice slot filled by another course"
            if unselected_electives and normalized in unselected_electives:
                return "elective not selected"
            if normalized not in NSU_CATALOG_EXPANDED:
                return "Not Provided by NSU"
            return f"not in {program_name} curriculum"
    # Prerequisite failure — course is in curriculum and passed, but prereq unmet
    if prereq_failure:
        return prereq_failure
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
    prereq_map: Optional[dict[str, list]] = None,
    passed_set: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    earned_credits: float = 0.0,
) -> tuple[float, dict[str, float], dict[str, list[dict]], dict[str, str]]:
    """Group by course_code, compute valid credits per course; apply prereq enforcement."""
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        code = r["course_code"]
        by_course.setdefault(code, []).append(r)

    per_course: dict[str, float] = {}
    prereq_failures: dict[str, str] = {}   # normalized code → failure reason

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
                continue
        # Program-specific credit override (e.g. MAT116: 0 for CSE, 3 for MIC)
        if program_credits and program_key and normalized in program_credits.get(program_key, {}):
            override = program_credits[program_key][normalized]
            if has_passing_attempt(attempts):
                raw_credits = override
            else:
                per_course[code] = 0.0
                continue
        # No passing grade → 0
        if raw_credits == 0 and not has_passing_attempt(attempts):
            per_course[code] = 0.0
            continue
        # ── Prerequisite check ───────────────────────────────────────────────
        if prereq_map and passed_set is not None and has_passing_attempt(attempts):
            ok, reason = prereq_satisfied(
                code, passed_set, prereq_map,
                waived_courses=waived_courses,
                earned_credits=earned_credits,
            )
            if not ok:
                per_course[code] = 0.0
                prereq_failures[normalized] = reason
                continue
        # ── Waived courses: count in Credit Completed only, not in Credit Counted ──
        if waived_courses and normalized in waived_courses:
            per_course[code] = 0.0
            continue
        # ─────────────────────────────────────────────────────────────────────
        per_course[code] = raw_credits

    return sum(per_course.values()), per_course, by_course, prereq_failures


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
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waiver_applied: bool = False,
    waived_courses: Optional[Set[str]] = None,
    prereq_failures: Optional[dict[str, str]] = None,
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
    _waived = waived_courses or set()
    credit_completed = total + WAIVER_CREDITS_EACH * len(_waived)
    if waiver_applied:
        print(f"  Waiver(s):    {', '.join(sorted(_waived))} — credits count in Credit Completed only.")
    print("-" * width)
    if required_credits is not None:
        print(f"  CREDIT COUNTED:   {total:.1f}  (courses with grades; used for CGPA)")
        print(f"  CREDIT COMPLETED: {credit_completed:.1f} / {required_credits}  (required for {program_name})")
    else:
        print(f"  CREDIT COUNTED:   {total:.1f}")
        print(f"  CREDIT COMPLETED: {credit_completed:.1f}")
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
                core_excluded=core_excluded,
                unselected_electives=unselected_electives,
                waived_courses=waived_courses,
                prereq_failure=(prereq_failures or {}).get(normalize_course_code(code)),
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


def select_electives_cse(
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
) -> tuple[list[str], str, list[str]]:
    """
    CSE elective selection driven by transcript.
    Returns (major_electives, open_elective, []).
    waived_courses: codes that were waived — excluded from open elective pool.
    """
    _waived = {normalize_course_code(c) for c in (waived_courses or set())}
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
    # Open elective pool preview — trail courses + courses outside CSE curriculum.
    # Waived courses and CSE 498R/498I (mandatory 1cr) are excluded.
    all_trail_codes = {c for trail in CSE_TRAILS.values() for c in trail}
    open_preview = sorted([
        c for c in taken
        if normalize_course_code(c) not in _waived
        and normalize_course_code(c) not in CSE_INTERNSHIP_RESEARCH
        and normalize_course_code(c) in NSU_CATALOG_EXPANDED  # must be a real NSU course
        and (c in all_trail_codes or c not in (allowed_codes or set()))
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
    # CSE 498R/498I are mandatory 1cr, not open elective.
    open_pool = sorted([
        c for c in taken
        if normalize_course_code(c) not in _waived
        and normalize_course_code(c) not in CSE_INTERNSHIP_RESEARCH
        and normalize_course_code(c) in NSU_CATALOG_EXPANDED  # must be a real NSU course
        and c not in set(major_electives)
        and (c in all_trail_codes or c not in (allowed_codes or set()))
    ])
    open_elective = ""
    if open_pool:
        print("\nSelect your OPEN ELECTIVE (outside CSE curriculum + unselected major electives):")
        open_elective = _prompt_pick("", open_pool, display=[_course_display(c, rows) for c in open_pool])
    else:
        print("  No outside-curriculum courses found in transcript for open elective.")

    return major_electives, open_elective, []


# CSE GED/University Core choice groups — student fills each slot with exactly ONE course
CSE_GED_CHOICE_GROUPS: list[list[str]] = [
    ["POL101", "POL104"],
    ["ECO101", "ECO104"],
    ["SOC101", "ENV203", "GEO205", "ANT101"],
]


def resolve_cse_choice_groups(rows: list[dict]) -> set[str]:
    """
    Auto-resolve CSE GED choice groups. Each group is a 'pick one' slot.
    If the student passed more than one course from the same group, keep the
    highest grade and silently exclude the rest. Ties are broken arbitrarily
    (max() with stable sort = first encountered in the group list wins).

    Returns: set of course codes to exclude from allowed_codes / credit tally.
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    excluded: set[str] = set()
    for group in CSE_GED_CHOICE_GROUPS:
        passed = [c for c in group if c in by_course and has_passing_attempt(by_course[c])]
        if len(passed) > 1:
            best = max(passed, key=lambda c: GRADE_RANK.get(get_display_grade(by_course[c]), 0))
            for c in passed:
                if c != best:
                    excluded.add(c)
    return excluded


def resolve_mic_aliases(rows: list[dict]) -> dict[str, str]:
    """
    For each MIC alias pair (e.g. BIO201 / MIC110), determine which code to exclude.

    Cases handled:
      - Both passed: exclude the lower-grade one (ties → keep A, exclude B).
      - One passed, other failed/withdrew: exclude the failed one so its F or W
        does not pollute the credit tally or CGPA.
      - Only one present: no exclusion needed.

    Returns: dict of  excluded_code -> kept_code  (may be empty).
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    exclusions: dict[str, str] = {}
    for code_a, code_b in MIC_ALIAS_PAIRS:
        a, b = normalize_course_code(code_a), normalize_course_code(code_b)
        present_a = a in by_course
        present_b = b in by_course
        pass_a = present_a and has_passing_attempt(by_course[a])
        pass_b = present_b and has_passing_attempt(by_course[b])

        if pass_a and pass_b:
            # Both passed — keep the better grade; ties favour A (default)
            grade_a = GRADE_RANK.get(get_display_grade(by_course[a]), 0)
            grade_b = GRADE_RANK.get(get_display_grade(by_course[b]), 0)
            if grade_b > grade_a:
                exclusions[a] = b
            else:
                exclusions[b] = a
        elif pass_a and present_b and not pass_b:
            # A passed, B only has F/W/I — exclude B so failures don't count
            exclusions[b] = a
        elif pass_b and present_a and not pass_a:
            # B passed, A only has F/W/I — exclude A
            exclusions[a] = b
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

    # --- Language 4th slot: BEN205 or ENG111 (choose one) ---
    lang_passed = passed_from(MIC_LANGUAGE_CHOICES)
    if len(lang_passed) > 1:
        print("\n  LANGUAGE (4th slot) — student passed both BEN205 and ENG111 (pick one to count):")
        chosen = _prompt_pick("", lang_passed, display=[_course_display(c, rows) for c in lang_passed])
        excluded.update(c for c in lang_passed if c != chosen)
        print(f"  ✓ Language slot: {chosen} counted.")
    elif len(lang_passed) == 1:
        print(f"\n  Language (4th slot): {lang_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Language (4th slot): no passing course found (BEN205 or ENG111 required).")

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


def select_electives_mic(rows: list[dict]) -> tuple[list[str], str, list[str]]:
    """
    MIC elective selection driven by transcript.
    Returns (major_electives, open_elective, free_extras) where major_electives has up to 3 courses.
    Free electives are treated as open electives (first one shown as open, rest in free_extras).
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
    free_available = [
        c for c in all_non_major
        if _mic_course_category(c) is None
        and normalize_course_code(c) in NSU_CATALOG_EXPANDED  # must be a real NSU course
    ]

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


def select_electives(
    program_key: str,
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
) -> tuple[list[str], str, list[str]]:
    """Dispatch elective selection by program. Returns (major_electives, open_elective, free_electives)."""
    if program_key == "CSE":
        return select_electives_cse(rows, allowed_codes=allowed_codes, waived_courses=waived_courses)
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
    # Copy so we don't mutate the shared program_codes set
    allowed_codes = set(program_codes.get(program_key)) if program_key in ("CSE", "MIC") else None
    credits_by_program = program_credits if program_key in ("CSE", "MIC") else None

    # --- Waiver Check (ENG102 and MAT112; each waived adds to Credit Completed only, not Credit Counted) ---
    waived_courses_waiverable: Set[str] = set()
    print("\n" + "=" * 56)
    print("  WAIVER CHECK")
    print("  (Waived courses count toward Credit Completed only; not in Credit Counted or CGPA)")
    print("=" * 56)
    if program_key in ("CSE", "MIC") and allowed_codes is not None:
        print("\n  Answer for each waiverable course:\n")
        eng_raw = input("    Is ENG102 waived for this student? (y/n): ").strip().lower()
        if eng_raw in ("y", "yes"):
            waived_courses_waiverable.add("ENG102")
            print("    → ENG102 waived.")
        else:
            print("    → ENG102 not waived (grade will count in Credit Counted and CGPA).")
        mat_raw = input("    Is MAT112 waived for this student? (y/n): ").strip().lower()
        if mat_raw in ("y", "yes"):
            waived_courses_waiverable.add("MAT112")
            print("    → MAT112 waived.")
        else:
            print("    → MAT112 not waived (grade will count in Credit Counted and CGPA).")
        num_waivers = len(waived_courses_waiverable)
        required_credits = get_required_credits_for_waivers(program_key, num_waivers)
        print(f"\n  Required credits for {program_key}: {required_credits}  (based on {num_waivers} waiver(s)).")
    else:
        required_credits = PROGRAM_BASE_CREDITS.get(program_key) if program_key else None
        if required_credits is not None:
            print(f"\n  Waiver not applicable. Required credits: {required_credits}.")
        else:
            print("\n  Waiver not applicable for this program.")
    waived_courses = waived_courses_waiverable
    waiver_applied = len(waived_courses) > 0
    print()

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
    core_excluded: Set[str] = set()
    if program_key == "MIC":
        core_excluded = select_mic_core_choices(rows)
        alias_exclusions = resolve_mic_aliases(rows)
        if alias_exclusions:
            print("\n  SHLS Core alias resolution (equivalent course pairs):")
            for excl, kept in alias_exclusions.items():
                print(f"    {excl} excluded — {kept} already satisfies this slot (better/equal grade).")
            print()
        core_excluded = core_excluded | set(alias_exclusions.keys())
        if allowed_codes is not None:
            allowed_codes = allowed_codes - core_excluded

    # --- CSE: Auto-resolve GED choice groups (POL/ECO/SOC slots) ---
    if program_key == "CSE":
        cse_choice_excluded = resolve_cse_choice_groups(rows)
        if cse_choice_excluded:
            print("\n  CSE GED choice resolution (only one course per slot counts):")
            for c in sorted(cse_choice_excluded):
                print(f"    {c} excluded — a higher-grade course fills the same required slot.")
            print()
        core_excluded = core_excluded | cse_choice_excluded
        if allowed_codes is not None:
            allowed_codes = allowed_codes - cse_choice_excluded

    # Track all elective-eligible course codes BEFORE selection so unselected ones
    # can be labelled accurately in the report instead of "not in curriculum".
    all_elective_candidates: Set[str] = set()
    if program_key == "CSE":
        all_elective_candidates = {c for trail in CSE_TRAILS.values() for c in trail}
    elif program_key == "MIC":
        all_elective_candidates = set(MIC_ELECTIVES)

    # --- Elective Selection ---
    major_electives: list[str] = []
    open_elective: str = ""
    free_electives: list[str] = []
    if program_key in ("CSE", "MIC"):
        major_electives, open_elective, free_electives = select_electives(
            program_key, rows, allowed_codes=allowed_codes, waived_courses=waived_courses
        )
        print_elective_summary(major_electives, open_elective, program_key, free_electives=free_electives)
        # Merge selected electives into allowed curriculum so they count toward the tally
        if allowed_codes is not None:
            all_selected = set(major_electives) | set(free_electives) | ({open_elective} if open_elective else set())
            allowed_codes = allowed_codes | all_selected

    # Elective candidates the student passed but were not selected — label them clearly
    all_selected_electives = set(major_electives) | set(free_electives) | ({open_elective} if open_elective else set())
    unselected_electives = all_elective_candidates - all_selected_electives

    # --- Prerequisite setup ---
    pkey = program_key if program_key in ("CSE", "MIC") else None
    prereq_map = CSE_PREREQS if pkey == "CSE" else (MIC_PREREQS if pkey == "MIC" else None)
    passed_set = build_passed_set(rows) if prereq_map else None
    # Baseline credit tally (no prereq enforcement) used for CREDITS_60/100 checks
    baseline_credits = compute_baseline_credits(
        rows, allowed_codes, credits_by_program, pkey
    ) if prereq_map else 0.0

    total, per_course, by_course, prereq_failures = compute_total_valid_credits(
        rows,
        allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=pkey,
        prereq_map=prereq_map,
        passed_set=passed_set,
        waived_courses=waived_courses,
        earned_credits=baseline_credits,
    )
    print_report(
        args.transcript,
        args.program_name,
        total,
        per_course,
        by_course,
        required_credits,
        allowed_codes=allowed_codes,
        program_credits=credits_by_program,
        program_key=pkey,
        major_electives=major_electives,
        open_elective=open_elective,
        free_electives=free_electives,
        core_excluded=core_excluded,
        unselected_electives=unselected_electives,
        waiver_applied=waiver_applied,
        waived_courses=waived_courses,
        prereq_failures=prereq_failures,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())