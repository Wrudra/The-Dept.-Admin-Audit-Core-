#!/usr/bin/env python3
"""
Level 1: Credit Tally Engine
Reads a student transcript CSV and reports total valid (earned) credits for graduation.

FIXES applied (vs original):
  #2  MIC498 prerequisite: all labs are AND-groups — every lab must be passed (not OR).
  #3  Removed dead is_no_credit() function.
  #5  get_ncl_labs(): MIC gets its own empty NCL set; no longer inherits CSE labs.
  #6  Early validation for unsupported program names in main().
  #7  Retake tiebreaker: same grade → use transcript order (most recent), not credits.
  #10 --no-interact flag: auto-selects best options; suitable for AI-agent invocation.
  #12 detect_credit_mismatches() + print_credit_mismatch_warning(): if a transcript
      lists a different credit value than program.md defines, a warning banner is
      printed and the program-defined credit is used (as it always was, silently).
      Applies to both CSE and MIC.  NCL (0-credit) labs are exempt from the check.
  #14 detect_credit_mismatches(): used the first-occurrence credit per course,
      so a retake row carrying a wrong credit was invisible when the earlier
      attempt had the correct credit (e.g. CSE173 C+/3cr then A/80cr → only
      80cr row matters but 3cr was seen first).  Fixed to use the best-passing-
      attempt credit, mirroring the credit engine's own selection logic.
  #15 detect_credit_mismatches(): CSE_INTERNSHIP_RESEARCH (CSE498R/I) now exempt
      from the mismatch check — their credit is hardcoded to 1.0 in
      load_program_courses() regardless of the transcript, so the warning was
      redundant noise.
  #16 detect_credit_mismatches(): courses where program.md defines 0.0 credits
      (e.g. MAT116 in CSE — prereq-only, no graduation credit) are now exempt.
      The transcript will always carry the registrar face-value (3.0); flagging
      this as a mismatch is misleading since the zero is an intentional policy.

Usage: python3 audit_l1.py transcript.csv program_name program_knowledge.md [--no-interact]
"""

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Optional, Set

# ══════════════════════════════════════════════════════════════════════════════
#  Visual layout constants
# ══════════════════════════════════════════════════════════════════════════════
_CC, _CCR, _CG, _CS = 12, 9, 6, 90          # col widths: code, credits, grade, status
_BW = (_CC+2) + 1 + (_CCR+2) + 1 + (_CG+2) + 1 + (_CS+2)   # banner inner width = 128

def _tsep(l='├', m='┼', r='┤'):
    return (f"  {l}" + "─"*(_CC+2) + m + "─"*(_CCR+2) + m
            + "─"*(_CG+2) + m + "─"*(_CS+2) + r)

_TTOP = _tsep('┌', '┬', '┐')
_TROW_SEP = _tsep()
_TBOT = _tsep('└', '┴', '┘')
_THDR = (f"  │ {'Course':<{_CC}} │ {'Credits':>{_CCR}} │ "
         f"{'Grade':<{_CG}} │ {'Status / Reason':<{_CS}} │")

def _trow(code: str, cr, grade: str, status: str) -> str:
    cr_s = f"{cr:>{_CCR}.1f}" if isinstance(cr, (int, float)) else f"{'—':^{_CCR}}"
    return (f"  │ {str(code):<{_CC}} │ {cr_s} │ "
            f"{str(grade):<{_CG}} │ {str(status)[:_CS]:<{_CS}} │")

def _btop(): return f"  ╔{'═'*_BW}╗"
def _bsep(): return f"  ╠{'═'*_BW}╣"
def _bbot(): return f"  ╚{'═'*_BW}╝"
def _bline(text: str = "") -> str: return f"  ║  {text:<{_BW-2}}║"

# ══════════════════════════════════════════════════════════════════════════════
#  NSU Offered Course Catalog
#  Source: NSU Offered Course List (Spring 2026), scraped from the RDS portal.
#  Cross-listed courses (e.g. CSE311/ETE335) are included under each code.
# ══════════════════════════════════════════════════════════════════════════════
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
    "CSE373","CSE401","CSE411","CSE413L/EEE413L/ETE419L","CSE418","CSE424","CSE427","CSE428","CSE429","CSE433",
    "CSE435/EEE411/ETE412","CSE435L/EEE411L/ETE412L","CSE440/EEE333/ETE333","CSE445","CSE446","CSE447","CSE448","CSE449",
    "CSE465","CSE468","CSE470","CSE482/ETE334",
    "CSE482L/ETE334L","CSE491","CSE492","CSE493","CSE494","CSE495A","CSE495B","CSE496","CSE532/EEE560","CSE534","CSE562","CSE583","CSE597/EEE597/ETE597","DEV503","DEV564",
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
    "MAT370","MAT480","MAT481","MAT482","MAT483","MAT485",
    # Minor in Physics courses
    "PHY230","PHY240","PHY250","PHY260","PHY310","PHY440",
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

# Expanded catalog: splits cross-listed entries so individual code lookups work.
NSU_CATALOG_EXPANDED: Set[str] = {
    part.strip()
    for entry in NSU_CATALOG
    for part in entry.split("/")
}

# ══════════════════════════════════════════════════════════════════════════════
#  Trail / elective / choice definitions
# ══════════════════════════════════════════════════════════════════════════════
CSE_TRAILS: dict[str, list[str]] = {
    "Algorithms and Computation": ["CSE257","CSE417","CSE401","CSE418","CSE326","CSE426","CSE273","CSE473","CSE491"],
    "Software Engineering":       ["CSE411","CSE424","CSE427","CSE428","CSE429","CSE492"],
    "Networks":                   ["CSE422","CSE562","CSE338","CSE438","CSE482","CSE485","CSE486","CSE493"],
    "Computer Architecture & VLSI": ["CSE433","CSE435","CSE413","CSE414","CSE495A","CSE494"],
    "Artificial Intelligence":    ["CSE440","CSE445","CSE465","CSE467","CSE419","CSE598","CSE468","CSE470","CSE495B"],
    "Bioinformatics":             ["CSE446","CSE447","CSE448","CSE449","CSE496"],
}

# Cross-listed trail course pairs — each pair is ONE slot; only the better attempt counts.
# e.g. CSE257 and CSE417 are cross-listed; a student cannot count both as separate electives.
CSE_TRAIL_ALIAS_PAIRS: list[tuple[str,str]] = [
    ("CSE257", "CSE417"),   # Algorithms trail
    ("CSE326", "CSE426"),   # Algorithms trail
    ("CSE273", "CSE473"),   # Algorithms trail
    ("CSE338", "CSE438"),   # Networks trail
]

MIC_ELECTIVES: list[str] = ["MIC201","MIC318","MIC404","MIC311","MIC309","MIC416","MIC417","MIC418"]

# CSE GED/University Core — student fills each slot with exactly ONE course
CSE_GED_CHOICE_GROUPS: list[list[str]] = [
    ["POL101","POL104"],
    ["ECO101","ECO104"],
    ["SOC101","ENV203","GEO205","ANT101"],
]

# ══════════════════════════════════════════════════════════════════════════════
#  Prerequisite maps
#  Each dict maps course_code → list[frozenset].
#  A frozenset is an OR-group (one member must be passed); all frozensets AND.
#  Tokens: WAIVER_ENG102, WAIVER_MAT112, CREDITS_60, CREDITS_100.
# ══════════════════════════════════════════════════════════════════════════════
CSE_PREREQS: dict[str, list] = {
    "ENG103":  [frozenset({"ENG102","WAIVER_ENG102"})],
    "ENG111":  [frozenset({"ENG103"})],
    "BEN205":  [frozenset({"ENG103"})],
    "MAT116":  [frozenset({"MAT112","WAIVER_MAT112"})],
    "MAT120":  [frozenset({"MAT116"})],
    "MAT125":  [frozenset({"MAT116"})],
    "MAT130":  [frozenset({"MAT120"})],
    "MAT250":  [frozenset({"MAT130"})],
    "MAT350":  [frozenset({"MAT250"})],
    "MAT361":  [frozenset({"MAT250"})],
    "PHY107":  [frozenset({"MAT120"})],
    "PHY107L": [frozenset({"MAT120"})],
    "PHY108":  [frozenset({"MAT130"}),frozenset({"PHY107"})],
    "PHY108L": [frozenset({"MAT130"}),frozenset({"PHY107"})],
    "CHE101":  [frozenset({"MAT350"})],
    "CSE173":  [frozenset({"CSE115"})],
    "CSE215":  [frozenset({"CSE173"})],
    "CSE215L": [frozenset({"CSE173"})],
    "CSE225":  [frozenset({"CSE215"})],
    "CSE225L": [frozenset({"CSE215"})],
    "CSE231":  [frozenset({"CSE173"})],
    "CSE231L": [frozenset({"CSE173"})],
    "EEE141":  [frozenset({"PHY107"}),frozenset({"MAT120"})],
    "EEE141L": [frozenset({"PHY107"}),frozenset({"MAT120"})],
    "EEE111":  [frozenset({"EEE141"})],
    "EEE111L": [frozenset({"EEE141"})],
    "CSE311":  [frozenset({"CSE225"})],
    "CSE311L": [frozenset({"CSE225"})],
    "CSE332":  [frozenset({"CSE231"})],
    "CSE332L": [frozenset({"CSE231"})],
    "CSE323":  [frozenset({"CSE332"})],
    "CSE373":  [frozenset({"CSE225"}),frozenset({"MAT361"})],
    "CSE327":  [frozenset({"CSE311"})],
    "CSE331":  [frozenset({"CSE323"})],
    "CSE331L": [frozenset({"CSE323"})],
    "CSE425":  [frozenset({"CSE327"})],
    "CSE299":  [frozenset({"CREDITS_60"})],
    "CSE499A": [frozenset({"CREDITS_100"})],
    "CSE499B": [frozenset({"CSE499A"})],
    # ── Trail elective prerequisites (from NSU ECE website) ──────────────────
    "CSE417":  [frozenset({"CSE225"}),frozenset({"MAT125"})],
    "CSE418":  [frozenset({"CSE225"}),frozenset({"CSE332"})],
    "CSE326":  [frozenset({"CSE332"})],
    "CSE426":  [frozenset({"CSE332"})],
    "CSE473":  [frozenset({"CSE173"}),frozenset({"CSE225"})],
    "CSE411":  [frozenset({"CSE311"})],
    "CSE424":  [frozenset({"CSE225"})],
    "CSE427":  [frozenset({"CSE327"})],
    "CSE428":  [frozenset({"CSE327"})],
    "CSE429":  [frozenset({"CSE327"})],
    "CSE338":  [frozenset({"CSE215"})],
    "CSE438":  [frozenset({"CSE215"})],
    "CSE482":  [frozenset({"CSE338","CSE438"})],
    "CSE433":  [frozenset({"CSE331"})],
    "CSE435":  [frozenset({"EEE111"}),frozenset({"CSE231"})],
    "CSE413":  [frozenset({"CSE231"})],
    "CSE414":  [frozenset({"CSE413"})],
    "CSE440":  [frozenset({"CSE225"}),frozenset({"MAT361"})],
    "CSE465":  [frozenset({"CSE373"})],
    "CSE468":  [frozenset({"CSE440"})],
    # ── End trail elective prerequisites ─────────────────────────────────────
    # Minor in Mathematics — all additional courses require MAT250
    "MAT370":  [frozenset({"MAT250"})],
    "MAT480":  [frozenset({"MAT250"})],
    "MAT481":  [frozenset({"MAT250"})],
    "MAT482":  [frozenset({"MAT250"})],
    "MAT483":  [frozenset({"MAT250"})],
    "MAT485":  [frozenset({"MAT250"})],
    # Minor in Physics — base courses require PHY108; upper-level require PHY250
    "PHY230":  [frozenset({"PHY108"})],
    "PHY240":  [frozenset({"PHY108"})],
    "PHY250":  [frozenset({"PHY108"})],
    "PHY260":  [frozenset({"PHY108"})],
    "PHY310":  [frozenset({"PHY250"})],
    "PHY440":  [frozenset({"PHY250"})],
}

MIC_PREREQS: dict[str, list] = {
    # Change 1: ENG103 requires ENG102 or waiver (same rule as CSE).
    # WAIVER_ENG102 token: waived ENG102 keeps ENG103 and its dependents accessible.
    "ENG103":  [frozenset({"ENG102","WAIVER_ENG102"})],
    "ENG105":  [frozenset({"ENG103"})],
    "BEN205":  [frozenset({"ENG103"})],
    "ENG111":  [frozenset({"ENG103"})],
    "CHE201":  [frozenset({"CHE101"})],
    "CHE202":  [frozenset({"CHE101"})],
    "CHE202L": [frozenset({"CHE101L"})],
    # Change 2: MAT116 requires MAT112 or waiver for MIC.
    # WAIVER_MAT112 token: waived MAT112 keeps MAT116 accessible.
    "MAT116":  [frozenset({"MAT112","WAIVER_MAT112"})],
    "BIO201":  [frozenset({"BIO103"})],
    "MIC110":  [frozenset({"BIO103"})],
    "BIO201L": [frozenset({"BIO103L"})],
    "MIC110L": [frozenset({"BIO103L"})],
    "BIO202":  [frozenset({"BIO103"})],
    "MIC101":  [frozenset({"BIO103"})],
    "BIO202L": [frozenset({"BIO103L"})],
    "MIC101L": [frozenset({"BIO103L"})],
    "MIC203":  [frozenset({"BIO201","MIC110"}),frozenset({"BIO202","MIC101"})],
    "BBT203":  [frozenset({"BIO201","MIC110"}),frozenset({"BUS172"})],
    "MIC202":  [frozenset({"CHE101"}),frozenset({"BIO202","MIC101"})],
    "MIC307":  [frozenset({"BIO201","MIC110"}),frozenset({"MIC202"})],
    "MIC314":  [frozenset({"MIC201"}),frozenset({"MIC202"})],
    "MIC315":  [frozenset({"MIC203"}),frozenset({"MIC202"})],
    "MIC315L": [frozenset({"BIO202L","MIC101L"}),frozenset({"MIC315"})],
    "MIC316":  [frozenset({"MIC307"})],
    "MIC316L": [frozenset({"BIO201L"}),frozenset({"MIC316"})],         # Change 2: needs BIO201L AND MIC316
    "MIC317":  [frozenset({"MIC307"}),frozenset({"MIC315"})],
    "MIC317L": [frozenset({"BIO202L","MIC101L"}),frozenset({"MIC317"})],
    "MIC206":  [frozenset({"MIC316"})],
    "MIC207":  [frozenset({"MIC203"}),frozenset({"CHE202"})],  # Change 1: needs MIC203 AND CHE202
    "MIC401":  [frozenset({"MIC316"}),frozenset({"MIC309"})],
    "MIC412":  [frozenset({"MIC315"}),frozenset({"MIC316"})],
    "MIC413":  [frozenset({"MIC316"}),frozenset({"MIC317"})],
    "MIC413L": [frozenset({"BIO202L","MIC101L"}),frozenset({"MIC413"})],
    "MIC414":  [frozenset({"MIC202"}),frozenset({"MIC203"})],
    "MIC414L": [frozenset({"BIO202L","MIC101L"}),frozenset({"MIC414"})],
    "MIC415":  [frozenset({"MIC202"}),frozenset({"MIC203"})],
    "MIC415L": [frozenset({"BIO202L","MIC101L"}),frozenset({"MIC415"})],
    # Change 3: MIC498 requires MIC316 AND ALL lab courses passed.
    # Each lab is its own AND-group so every one must be completed.
    "MIC498":  [
        frozenset({"MIC316"}),
        frozenset({"MIC315L"}),
        frozenset({"MIC316L"}),
        frozenset({"MIC317L"}),
        frozenset({"MIC413L"}),
        frozenset({"MIC414L"}),
        frozenset({"MIC415L"}),
    ],
    "MIC201":  [frozenset({"BIO202","MIC101"})],
    "MIC309":  [frozenset({"MIC203"}),frozenset({"MIC207"})],
    "MIC311":  [frozenset({"MIC316"})],
    "MIC318":  [frozenset({"MIC203"}),frozenset({"MIC201"})],
    "MIC404":  [frozenset({"MIC307"})],
    "MIC416":  [frozenset({"MIC316"})],
    "MIC417":  [frozenset({"MIC317"})],
    "MIC418":  [frozenset({"MIC416"})],
}

# ══════════════════════════════════════════════════════════════════════════════
#  Grade tables
# ══════════════════════════════════════════════════════════════════════════════
GRADE_RANK: dict[str,int] = {
    "A":10,"A-":9,"B+":8,"B":7,"B-":6,
    "C+":5,"C":4,"C-":3,"D+":2,"D":1,
}
PASSING_GRADES = set(GRADE_RANK.keys())
NO_CREDIT_GRADES = {"F","W","I"}

# ══════════════════════════════════════════════════════════════════════════════
#  Non-credit lab sets
#  FIX #5: MIC has its own NCL set (currently empty; no 0-credit labs in MIC core).
#           Previously MIC inherited CSE labs (CSE225L etc.) which was semantically wrong.
# ══════════════════════════════════════════════════════════════════════════════
CSE_NCL_LABS: Set[str] = {"CSE225L","CSE231L","CSE311L","CSE331L","CSE332L"}
MIC_NCL_LABS: Set[str] = set()   # MIC has no 0-credit labs in core curriculum

def get_ncl_labs(program_key: Optional[str] = None) -> Set[str]:
    """Return the set of non-credit (0-credit) lab codes for the given program."""
    if program_key == "CSE":
        return CSE_NCL_LABS
    if program_key == "MIC":
        return MIC_NCL_LABS
    return CSE_NCL_LABS   # conservative fallback for unknown programs

# ══════════════════════════════════════════════════════════════════════════════
#  Program credit requirements
# ══════════════════════════════════════════════════════════════════════════════
PROGRAM_BASE_CREDITS: dict[str,int] = {"CSE":130,"MIC":120}
WAIVERABLE_COURSES = frozenset({"ENG102","MAT112"})
WAIVER_CREDITS_EACH = 3
CSE_INTERNSHIP_RESEARCH = frozenset({"CSE498R","CSE498I"})
# BIO103L and CSE498R/I fill the same 1-credit slot — only one may count.
CSE_BIO_INTERNSHIP_SLOT: frozenset[str] = frozenset({"BIO103L","CSE498R","CSE498I"})
# Minor in Math — additional courses beyond School Core (MAT120/125/130/250 already required)
CSE_MINOR_MATH:    Set[str] = {"MAT370","MAT480","MAT481","MAT482","MAT483","MAT485"}
# Minor in Physics — PHY310/PHY440 are a choice (either counts)
CSE_MINOR_PHYSICS: Set[str] = {"PHY230","PHY240","PHY250","PHY260","PHY310","PHY440"}
CSE_MINOR_COURSES: Set[str] = CSE_MINOR_MATH | CSE_MINOR_PHYSICS

def get_required_credits_for_waivers(program_key: str, num_waivers: int) -> int:
    base = PROGRAM_BASE_CREDITS.get(program_key, 130)
    return base + (2 - min(2, max(0, num_waivers))) * WAIVER_CREDITS_EACH

# ══════════════════════════════════════════════════════════════════════════════
#  MIC required categories + choice groups
# ══════════════════════════════════════════════════════════════════════════════
MIC_REQUIRED_CATEGORIES: dict[str,set[str]] = {
    "University Core": {
        "ENG102","ENG103","ENG105","BEN205","ENG111",
        "HIS101","HIS103","PHI101",
        "POL101","POL104","ECO101","ECO104","SOC101","ANT101",
        "MIS107","MAT112","MAT116","BUS172",
        "BIO103","BIO103L","PHY107","PHY107L",
    },
    "SHLS Core": {
        "BBT203",
        "CHE101","CHE101L","CHE201","CHE202","CHE202L",
        "BIO201","MIC110","BIO201L","MIC110L",
        "BIO202","MIC101","BIO202L","MIC101L",
        "MIC203",
    },
    "Major Core": {
        "MIC202","MIC206","MIC207","MIC307","MIC314",
        "MIC315","MIC315L","MIC316","MIC316L","MIC317","MIC317L",
        "MIC401","MIC412","MIC413","MIC413L",
        "MIC414","MIC414L","MIC415","MIC415L","MIC498",
    },
}

MIC_ALIAS_PAIRS: list[tuple[str,str]] = [
    ("BIO201","MIC110"),("BIO201L","MIC110L"),
    ("BIO202","MIC101"),("BIO202L","MIC101L"),
]
MIC_LANGUAGE_CHOICES: list[str] = ["BEN205","ENG111"]
MIC_HUMANITIES_CHOICES: list[str] = ["HIS101","HIS103","PHI101"]
MIC_SOCIAL_CHOICES: list[str]     = ["POL101","POL104","ECO101","ECO104","SOC101","ANT101"]
MIC_SCIENCE_CHOICES: list[tuple[str,str]] = [
    ("BIO103","BIO103L"),("PHY107","PHY107L"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  Non-interactive / batch mode flag
#  FIX #10: Set NO_INTERACT=True via --no-interact to skip all prompts.
#           Auto-selects best grade for choice slots; first available for electives.
#           Suitable for AI-agent or pipeline invocations.
# ══════════════════════════════════════════════════════════════════════════════
NO_INTERACT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
#  Core helpers
# ══════════════════════════════════════════════════════════════════════════════
def normalize_course_code(raw: str) -> str:
    return re.sub(r"\s+","",( raw or "").strip()).upper()

def parse_credits(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw: return 0.0
    try: return float(raw)
    except ValueError: return 0.0

def normalize_grade(raw: str) -> str:
    return (raw or "").strip().upper()

def is_passing(grade: str) -> bool:
    return grade in PASSING_GRADES

def has_passing_attempt(attempts: list[dict]) -> bool:
    return any(is_passing(a["grade"]) for a in attempts)

def get_display_grade(attempts: list[dict]) -> str:
    if not attempts: return "—"
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        # FIX #7: tiebreak on grade rank only; same grade → keep most recent (last in list)
        best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0))
        return best["grade"]
    return attempts[-1]["grade"] if attempts[-1]["grade"] else "—"

def valid_credits_for_course(attempts: list[dict]) -> float:
    """
    Retake rule: only best passing attempt counts once; if none, 0.
    FIX #7: tiebreak on grade rank only — same grade → use most recent attempt.
    """
    passing = [a for a in attempts if is_passing(a["grade"])]
    if not passing: return 0.0
    best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0))
    return best["credits"]

def build_passed_set(
    rows: list[dict],
    prereq_map: Optional[dict[str,list]] = None,
    waived_courses: Optional[Set[str]] = None,
    earned_credits: float = 0.0,
) -> Set[str]:
    """
    Build the set of courses the student genuinely passed, propagating
    prerequisite failures transitively.

    Without a prereq_map: simple grade-based set (original behaviour).
    With a prereq_map: runs iterative rounds until stable:
      Round 1: collect all courses with a passing grade
      Round N: remove any course whose prereq is no longer in the valid set
    This ensures MAT250 is invalidated when MAT130 is invalid,
    and MAT370/480/481+ are invalidated when MAT250 is invalid, etc.
    """
    seen: dict[str,list[dict]] = {}
    for r in rows:
        seen.setdefault(normalize_course_code(r["course_code"]),[]).append(r)

    # Start with every course that has a passing grade attempt
    valid: Set[str] = {code for code, att in seen.items() if has_passing_attempt(att)}

    if not prereq_map:
        return valid

    # Waived courses count as implicitly passed for prereq checking
    _waived = {normalize_course_code(c) for c in (waived_courses or set())}
    effective = valid | _waived

    # Iteratively remove courses whose prereqs are no longer satisfied.
    # Use earned_credits=inf so CREDITS_60/CREDITS_100 thresholds never falsely
    # invalidate courses during propagation — those are checked separately in
    # compute_total_valid_credits with the real baseline credit total.
    while True:
        to_remove: Set[str] = set()
        for code in list(valid):
            ok, _ = prereq_satisfied(
                code, effective - {code}, prereq_map,
                waived_courses=waived_courses,
                earned_credits=float("inf"),   # ignore credit-threshold prereqs here
            )
            if not ok:
                to_remove.add(code)
        if not to_remove:
            break
        valid -= to_remove
        effective = valid | _waived

    return valid

def prereq_satisfied(
    course: str,
    passed_set: Set[str],
    prereq_map: dict[str,list],
    waived_courses: Optional[Set[str]] = None,
    earned_credits: float = 0.0,
) -> tuple[bool,str]:
    """Return (True,"") on success, (False,"reason") on failure."""
    normalized = normalize_course_code(course)
    spec = prereq_map.get(normalized)
    if not spec: return True,""
    _waived = {normalize_course_code(c) for c in (waived_courses or set())}
    missing_labels: list[str] = []
    for or_group in spec:
        if "CREDITS_60" in or_group:
            if earned_credits >= 60: continue
            missing_labels.append(f"60 credits (have {earned_credits:.0f})")
            continue
        if "CREDITS_100" in or_group:
            if earned_credits >= 100: continue
            missing_labels.append(f"100 credits (have {earned_credits:.0f})")
            continue
        group_ok = False
        for opt in or_group:
            n = normalize_course_code(opt)
            if n == "WAIVER_ENG102":
                if "ENG102" in _waived: group_ok = True; break
            elif n == "WAIVER_MAT112":
                if "MAT112" in _waived: group_ok = True; break
            elif n in passed_set or n in _waived:
                group_ok = True; break
        if not group_ok:
            _waiver_tokens = {"WAIVER_ENG102","WAIVER_MAT112"}
            real = sorted(o for o in or_group if o not in _waiver_tokens)
            missing_labels.append(real[0] if len(real)==1 else "("+(" or ".join(real))+")")
    if missing_labels:
        return False,"prereq not met: "+", ".join(missing_labels)
    return True,""

def compute_baseline_credits(
    rows: list[dict],
    allowed_codes: Optional[Set[str]],
    program_credits: Optional[dict[str,dict[str,float]]],
    program_key: Optional[str],
) -> float:
    """Quick tally (no capstone) used to evaluate CREDITS_60 / CREDITS_100 thresholds."""
    CAPSTONE = {"CSE299","CSE499A","CSE499B"}
    ncl = get_ncl_labs(program_key)
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"],[]).append(r)
    total = 0.0
    for code, att in by_course.items():
        n = normalize_course_code(code)
        if n in CAPSTONE or n in ncl: continue
        if allowed_codes is not None and n not in allowed_codes: continue
        if not has_passing_attempt(att): continue
        if program_credits and program_key and n in program_credits.get(program_key,{}):
            total += program_credits[program_key][n]
        else:
            total += valid_credits_for_course(att)
    return total

# ══════════════════════════════════════════════════════════════════════════════
#  Program knowledge parsing
# ══════════════════════════════════════════════════════════════════════════════
def _extract_course_codes_from_text(text: str) -> Set[str]:
    codes: Set[str] = set()
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]: continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2: continue
        first = re.sub(r"\*\*","",parts[1].strip())
        if not first or first.upper() in ("COURSE","CREDITS","NOTES") or re.match(r"^[-]+$",first): continue
        course_part = first.split(",")[0].strip()
        for seg in re.split(r"\s*/\s*|\s+and\s+",course_part,flags=re.IGNORECASE):
            for m in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*",seg.strip()):
                code = normalize_course_code(m.group(0))
                if len(code)>=4 and code not in ("CHOOSE","ONE","LAB","NONCREDIT"):
                    codes.add(code)
    return codes

def _extract_course_credits_from_text(text: str) -> dict[str,float]:
    result: dict[str,float] = {}
    for line in text.splitlines():
        if not line.strip().startswith("|") or "|" not in line[1:]: continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2: continue
        first = re.sub(r"\*\*","",parts[1].strip())
        cred_cell = parts[2].strip() if len(parts)>2 else "0"
        if not first or first.upper() in ("COURSE","CREDITS","NOTES") or re.match(r"^[-]+$",first): continue
        if re.match(r"non-?credit",cred_cell,flags=re.IGNORECASE):
            cred_values = [0.0]
        else:
            cred_values = [float(m) for m in re.findall(r"\d+\.?\d*",cred_cell)] or [0.0]
        course_part = first.split(",")[0].strip()
        codes_in_row: list[str] = []
        for seg in re.split(r"\s*/\s*|\s+and\s+",course_part,flags=re.IGNORECASE):
            for m in re.finditer(r"[A-Za-z]+\s*\d+[A-Za-z]*",seg.strip()):
                code = normalize_course_code(m.group(0))
                if len(code)>=4 and code not in ("CHOOSE","ONE","LAB","NONCREDIT"):
                    codes_in_row.append(code)
        for i, code in enumerate(codes_in_row):
            result[code] = cred_values[i] if i<len(cred_values) else cred_values[-1]
    return result

def load_program_courses(program_path: Path) -> tuple[dict[str,Set[str]],dict[str,dict[str,float]]]:
    codes: dict[str,Set[str]] = {"CSE":set(),"MIC":set()}
    credits: dict[str,dict[str,float]] = {"CSE":{},"MIC":{}}
    if not program_path.exists(): return codes,credits
    try: text = program_path.read_text(encoding="utf-8")
    except OSError: return codes,credits
    if "Microbiology Undergraduate Program" in text:
        before_mic,_,after_mic = text.partition("# Microbiology Undergraduate Program")
        codes["MIC"]   = _extract_course_codes_from_text(after_mic)
        credits["MIC"] = _extract_course_credits_from_text(after_mic)
        cse_start = before_mic.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            cse_block = before_mic[cse_start:]
            codes["CSE"]   = _extract_course_codes_from_text(cse_block)
            credits["CSE"] = _extract_course_credits_from_text(cse_block)
    else:
        cse_start = text.find("# CSE Undergraduate Program")
        if cse_start >= 0:
            cse_block = text[cse_start:]
            codes["CSE"]   = _extract_course_codes_from_text(cse_block)
            credits["CSE"] = _extract_course_credits_from_text(cse_block)
    codes["CSE"].update(CSE_INTERNSHIP_RESEARCH)
    for c in CSE_INTERNSHIP_RESEARCH:
        credits["CSE"][c] = 1.0
    for pkey in ("CSE","MIC"):
        credits[pkey]["ENG102"] = 3.0
        credits[pkey]["MAT112"] = 3.0
    return codes,credits

# ══════════════════════════════════════════════════════════════════════════════
#  Transcript loading
# ══════════════════════════════════════════════════════════════════════════════
def load_transcript(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames: return rows
        keys = {k.strip().lower().replace(" ","_"): k for k in reader.fieldnames}
        for row in reader:
            course_code = normalize_course_code((row.get(keys.get("course_code","Course_Code")) or "").strip())
            credits     = parse_credits(row.get(keys.get("credits","Credits")) or "0")
            grade       = normalize_grade(row.get(keys.get("grade","Grade")) or "")
            semester    = (row.get(keys.get("semester","Semester")) or "").strip()
            if not course_code and not grade and credits==0: continue
            rows.append({"course_code":course_code or "UNKNOWN","credits":credits,"grade":grade,"semester":semester})
    return rows

# ══════════════════════════════════════════════════════════════════════════════
#  Credit mismatch detection
# ══════════════════════════════════════════════════════════════════════════════
def detect_credit_mismatches(
    rows: list[dict],
    program_credits: dict[str, dict[str, float]],
    program_key: str,
    allowed_codes: Optional[Set[str]] = None,
) -> dict[str, tuple[float, float]]:
    """
    Compare transcript credit values against program.md definitions.
    For every in-curriculum course whose transcript credit differs from the
    program-defined credit, record (transcript_cr, program_cr).

    Only courses listed in program.md (program_credits) and belonging to the
    program curriculum (allowed_codes) are checked.  NCL (0-credit) labs are
    skipped because the transcript often omits their credit column entirely.

    Returns: {normalized_course_code: (transcript_cr, program_cr)}
    """
    prog_cr_map = program_credits.get(program_key, {})
    ncl = get_ncl_labs(program_key)

    # Collect transcript credit per course using the SAME selection logic as the
    # credit engine: the best passing attempt's credit value wins.
    # If there are no passing attempts, fall back to the last non-zero credit seen.
    # FIX #14: the original code used the FIRST occurrence credit, so a retake row
    # with a wrong credit value was invisible when the earlier attempt had the
    # correct credit.  e.g. CSE173: C+ (3cr) then A (80cr) → old code saw 3cr ✓,
    # new code sees the best-passing-attempt credit (80cr) → fires mismatch ✓.
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    transcript_cr: dict[str, float] = {}
    for n, attempts in by_course.items():
        passing = [a for a in attempts if is_passing(a["grade"])]
        if passing:
            best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"], 0))
            transcript_cr[n] = best["credits"]
        else:
            # No passing attempt — use last non-zero credit, else last credit
            non_zero = [a for a in attempts if a["credits"] != 0.0]
            ref = non_zero[-1] if non_zero else attempts[-1]
            transcript_cr[n] = ref["credits"]

    mismatches: dict[str, tuple[float, float]] = {}
    for n, t_cr in transcript_cr.items():
        if allowed_codes is not None and n not in allowed_codes:
            continue  # not part of this program's curriculum
        if n in ncl:
            continue  # NCL labs are always 0-credit — skip
        if n in CSE_INTERNSHIP_RESEARCH:
            continue  # credit hardcoded to 1.0 in load_program_courses(); mismatch warning redundant
        if n not in prog_cr_map:
            continue  # program.md has no credit entry for this course
        p_cr = prog_cr_map[n]
        if p_cr == 0.0:
            continue  # program defines 0-credit intentionally (e.g. MAT116 in CSE); not a mismatch
        if abs(t_cr - p_cr) > 1e-9:
            mismatches[n] = (t_cr, p_cr)

    return mismatches


def print_credit_mismatch_warning(mismatches: dict[str, tuple[float, float]]) -> None:
    """
    Print a prominent warning banner whenever the transcript lists different
    credit values from those defined in program.md.
    Program-defined credits are always authoritative for all calculations.
    """
    if not mismatches:
        return
    print()
    print(_btop())
    print(_bline("⚠  CREDIT MISMATCH — TRANSCRIPT vs PROGRAM DEFINITION"))
    print(_bline("The courses below have different credit values in the transcript vs the program knowledge file."))
    print(_bline("Program-defined credits are authoritative and have been used for all calculations."))
    print(_bsep())
    print(_THDR)
    print(_TROW_SEP)
    for code in sorted(mismatches):
        t_cr, p_cr = mismatches[code]
        status = (f"Transcript listed {t_cr:.1f} cr  →  "
                  f"Overridden with program.md value: {p_cr:.1f} cr")
        print(_trow(code, p_cr, "—", status))
        print(_TROW_SEP)
    print(_TBOT)
    print(_bbot())
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  Grade anomaly detection
# ══════════════════════════════════════════════════════════════════════════════
_KNOWN_GRADES: frozenset[str] = frozenset(PASSING_GRADES | NO_CREDIT_GRADES)

def detect_grade_anomalies(rows: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """
    Scan every transcript row for grades outside NSU policy.
    A grade is anomalous if it is not in PASSING_GRADES (A..D) or NO_CREDIT_GRADES (F/W/I).

    Returns: {course_code: [(grade, semester), ...]}
      — one entry per course that has at least one anomalous attempt.
      Multiple anomalous rows for the same course are grouped together.
    """
    anomalies: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        if r["grade"] not in _KNOWN_GRADES:
            anomalies.setdefault(r["course_code"], []).append((r["grade"], r["semester"]))
    return anomalies


def print_grade_anomaly_warning(anomalies: dict[str, list[tuple[str, str]]]) -> None:
    """
    Print a prominent warning banner for every transcript row whose grade is
    not recognised by NSU grading policy.

    Consequences spelled out for the admin:
      • The row is treated as a non-passing, non-credit attempt (same as F for
        credit purposes, but the credits DO enter the CGPA denominator with 0 GP,
        dragging the CGPA down — just like a real F would).
      • Any course that depends on this one as a prerequisite will also fail,
        since the course is not in the student's passed_set.
    """
    if not anomalies:
        return
    print()
    print(_btop())
    print(_bline("⚠  UNRECOGNISED GRADE — OUTSIDE NSU GRADING POLICY"))
    print(_bline("The rows below carry a grade not in the NSU scale (A/A-/B+/B/B-/C+/C/C-/D+/D/F/W/I)."))
    print(_bline("Each anomalous row is treated as non-passing (0 credits)."))
    print(_bline("If also in-curriculum, its credits enter the CGPA denominator with 0 GP — same as F."))
    print(_bline("Any courses that require it as a prerequisite will also be blocked."))
    print(_bsep())
    print(_THDR)
    print(_TROW_SEP)
    for code in sorted(anomalies):
        for grade, semester in anomalies[code]:
            status = f"Grade '{grade}' is not a valid NSU grade — treated as non-passing (semester: {semester})"
            print(_trow(code, "—", grade, status))
            print(_TROW_SEP)
    print(_TBOT)
    print(_bbot())
    print()


# ══════════════════════════════════════════════════════════════════════════════
#  Credit computation
# ══════════════════════════════════════════════════════════════════════════════
def compute_total_valid_credits(
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str,dict[str,float]]] = None,
    program_key: Optional[str] = None,
    prereq_map: Optional[dict[str,list]] = None,
    passed_set: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    earned_credits: float = 0.0,
) -> tuple[float,dict[str,float],dict[str,list[dict]],dict[str,str]]:
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(r["course_code"],[]).append(r)
    ncl = get_ncl_labs(program_key)
    # FIX #11: always normalise waived_courses so comparisons are case/space safe
    _waived_n = {normalize_course_code(c) for c in (waived_courses or set())}
    per_course: dict[str,float] = {}
    prereq_failures: dict[str,str] = {}
    for code, att in by_course.items():
        n = normalize_course_code(code)
        if n in ncl:
            per_course[code] = 0.0; continue
        raw_credits = valid_credits_for_course(att)
        if allowed_codes is not None and n not in allowed_codes:
            per_course[code] = 0.0; continue
        if program_credits and program_key and n in program_credits.get(program_key,{}):
            if has_passing_attempt(att):
                raw_credits = program_credits[program_key][n]
            else:
                per_course[code] = 0.0; continue
        if raw_credits==0 and not has_passing_attempt(att):
            per_course[code] = 0.0; continue
        if prereq_map and passed_set is not None and has_passing_attempt(att):
            ok, reason = prereq_satisfied(code, passed_set, prereq_map,
                                          waived_courses=waived_courses,
                                          earned_credits=earned_credits)
            if not ok:
                per_course[code] = 0.0
                prereq_failures[n] = reason; continue
        if n in _waived_n:
            per_course[code] = 0.0; continue
        per_course[code] = raw_credits
    return sum(per_course.values()), per_course, by_course, prereq_failures

def reason_not_counted(
    attempts: list[dict],
    course_code: str = "",
    program_name: str = "",
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str,dict[str,float]]] = None,
    program_key: Optional[str] = None,
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    prereq_failure: Optional[str] = None,
) -> str:
    if not attempts: return "no attempts on transcript"
    n = normalize_course_code(course_code) if course_code else ""
    _waived_n = {normalize_course_code(c) for c in (waived_courses or set())}
    if n in _waived_n:
        return "waived — counts in Credit Completed only (excluded from Credit Counted & CGPA)"
    if core_excluded and n in core_excluded:
        if n in CSE_BIO_INTERNSHIP_SLOT:
            if n == "BIO103L":
                return "1-credit slot claimed by CSE498R/I — only one of BIO103L / CSE498R / CSE498I may count"
            else:  # CSE498R or CSE498I excluded
                return "1-credit slot claimed by BIO103L — only one of BIO103L / CSE498R / CSE498I may count"
        return "choice slot already filled by a higher-grade course from the same group"
    if unselected_electives and n in unselected_electives:
        # Course IS a known elective for this program — never show "not part of curriculum".
        # FIX #13: only show "not selected" if the student actually passed it.
        # Failed/withdrawn electives fall through to the grade-check below so the
        # admin sees the real failure reason instead of a misleading "not selected".
        if has_passing_attempt(attempts):
            return "elective not selected for this audit — may be re-used in future semesters"
        # fall through to prereq and grade checks
    elif allowed_codes is not None and program_name and course_code:
        if n not in allowed_codes:
            if n not in NSU_CATALOG_EXPANDED:
                return "course not offered by NSU — cannot count toward any program"
            return f"not part of {program_name} required curriculum"
    if prereq_failure:
        return prereq_failure
    passing = [a for a in attempts if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"],0))
        prog_cr = (program_credits[program_key].get(n)
                   if program_credits and program_key and n in program_credits.get(program_key,{})
                   else None)
        eff = prog_cr if prog_cr is not None else best["credits"]
        if eff == 0:
            label = "non-credit lab" if n.endswith("L") else "0-credit course"
            return f"{label} — credits not applied toward graduation total"
        return "internal error: has passing attempt but counted 0 (please report)"
    grades = {a["grade"] for a in attempts}
    parts = []
    if "F" in grades: parts.append("failure (F)")
    if "W" in grades: parts.append("withdrawal (W)")
    if "I" in grades: parts.append("incomplete (I)")
    other = grades - PASSING_GRADES - NO_CREDIT_GRADES
    if other: parts.append("unrecognised grade")
    return (" and ".join(parts) + "; no passing retake on record") if parts else "no passing grade"

# ══════════════════════════════════════════════════════════════════════════════
#  Report printing
# ══════════════════════════════════════════════════════════════════════════════
def print_report(
    transcript_path: Path,
    program_name: str,
    total: float,
    per_course: dict[str,float],
    by_course: dict[str,list[dict]],
    required_credits: Optional[int] = None,
    allowed_codes: Optional[Set[str]] = None,
    program_credits: Optional[dict[str,dict[str,float]]] = None,
    program_key: Optional[str] = None,
    major_electives: Optional[list[str]] = None,
    open_elective: str = "",
    free_electives: Optional[list[str]] = None,
    core_excluded: Optional[Set[str]] = None,
    unselected_electives: Optional[Set[str]] = None,
    waiver_applied: bool = False,
    waived_courses: Optional[Set[str]] = None,
    prereq_failures: Optional[dict[str,str]] = None,
    report_level: int = 1,
) -> None:
    major_set = {normalize_course_code(c) for c in (major_electives or [])}
    free_set  = {normalize_course_code(c) for c in (free_electives or [])}
    open_code = normalize_course_code(open_elective) if open_elective else ""
    ncl       = get_ncl_labs(program_key)
    _waived   = waived_courses or set()
    _waived_n = {normalize_course_code(c) for c in _waived}
    credit_completed = total + WAIVER_CREDITS_EACH * len(_waived)

    title = f"LEVEL {report_level} ▸ CREDIT TALLY ENGINE"
    print()
    print(_btop())
    print(_bline(title))
    print(_bsep())
    print(_bline(f"Transcript  :  {transcript_path.name}"))
    print(_bline(f"Program     :  {program_name}"))
    if waiver_applied and _waived:
        print(_bline(f"Waivers     :  {', '.join(sorted(_waived))}  (count in Credit Completed only)"))
    print(_bsep())
    if required_credits is not None:
        cr_ok = "✓ MET" if credit_completed >= required_credits else "✗ NOT MET"
        print(_bline(f"CREDIT COUNTED    :  {total:.1f}   (courses with grades; basis for CGPA)"))
        print(_bline(f"CREDIT COMPLETED  :  {credit_completed:.1f} / {required_credits} required   [{cr_ok}]"))
    else:
        print(_bline(f"CREDIT COUNTED    :  {total:.1f}"))
        print(_bline(f"CREDIT COMPLETED  :  {credit_completed:.1f}"))
    print(_bbot())
    print()

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

    def _status(code: str) -> str:
        n = normalize_course_code(code)
        if n == open_code:
            return "Counted  [Free Elective]" if program_key == "MIC" else "Counted  [Open Elective]"
        if n in free_set:   return "Counted  [Free Elective]"
        if n in major_set:  return "Counted  [Major Elective]"
        return "Counted"

    print("  Courses counted toward graduation:")
    print(_TTOP)
    print(_THDR)
    print(_TROW_SEP)
    for code, cr in counted:
        grade = get_display_grade(by_course[code])
        print(_trow(code, cr, grade, _status(code)))
    print(_TBOT)
    print()

    if excluded or _retake_ghosts:
        print("  Courses not counted (0 credits):")
        print(_TTOP)
        print(_THDR)
        print(_TROW_SEP)
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

# ══════════════════════════════════════════════════════════════════════════════
#  MIC alias / choice helpers
# ══════════════════════════════════════════════════════════════════════════════
def _mic_course_category(code: str) -> Optional[str]:
    n = normalize_course_code(code)
    for cat, codes in MIC_REQUIRED_CATEGORIES.items():
        if n in codes: return cat
    return None

def resolve_mic_aliases(rows: list[dict]) -> dict[str,str]:
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]),[]).append(r)
    exclusions: dict[str,str] = {}
    for code_a, code_b in MIC_ALIAS_PAIRS:
        a, b = normalize_course_code(code_a), normalize_course_code(code_b)
        pa = a in by_course and has_passing_attempt(by_course[a])
        pb = b in by_course and has_passing_attempt(by_course[b])
        if pa and pb:
            ga = GRADE_RANK.get(get_display_grade(by_course[a]),0)
            gb = GRADE_RANK.get(get_display_grade(by_course[b]),0)
            if gb > ga: exclusions[a] = b
            else:       exclusions[b] = a
        elif pa and b in by_course and not pb: exclusions[b] = a
        elif pb and a in by_course and not pa: exclusions[a] = b
    return exclusions

# GED group labels — shown in the prompt header
_GED_GROUP_LABELS: list[str] = [
    "Politics / Government",
    "Economics",
    "Society / Environment",
]

def resolve_cse_choice_groups(rows: list[dict]) -> set[str]:
    """
    For each CSE GED choice group (one slot, pick exactly ONE course):
      - If the student passed only one course from the group → auto-select, no prompt.
      - If they passed multiple → prompt the admin to choose which one counts.
        In NO_INTERACT mode, auto-select the highest-grade one (ties → first in group list).
    Returns: set of course codes to EXCLUDE from the credit tally.
    """
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]),[]).append(r)

    excluded: set[str] = set()

    # Resolve all groups first (asking prompts where needed), then print one clean box.
    resolved_lines: list[str] = []

    for group, label in zip(CSE_GED_CHOICE_GROUPS, _GED_GROUP_LABELS):
        passed = sorted(
            [c for c in group if c in by_course and has_passing_attempt(by_course[c])],
            key=lambda c: GRADE_RANK.get(get_display_grade(by_course[c]), 0),
            reverse=True,  # best grade first → auto-mode picks highest grade
        )
        if len(passed) == 0:
            resolved_lines.append(f"  [{label}]  No passing course found — slot unfilled.")
        elif len(passed) == 1:
            resolved_lines.append(
                f"  [{label}]  {passed[0]}  ({get_display_grade(by_course[passed[0]])})"
                f"  — only option, auto-selected."
            )
        else:
            # Multiple passed — prompt outside the box, then record result
            print()
            print(f"  [{label}]  Student passed multiple courses — pick ONE to count:")
            display = [
                f"{c:<10}  (grade: {get_display_grade(by_course[c])})"
                for c in passed
            ]
            chosen = _prompt_pick("", passed, display=display)
            excluded.update(c for c in passed if c != chosen)
            resolved_lines.append(
                f"  [{label}]  {chosen}  ({get_display_grade(by_course[chosen])})"
                f"  — selected.  Others excluded: {', '.join(sorted(set(passed)-{chosen}))}"
            )

    # Print the complete resolution in a single well-formed box
    print()
    print(_btop())
    print(_bline("CSE GED / UNIVERSITY CORE — CHOICE SLOT RESOLUTION"))
    print(_bline("Each group below is ONE slot.  Only the chosen course counts toward credits."))
    print(_bsep())
    for line in resolved_lines:
        print(_bline(line))
    print(_bbot())
    print()
    return excluded

# ══════════════════════════════════════════════════════════════════════════════
#  Interactive helpers (respect NO_INTERACT flag)
# ══════════════════════════════════════════════════════════════════════════════
def _prompt_pick(prompt: str, options: list[str], display: Optional[list[str]] = None) -> str:
    """Numbered menu; in NO_INTERACT mode auto-selects option[0] (first = best candidate)."""
    labels = display if display and len(display)==len(options) else options
    if NO_INTERACT:
        if prompt: print(prompt)
        print(f"  [auto] → {labels[0]}")
        return options[0]
    while True:
        if prompt: print(prompt)
        for i, label in enumerate(labels,1):
            print(f"  {i}. {label}")
        raw = input("  Enter number: ").strip()
        if raw.isdigit():
            idx = int(raw)-1
            if 0<=idx<len(options): return options[idx]
        print("  Invalid input, please try again.\n")

def _prompt_yes_no(prompt: str) -> bool:
    """Yes/no prompt; in NO_INTERACT mode returns False (conservative default)."""
    if NO_INTERACT:
        print(f"  [auto] {prompt} → No (default in non-interactive mode)")
        return False
    while True:
        raw = input(f"      {prompt} (y/n): ").strip().lower()
        if raw in ("y","yes"): return True
        if raw in ("n","no"):  return False
        print("      Please enter y or n.")

def _course_display(code: str, rows: list[dict]) -> str:
    att = [r for r in rows if normalize_course_code(r["course_code"])==normalize_course_code(code)]
    passing = [a for a in att if is_passing(a["grade"])]
    if passing:
        best = max(passing, key=lambda a: GRADE_RANK.get(a["grade"],0))
        cr = best["credits"]
        return f"{code:<10}  ({int(cr) if cr==int(cr) else cr} cr, {best['grade']})"
    return code

def _get_taken_courses(rows: list[dict]) -> list[str]:
    seen: dict[str,list[dict]] = {}
    for r in rows:
        seen.setdefault(r["course_code"],[]).append(r)
    return [code for code, att in seen.items() if has_passing_attempt(att)]

# ══════════════════════════════════════════════════════════════════════════════
#  MIC University Core choice selection
# ══════════════════════════════════════════════════════════════════════════════
def select_mic_core_choices(rows: list[dict]) -> set[str]:
    by_course: dict[str,list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]),[]).append(r)
    def passed_from(group: list[str]) -> list[str]:
        return [c for c in group if c in by_course and has_passing_attempt(by_course[c])]
    excluded: set[str] = set()
    print("\n" + _btop())
    print(_bline("MIC UNIVERSITY CORE — REQUIRED CHOICE SLOTS"))
    print(_bline("Only ONE course per group counts toward credits."))
    print(_bbot())

    lang_passed = passed_from(MIC_LANGUAGE_CHOICES)
    if len(lang_passed) > 1:
        print("\n  LANGUAGE (4th slot) — student passed both BEN205 and ENG111 (pick one):")
        chosen = _prompt_pick("", lang_passed, display=[_course_display(c,rows) for c in lang_passed])
        excluded.update(c for c in lang_passed if c!=chosen)
        print(f"  ✓ Language slot: {chosen} selected.")
    elif len(lang_passed)==1:
        print(f"\n  Language (4th slot): {lang_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Language (4th slot): no passing course found (BEN205 or ENG111 required).")

    hum_passed = passed_from(MIC_HUMANITIES_CHOICES)
    if len(hum_passed) > 1:
        print("\n  HUMANITIES — student passed multiple courses (pick one):")
        chosen = _prompt_pick("", hum_passed, display=[_course_display(c,rows) for c in hum_passed])
        excluded.update(c for c in hum_passed if c!=chosen)
        print(f"  ✓ Humanities slot: {chosen} selected.")
    elif len(hum_passed)==1:
        print(f"\n  Humanities: {hum_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Humanities: no passing course found.")

    soc_passed = passed_from(MIC_SOCIAL_CHOICES)
    if len(soc_passed) > 1:
        print("\n  SOCIAL SCIENCES — student passed multiple courses (pick one):")
        chosen = _prompt_pick("", soc_passed, display=[_course_display(c,rows) for c in soc_passed])
        excluded.update(c for c in soc_passed if c!=chosen)
        print(f"  ✓ Social Sciences slot: {chosen} selected.")
    elif len(soc_passed)==1:
        print(f"\n  Social Sciences: {soc_passed[0]} — only option, auto-selected.")
    else:
        print("\n  Social Sciences: no passing course found.")

    passed_pairs = [
        (t,l) for t,l in MIC_SCIENCE_CHOICES
        if t in by_course and has_passing_attempt(by_course[t])
        and l in by_course and has_passing_attempt(by_course[l])
    ]
    if len(passed_pairs) > 1:
        print("\n  SCIENCE — student passed courses from multiple pairs (pick one pair):")
        pair_opts = [f"{t}+{l}" for t,l in passed_pairs]
        chosen_str = _prompt_pick("", pair_opts, display=[
            f"{t} ({get_display_grade(by_course[t])})  +  {l} ({get_display_grade(by_course.get(l,[]))})"
            for t,l in passed_pairs
        ])
        chosen_theory, chosen_lab = chosen_str.split("+")
        for theory, lab in passed_pairs:
            if theory != chosen_theory:
                excluded.add(theory); excluded.add(lab)
        print(f"  ✓ Science slot: {chosen_theory} + {chosen_lab} selected.")
    elif len(passed_pairs)==1:
        t,l = passed_pairs[0]
        print(f"\n  Science: {t} + {l} — only option, auto-selected.")
    else:
        print("\n  Science: no complete pair found (both theory and lab must be passed).")
    print()
    return excluded

# ══════════════════════════════════════════════════════════════════════════════
#  Elective selection
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
#  BIO103L / Internship choice resolution (CSE only)
# ══════════════════════════════════════════════════════════════════════════════
def resolve_cse_bio_internship_choice(rows: list[dict]) -> set[str]:
    """
    BIO103L and CSE498R/CSE498I occupy the same 1-credit slot in the CSE program.
    Exactly ONE may count toward graduation credits and CGPA; the other is excluded.

    Logic:
      - Only one side on record  → auto-select it, no prompt.
      - Both sides on record     → prompt the admin to choose.
      - Neither on record        → no action (deficiency check will catch it).

    In NO_INTERACT mode, CSE498R/I is auto-preferred over BIO103L.

    Returns: set of course codes to EXCLUDE from the credit tally (added to core_excluded).
    """
    by_course: dict[str, list[dict]] = {}
    for r in rows:
        by_course.setdefault(normalize_course_code(r["course_code"]), []).append(r)

    internship_passed = [
        c for c in ("CSE498R", "CSE498I")
        if c in by_course and has_passing_attempt(by_course[c])
    ]
    bio_passed = "BIO103L" in by_course and has_passing_attempt(by_course["BIO103L"])

    excluded: set[str] = set()

    print()
    print(_btop())
    print(_bline("CSE INTERNSHIP / BIO103L — 1-CREDIT SLOT"))
    print(_bline("BIO103L (lab) and CSE498R/I (internship/research) fill the same 1-credit slot."))
    print(_bline("Only ONE counts toward graduation credits and CGPA; the other is excluded."))
    print(_bsep())

    if not internship_passed and not bio_passed:
        print(_bline("  Neither BIO103L nor CSE498R/I found with a passing grade — slot unfilled."))

    elif bio_passed and not internship_passed:
        print(_bline("  BIO103L — only option on record, auto-selected for the 1-credit slot."))
        excluded.update({"CSE498R", "CSE498I"})

    elif internship_passed and not bio_passed:
        chosen = internship_passed[0]
        grade  = get_display_grade(by_course[chosen])
        print(_bline(f"  {chosen}  ({grade}) — only option on record, auto-selected for the 1-credit slot."))
        excluded.add("BIO103L")

    else:
        # Both sides present — prompt (internship listed first so NO_INTERACT prefers it)
        options = internship_passed + ["BIO103L"]
        display = [
            f"{c:<10}  (grade: {get_display_grade(by_course[c])})"
            for c in options
        ]
        print(_bline("  Both BIO103L and CSE498R/I passed — choose ONE to count:"))
        print(_bsep())
        if NO_INTERACT:
            for i, label in enumerate(display, 1):
                print(_bline(f"  {i}. {label}"))
            print(_bline(f"  [auto] → {display[0]}"))
            chosen = options[0]
        else:
            while True:
                for i, label in enumerate(display, 1):
                    print(_bline(f"  {i}. {label}"))
                print(_bsep())
                raw = input("      Enter number: ").strip()
                if raw.isdigit() and 0 <= int(raw) - 1 < len(options):
                    chosen = options[int(raw) - 1]
                    break
                print(_bline("  Invalid input, please try again."))
                print(_bsep())
        excluded = set(options) - {chosen}
        grade   = get_display_grade(by_course[chosen])
        print(_bline(f"  ✓ {chosen}  ({grade}) selected for the 1-credit slot."))
        excl_str = ", ".join(sorted(excluded))
        print(_bline(f"    Excluded: {excl_str}"))

    print(_bbot())
    return excluded


def select_electives_cse(
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    core_excluded: Optional[Set[str]] = None,
) -> tuple[list[str],str,list[str]]:
    _waived    = {normalize_course_code(c) for c in (waived_courses or set())}
    _core_excl = {normalize_course_code(c) for c in (core_excluded or set())}
    taken   = set(_get_taken_courses(rows))

    # Resolve cross-listed alias pairs: if a student has both, exclude the lower-grade one
    # so only one slot is occupied, preventing double-counting of the same course.
    _trail_alias_excl: set[str] = set()
    for code_a, code_b in CSE_TRAIL_ALIAS_PAIRS:
        if code_a in taken and code_b in taken:
            ga = GRADE_RANK.get(get_display_grade([r for r in rows if normalize_course_code(r["course_code"])==code_a]), 0)
            gb = GRADE_RANK.get(get_display_grade([r for r in rows if normalize_course_code(r["course_code"])==code_b]), 0)
            excl = code_b if ga >= gb else code_a
            _trail_alias_excl.add(excl)
    taken -= _trail_alias_excl

    trail_taken: dict[str,list[str]] = {
        t: [c for c in codes if c in taken]
        for t, codes in CSE_TRAILS.items()
        if any(c in taken for c in codes)
    }
    all_trail_codes = {c for trail in CSE_TRAILS.values() for c in trail}

    print("\n" + _btop())
    print(_bline("CSE MAJOR ELECTIVE SELECTION"))
    print(_bline("Rule: 2 courses from primary trail + 1 from secondary trail + 1 open elective"))
    print(_bbot())

    print("\n  Elective courses found in your transcript:\n")
    for trail_name, codes in trail_taken.items():
        print(f"    [{trail_name}]")
        for c in codes: print(f"      {_course_display(c,rows)}")
    open_preview = sorted([
        c for c in taken
        if normalize_course_code(c) not in _waived
        and normalize_course_code(c) not in CSE_INTERNSHIP_RESEARCH
        and normalize_course_code(c) not in _core_excl
        and normalize_course_code(c) in NSU_CATALOG_EXPANDED
        and (c in all_trail_codes
             or c not in (allowed_codes or set())
             or normalize_course_code(c) in CSE_MINOR_COURSES)
    ])
    if open_preview:
        print(f"\n    [Open Elective candidates — trail courses + outside-curriculum NSU courses + minor courses]")
        for c in open_preview: print(f"      {_course_display(c,rows)}")
    print()

    major_electives: list[str] = []
    eligible_primary = [t for t,c in trail_taken.items() if len(c)>=2] or list(trail_taken.keys())
    if not eligible_primary:
        print("  No elective courses found in transcript for CSE trails.")
        return [],"",[], _trail_alias_excl

    primary_name = _prompt_pick("\nSelect your PRIMARY trail (need 2 courses):", eligible_primary)
    primary_pool = trail_taken[primary_name]
    print(f"\nCourse 1 of 2 from '{primary_name}':")
    c1 = _prompt_pick("", primary_pool, display=[_course_display(c,rows) for c in primary_pool])
    major_electives.append(c1)
    remaining_primary = [c for c in primary_pool if c!=c1]
    if remaining_primary:
        print(f"\nCourse 2 of 2 from '{primary_name}':")
        c2 = _prompt_pick("", remaining_primary, display=[_course_display(c,rows) for c in remaining_primary])
        major_electives.append(c2)
    else:
        print(f"  Only one course in '{primary_name}' from transcript — counting {c1} only.")

    secondary_opts = [t for t in trail_taken if t != primary_name]
    open_elective = ""
    if secondary_opts:
        sec_name = _prompt_pick("\nSelect your SECONDARY trail (1 course):", secondary_opts)
        sec_pool = trail_taken[sec_name]
        print(f"\n1 course from '{sec_name}':")
        c3 = _prompt_pick("", sec_pool, display=[_course_display(c,rows) for c in sec_pool])
        major_electives.append(c3)

    open_pool = sorted([
        c for c in taken
        if normalize_course_code(c) not in _waived
        and normalize_course_code(c) not in CSE_INTERNSHIP_RESEARCH
        and normalize_course_code(c) not in _core_excl
        and normalize_course_code(c) in NSU_CATALOG_EXPANDED
        and c not in set(major_electives)
        and (c in all_trail_codes
             or c not in (allowed_codes or set())
             or normalize_course_code(c) in CSE_MINOR_COURSES)
    ])
    if open_pool:
        print("\nSelect your OPEN ELECTIVE (unselected trail + outside-curriculum NSU courses):")
        open_elective = _prompt_pick("", open_pool, display=[_course_display(c,rows) for c in open_pool])
    else:
        print("  No outside-curriculum courses found in transcript for open elective.")
    return major_electives, open_elective, [], _trail_alias_excl

def select_electives_mic(rows: list[dict]) -> tuple[list[str],str,list[str],set]:
    taken = set(_get_taken_courses(rows))
    _major_core_req = MIC_REQUIRED_CATEGORIES.get("Major Core",set())
    major_pool  = [c for c in MIC_ELECTIVES if c in taken and c not in _major_core_req]
    _major_pool_n = {normalize_course_code(c) for c in major_pool}
    free_avail  = [c for c in taken
                   if normalize_course_code(c) not in _major_pool_n
                   and _mic_course_category(c) is None
                   and normalize_course_code(c) in NSU_CATALOG_EXPANDED]

    print("\n" + _btop())
    print(_bline("MIC ELECTIVE SELECTION"))
    print(_bline("Rule: 3 major electives + 3 free electives"))
    print(_bbot())
    print("\n  Available major elective courses:\n")
    for c in major_pool: print(f"    {_course_display(c,rows)}")
    if not major_pool: print("    (none)")
    print("\n  Free elective candidates (outside-curriculum + unselected major electives):\n")
    for c in free_avail+major_pool: print(f"    {_course_display(c,rows)}")
    if not free_avail and not major_pool: print("    (none)")
    print()

    major_electives: list[str] = []
    remaining = list(major_pool)
    for i in range(1,4):
        if not remaining: print(f"  No more elective courses (have {i-1} of 3)."); break
        c = _prompt_pick(f"\nMajor elective {i} of 3:", remaining,
                         display=[_course_display(x,rows) for x in remaining])
        major_electives.append(c)
        remaining = [x for x in remaining if x!=c]

    free_pool   = free_avail + [c for c in major_pool if c not in set(major_electives) and c not in free_avail]
    free_pool   = [c for c in free_pool if c not in set(major_electives)]
    open_elect  = ""
    free_extras: list[str] = []
    if not free_pool:
        print("\n  No free elective courses available in transcript.")
    else:
        print(f"\nSelect 3 FREE ELECTIVES:\n")
        for i in range(1, 4):
            if not free_pool:
                print(f"  No more courses available (selected {i - 1} of 3).")
                break
            c = _prompt_pick(f"Free elective {i} of 3:", free_pool,
                             display=[_course_display(x, rows) for x in free_pool])
            if i == 1:
                open_elect = c
            else:
                free_extras.append(c)
            free_pool = [x for x in free_pool if x != c]
    return major_electives, open_elect, free_extras, set()

def select_electives(
    program_key: str,
    rows: list[dict],
    allowed_codes: Optional[Set[str]] = None,
    waived_courses: Optional[Set[str]] = None,
    core_excluded: Optional[Set[str]] = None,
) -> tuple[list[str],str,list[str],set]:
    if program_key == "CSE": return select_electives_cse(rows, allowed_codes=allowed_codes,
                                                          waived_courses=waived_courses,
                                                          core_excluded=core_excluded)
    if program_key == "MIC": return select_electives_mic(rows)
    return [],"",[],set(),

def print_elective_summary(
    major_electives: list[str],
    open_elective: str,
    program_key: str,
    free_electives: Optional[list[str]] = None,
    rows: Optional[list[dict]] = None,
    prereq_failures: Optional[dict] = None,
) -> None:
    print()
    print(_btop())
    print(_bline("SELECTED ELECTIVES  (included in credit tally)"))
    print(_bsep())
    _pf = {normalize_course_code(c) for c in (prereq_failures or {}).keys()}
    for code in major_electives:
        warn = "  ⚠ prereq not met — will NOT count" if normalize_course_code(code) in _pf else ""
        print(_bline(f"  ▸ {code}   [Major Elective]{warn}"))
    for code in (free_electives or []):
        warn = "  ⚠ prereq not met — will NOT count" if normalize_course_code(code) in _pf else ""
        print(_bline(f"  ▸ {code}   [Free Elective]{warn}"))
    if open_elective:
        open_n = normalize_course_code(open_elective)
        open_minor_tag = ""
        if open_n in CSE_MINOR_MATH:
            open_minor_tag = "  ★ Minor in Math"
        elif open_n in CSE_MINOR_PHYSICS:
            open_minor_tag = "  ★ Minor in Physics"
        label = "Free Elective" if program_key=="MIC" else "Open Elective"
        warn = "  ⚠ prereq not met — will NOT count" if open_n in _pf else ""
        print(_bline(f"  ▸ {open_elective}   [{label}]{open_minor_tag}{warn}"))
    print(_bbot())
    print()

    # ── Minor Program box (CSE only) ─────────────────────────────────────────
    if program_key == "CSE" and rows is not None:
        # Exclude prereq-failed courses — they don't count toward credits
        # so they cannot count toward minor completion either.
        _pf_minor = {normalize_course_code(c) for c in (_pf or set())}
        taken_norm = {normalize_course_code(r["course_code"]) for r in rows
                      if r.get("grade") in PASSING_GRADES
                      and normalize_course_code(r["course_code"]) not in _pf_minor}
        math_taken    = sorted(taken_norm & CSE_MINOR_MATH)
        physics_taken = sorted(taken_norm & CSE_MINOR_PHYSICS)

        if math_taken or physics_taken:
            open_n = normalize_course_code(open_elective) if open_elective else ""
            print(_btop())
            print(_bline("MINOR PROGRAM(S) DETECTED"))
            print(_bsep())

            if math_taken:
                # School Core courses already required — they're prereqs not extras
                MATH_CORE = {"MAT120","MAT125","MAT130","MAT250"}
                needed_extra = 3   # need 3 additional beyond school core
                extras = [c for c in math_taken if c not in MATH_CORE]
                complete = len(extras) >= needed_extra
                status = "✓ COMPLETE" if complete else f"IN PROGRESS  ({len(extras)}/{needed_extra} additional courses done)"
                print(_bline(f"  Minor in Mathematics (21 credits)   —   {status}"))
                print(_bline(f"  School Core (already required): MAT120, MAT125, MAT130, MAT250"))
                print(_bline(f"  Additional courses taken: {', '.join(extras) if extras else 'none yet'}"))
                if open_n in CSE_MINOR_MATH:
                    print(_bline(f"  ★ {open_elective} counted as Open Elective toward graduation"))
                if physics_taken:
                    print(_bsep())

            if physics_taken:
                PHYS_CHOICE = {"PHY310","PHY440"}
                needed_extra = 4   # PHY230/240/250/260 + one of PHY310/PHY440
                has_choice = bool(taken_norm & PHYS_CHOICE)
                base_done  = [c for c in physics_taken if c not in PHYS_CHOICE]
                choice_done = [c for c in physics_taken if c in PHYS_CHOICE]
                total_done = len(base_done) + (1 if has_choice else 0)
                complete = total_done >= 5  # PHY230+240+250+260 + one choice = 5
                status = "✓ COMPLETE" if complete else f"IN PROGRESS  ({total_done}/5 courses done)"
                print(_bline(f"  Minor in Physics (15 credits)   —   {status}"))
                print(_bline(f"  Courses taken: {', '.join(physics_taken)}"))
                if choice_done:
                    print(_bline(f"  Elective slot (PHY310 or PHY440): {choice_done[0]} ✓"))
                else:
                    print(_bline(f"  Elective slot (PHY310 or PHY440): not yet taken"))
                if open_n in CSE_MINOR_PHYSICS:
                    print(_bline(f"  ★ {open_elective} counted as Open Elective toward graduation"))

            print(_bbot())
            print()

# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main() -> int:
    global NO_INTERACT
    parser = argparse.ArgumentParser(
        description="Level 1: Credit Tally Engine — total valid credits from transcript."
    )
    parser.add_argument("transcript",         type=Path, help="Path to transcript CSV")
    parser.add_argument("program_name",       type=str,  help="Program name: CSE or MIC")
    parser.add_argument("program_knowledge",  type=Path, help="Path to program knowledge markdown")
    parser.add_argument("--no-interact",      action="store_true",
                        help="Non-interactive mode: auto-select best options (for AI agent / pipeline use)")
    args = parser.parse_args()
    NO_INTERACT = args.no_interact

    if not args.transcript.exists():
        print(f"  Error: transcript not found: {args.transcript}", file=sys.stderr)
        return 1

    program_key = (args.program_name or "").strip().upper()
    # FIX #6: Validate program name early — fail fast with a clear message
    if program_key not in ("CSE","MIC"):
        print(f"\n  Error: unsupported program '{args.program_name}'.", file=sys.stderr)
        print(  "  Supported programs: CSE, MIC", file=sys.stderr)
        return 1

    program_codes, program_credits = load_program_courses(args.program_knowledge)
    allowed_codes     = set(program_codes.get(program_key,set()))
    credits_by_program = program_credits

    # Waiver check
    waived_courses: Set[str] = set()
    print()
    print(_btop())
    print(_bline("WAIVER CHECK"))
    print(_bline("Waived courses count toward Credit Completed only (not Credit Counted or CGPA)."))
    print(_bsep())
    print(_bline(""))
    if _prompt_yes_no("Is ENG102 waived for this student?"):
        waived_courses.add("ENG102")
        print(_bline("  → ENG102 waived."))
    else:
        print(_bline("  → ENG102 not waived (grade counts in Credit Counted and CGPA)."))
    if _prompt_yes_no("Is MAT112 waived for this student?"):
        waived_courses.add("MAT112")
        print(_bline("  → MAT112 waived."))
    else:
        print(_bline("  → MAT112 not waived (grade counts in Credit Counted and CGPA)."))
    num_waivers    = len(waived_courses)
    required_credits = get_required_credits_for_waivers(program_key, num_waivers)
    print(_bline(f"  Required credits for {program_key}: {required_credits}  "
                 f"(based on {num_waivers} waiver(s))"))
    print(_bbot())
    waiver_applied = bool(waived_courses)

    if program_key == "MIC":
        _mic_core_all   = set().union(*MIC_REQUIRED_CATEGORIES.values())
        _purely_elective = set(MIC_ELECTIVES) - _mic_core_all
        allowed_codes   = allowed_codes - _purely_elective

    rows = load_transcript(args.transcript)

    # Grade anomaly check: warn immediately after loading — before any computation
    grade_anomalies = detect_grade_anomalies(rows)
    print_grade_anomaly_warning(grade_anomalies)

    core_excluded: Set[str] = set()
    if program_key == "MIC":
        core_excluded  = select_mic_core_choices(rows)
        alias_excl     = resolve_mic_aliases(rows)
        if alias_excl:
            print("\n  SHLS Core alias resolution (equivalent course pairs):")
            for excl, kept in alias_excl.items():
                print(f"    {excl} excluded — {kept} already satisfies this slot.")
            print()
        core_excluded = core_excluded | set(alias_excl.keys())
        allowed_codes = allowed_codes - core_excluded

    if program_key == "CSE":
        cse_excl = resolve_cse_choice_groups(rows)
        core_excluded = core_excluded | cse_excl
        allowed_codes = allowed_codes - cse_excl
        bio_intern_excl = resolve_cse_bio_internship_choice(rows)
        core_excluded = core_excluded | bio_intern_excl
        allowed_codes = allowed_codes - bio_intern_excl

    all_elective_candidates: Set[str] = (
        {c for trail in CSE_TRAILS.values() for c in trail} if program_key=="CSE"
        else set(MIC_ELECTIVES)
    )

    major_electives, open_elective, free_electives, trail_alias_excl = select_electives(
        program_key, rows, allowed_codes=allowed_codes, waived_courses=waived_courses,
        core_excluded=core_excluded)
    all_selected = set(major_electives)|set(free_electives)|({open_elective} if open_elective else set())
    unselected_electives = all_elective_candidates - all_selected
    # FIX: also subtract unselected_electives — trail courses not chosen must not count toward credits
    allowed_codes = (allowed_codes | all_selected) - trail_alias_excl - unselected_electives

    # Credit mismatch check: warn if transcript credits differ from program.md
    credit_mismatches = detect_credit_mismatches(
        rows, credits_by_program, program_key, allowed_codes=allowed_codes)
    print_credit_mismatch_warning(credit_mismatches)

    pkey       = program_key
    prereq_map = CSE_PREREQS if pkey=="CSE" else MIC_PREREQS
    passed_set = build_passed_set(rows, prereq_map=prereq_map, waived_courses=waived_courses)
    baseline   = compute_baseline_credits(rows, allowed_codes, credits_by_program, pkey)

    total, per_course, by_course, prereq_failures = compute_total_valid_credits(
        rows, allowed_codes=allowed_codes, program_credits=credits_by_program,
        program_key=pkey, prereq_map=prereq_map, passed_set=passed_set,
        waived_courses=waived_courses, earned_credits=baseline,
    )

    # Print elective summary AFTER prereq computation so prereq warnings are shown
    print_elective_summary(major_electives, open_elective, program_key, free_electives=free_electives,
                           rows=rows, prereq_failures=prereq_failures)
    print_report(
        args.transcript, args.program_name, total, per_course, by_course,
        required_credits, allowed_codes=allowed_codes,
        program_credits=credits_by_program, program_key=pkey,
        major_electives=major_electives, open_elective=open_elective,
        free_electives=free_electives, core_excluded=core_excluded,
        unselected_electives=unselected_electives, waiver_applied=waiver_applied,
        waived_courses=waived_courses, prereq_failures=prereq_failures,
        report_level=1,
    )
    return 0

if __name__ == "__main__":
    sys.exit(main())