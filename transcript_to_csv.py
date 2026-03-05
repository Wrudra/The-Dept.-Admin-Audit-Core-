#!/usr/bin/env python3
"""
transcript_to_csv.py

Converts NSU official transcripts (PDF or image: JPEG, PNG, TIFF, BMP) to the
CSV format expected by audit_l1 / audit_l2 / audit_l3.

Output columns: Course_Code, Credits, Grade, Semester

Strategy
--------
NSU transcripts are printed with a two-column layout (older semesters in the
left column, recent semesters in the right column).  Plain OCR merges both
columns into single lines, making naïve line-by-line parsing unreliable.

This tool splits each page image into left and right halves, OCRs them
independently, then parses each half with its own semester-context tracker.
On single-column pages (or images that don't split cleanly) the full-width
OCR result is used as a fallback.

Dependencies (one-time setup)
------------------------------
    pip install pillow pytesseract pdf2image
    # macOS:  brew install tesseract poppler
    # Ubuntu: sudo apt install tesseract-ocr poppler-utils

Usage
-----
    python transcript_to_csv.py Transcript.pdf
    python transcript_to_csv.py Transcript2.jpeg -o output.csv
    python transcript_to_csv.py Transcript.pdf --debug
"""

import csv
import re
import sys
import argparse
from pathlib import Path

# ── optional imports ───────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageEnhance
    import pytesseract
except ImportError:
    sys.exit("ERROR: Run:  pip install pillow pytesseract")

try:
    from pdf2image import convert_from_path
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False

# ── constants ──────────────────────────────────────────────────────────────────
VALID_GRADES: set[str] = {
    "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F", "W", "I", "X"
}
# Standard NSU credit values
STANDARD_CREDITS = {"0.0", "1.0", "1.5", "3.0"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# Semester header: Fall / Spring / Summer / Intersession + plausible year.
# No trailing boundary: '20(?:0\d|1\d|2\d)' captures exactly 4 digits so
# '202250' correctly yields '2022' even though extra digits follow.
_SEMESTER_PAT = r'\b(Fall|Spring|Summer|Intersession)\s+(20(?:0\d|1\d|2\d))'
SEMESTER_RE   = re.compile(_SEMESTER_PAT, re.IGNORECASE)

# NSU course code: exactly 3 uppercase letters + 3 digits (tolerates I/l/O/S noise)
# + optional trailing letter (e.g. CSE115L, PHY108L, CSE499A)
# NSU uses exclusively 3-letter department prefixes; requiring {3} prevents
# false positives like "AS130" from watermark OCR noise.
_CODE_BODY     = r'[A-Z]{3}[0-9IlOSL]{3}[A-Z]?(?![0-9])'
COURSE_CODE_RE = re.compile(r'\b(' + _CODE_BODY + r')\b')

# Spaced course code produced by OCR: e.g. "PHY 107" "PHY 108L"
_SPACED_CODE_RE = re.compile(r'\b([A-Z]{3})\s([0-9]{3}[A-Z]?)\b')

# Grade pattern: allow 't' as OCR artefact for '+' (B+ → Bt, C+ → Ct, D+ → Dt)
_GRADE_SET = r'(?:A[-]?|B[+\-t]?|C[+\-t]?|D[+\-t]?|[FWIX])'

# Primary: credit  grade  [CC]  [CP]  at end of line.
# \s* between credit and grade handles fused OCR like '730A'.
END_RE = re.compile(
    r'(\d{1,3}\.?\d*)\s*'          # credit
    r'(' + _GRADE_SET + r')'       # grade
    r'(?:\s+(\d{1,3}\.?\d*))?'    # CC - captured for credit fallback
    r'(?:\s+\d{1,3}\.?\d*)?'      # CP - not captured
    r'\s*$'
)

# Fallback: when the credit is completely unreadable (e.g. 'TBO A- 3.0 3.0'),
# match grade  CC  [CP]  at end of line and use CC as credit.
END_RE_FALLBACK = re.compile(
    r'\b(' + _GRADE_SET + r')'     # grade (word-bounded)
    r'\s+(\d{1,3}\.?\d*)'        # CC - used as credit
    r'(?:\s+\d{1,3}\.?\d*)?'     # CP - not captured
    r'\s*$'
)

# Intersession keyword without a valid 4-digit year (OCR garbles the year)
# Used as a fallback when SEMESTER_RE fails to find a valid Intersession header.
_INTERSESSION_WORD_RE = re.compile(r'\bIntersession\b', re.IGNORECASE)

# Lines/tokens to skip entirely
_SKIP_RE = re.compile(
    r'Semester\s+Credit|TGPA|CGPA|Summary|Total\s+Credit|Grade\s+Point'
    r'|Course\s+Title|End\s+of\s+Transcript|Controller|Official\s+Transcript'
    r'|Student\s+Name|Student\s+ID|Date\s+of\s+Birth|Degree\s+Objective'
    r'|Degree\s+Status|Credits\s+Accept|Courses\s+Waived',
    re.IGNORECASE
)

# ── image utilities ────────────────────────────────────────────────────────────

def _enhance(img: "Image.Image") -> "Image.Image":
    gray      = img.convert("L")
    enhanced  = ImageEnhance.Contrast(gray).enhance(2.2)
    sharpened = ImageEnhance.Sharpness(enhanced).enhance(1.5)
    return sharpened


def _ocr(img: "Image.Image") -> str:
    processed = _enhance(img)
    return pytesseract.image_to_string(processed, config="--oem 3 --psm 6")


def _get_page_images(src: Path) -> list:
    """Return a list of PIL Image objects (one per page / one for the image)."""
    ext = src.suffix.lower()
    if ext == ".pdf":
        if not _HAS_PDF:
            sys.exit("ERROR: Run:  pip install pdf2image   +   brew install poppler")
        return convert_from_path(str(src), dpi=300)
    if ext in IMAGE_EXTS:
        return [Image.open(str(src))]
    sys.exit(f"ERROR: Unsupported file type '{ext}'")


def _split_columns(img: "Image.Image") -> tuple:
    """
    Return (left_img, right_img) for a two-column page, found by locating
    the vertical gap with the least dark pixels in the centre third.
    Falls back to a 50/50 split if no clear gap is detected.
    """
    w, h = img.size
    gray = img.convert("L")

    # Search for the column divider in the middle 20-80% of the width
    lo, hi = int(w * 0.20), int(w * 0.80)
    col_darkness = []
    for x in range(lo, hi):
        # count pixels darker than 128 (ink)
        dark = sum(1 for y in range(0, h, 4) if gray.getpixel((x, y)) < 128)
        col_darkness.append((dark, x))

    # The column with least dark pixels in the centre is the gutter
    _, split_x = min(col_darkness)

    left  = img.crop((0, 0, split_x, h))
    right = img.crop((split_x, 0, w, h))
    return left, right

# ── text normalisation ─────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    """Clean up common OCR artefacts."""
    text = re.sub(r'_+', ' ', text)               # underscores -> spaces
    text = re.sub(r'\t+', ' ', text)              # tabs -> spaces
    # Fix truncated season words OCR sometimes drops a letter from
    text = re.sub(r'\bSprin\b', 'Spring', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFal\b',   'Fall',   text, flags=re.IGNORECASE)
    text = re.sub(r'\bSumme\b', 'Summer', text, flags=re.IGNORECASE)
    # Fix spaced course codes: 'PHY 107' -> 'PHY107'
    text = _SPACED_CODE_RE.sub(lambda m: m.group(1) + m.group(2), text)
    # Strip punctuation that disrupts credit/grade matching.
    # NOTE: '+' and '-' are intentionally kept — they appear in valid grades (B+, A-).
    text = re.sub(r"[,;|()\[\]=/\\°¥©®™•·!%'\"*`~@#$^&{}]+", ' ', text)
    # Fix OCR noise in numeric contexts
    text = re.sub(r'(\d)S(?=\s|$)', r'\1', text)   # '15S A' -> '15 A'  (5->S OCR)
    text = re.sub(r'(\d)o', r'\g<1>0', text)        # '1o'   -> '10'    (0->o OCR)
    text = re.sub(r'(\d)Q', r'\g<1>0', text)        # '3Q'   -> '30'    (Q→0 on '3.0' sans dot)
    # Insert a space between two fused decimal numbers: '3.03.0' -> '3.0 3.0'
    text = re.sub(r'(?<=\.\d)(?=\d\.)', ' ', text)
    # Grade letter immediately followed by noise 'L': strip the L so that
    # 'AL' is read as grade 'A' by downstream patterns.
    text = re.sub(r'\b([ABCDF])L\b', r'\1', text)
    text = re.sub(r' {2,}', ' ', text)            # collapse multiple spaces
    return text


def _normalize_grade(raw: str) -> str:
    """Fix OCR artefacts in a captured grade string."""
    g = raw.strip()
    # '+' is sometimes OCR'd as 't' (B+ → Bt, C+ → Ct, D+ → Dt)
    if len(g) == 2 and g[1] == 't':
        g = g[0] + '+'
    return g


def _parse_course_code(raw: str) -> str:
    """
    Normalise a raw OCR'd token that looks like a course code.
    Splits into  prefix + 3-digit-section + optional-suffix  and fixes noise.
    """
    m = re.match(r'^([A-Z]{3})([0-9IlOSL]{3})([A-Z]?)$', raw.strip())
    if not m:
        return raw
    digits = (
        m.group(2)
        .replace('I', '1').replace('l', '1')
        .replace('O', '0').replace('S', '5').replace('L', '1')
    )
    return m.group(1) + digits + m.group(3)


def _normalize_credit(raw: str, cc_raw: str = None) -> str:
    """
    Return a canonical credit string from a possibly noisy OCR value.

    Handles common artefacts:
      '30'  -> '3.0'    '10'  -> '1.0'    '15' -> '1.5'    '00' -> '0.0'
      '730' -> '3.0'    '73.0'-> '3.0'    '0.' -> '0.0'    '0'  -> '0.0'

    Special case: when the tentative result is '0.0' but the CC value on the
    same line is a non-zero standard credit, we prefer CC.  This corrects the
    frequent OCR artefact where the column-split cuts 'X.' off the front of
    'X.0', leaving only '0', while the CC column still shows the full value.
    """
    s = raw.strip()

    # Compute tentative value from raw alone
    def _tentative(v: str) -> str:
        if v in STANDARD_CREDITS:
            return v
        if v == '0':
            return '0.0'
        if v.endswith('.') and v[:-1].isdigit():
            return v + '0'
        if len(v) == 2 and v.isdigit():
            return f"{v[0]}.{v[1]}"
        for known in ('3.0', '1.5', '1.0', '0.0'):
            if known in v:
                return known
        _TAIL = {'30': '3.0', '10': '1.0', '15': '1.5', '00': '0.0'}
        # Only apply the TAIL heuristic for short values (≤3 chars).
        # Longer values like '7310' could incorrectly map to '1.0' via TAIL['10'];
        # they are better handled by the CC fallback below.
        if 2 <= len(v) <= 3 and v[-2:] in _TAIL:
            return _TAIL[v[-2:]]
        # Special case: 4-digit symmetric string like '3030' = CC+CP fused without space.
        # Only applies when both halves are identical (CC == CP = same credit value).
        if len(v) == 4 and v.isdigit() and v[:2] == v[2:] and v[2:] in _TAIL:
            return _TAIL[v[2:]]
        return v  # best effort

    result = _tentative(s)

    # If tentative is 0.0 or not a standard credit, and CC has a real value,
    # prefer CC.  Cases:
    #   '0.0' + CC='3.0'  -> column-split OCR cut off 'X.' leaving '0'
    #   '4.0' + CC='1.0'  -> garbled credit (OCR artefact like '40' -> '4.0')
    if cc_raw:
        cc = _tentative(cc_raw.strip())
        if cc in STANDARD_CREDITS and cc != '0.0':
            if result not in STANDARD_CREDITS or result == '0.0':
                return cc

    return result

# ── core parser ────────────────────────────────────────────────────────────────

def _parse_column(text: str, debug: bool = False) -> list[dict]:
    """
    Parse a single OCR column text and return a list of row dicts:
      { 'Course_Code', 'Credits', 'Grade', 'Semester' }
    """
    text = _normalize_text(text)
    rows = []
    current_semester = None
    # Track the highest year seen so far; used to filter anomalously old semester matches.
    _max_year_seen = 0

    # Pre-merge wrapped lines: if a line ends mid-number (no grade found)
    # and the NEXT line starts with a digit, merge them.
    raw_lines = text.splitlines()
    lines = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        # Merge continuation if this line ends with a bare number and next starts with digit
        if (lines
                and END_RE.search(lines[-1]) is None
                and re.match(r'^\d', line)
                and not SEMESTER_RE.search(line)
                and not COURSE_CODE_RE.search(line)):
            lines[-1] = lines[-1] + ' ' + line
            i += 1
            continue
        lines.append(line)
        i += 1

    for line in lines:
        if not line:
            continue
        if _SKIP_RE.search(line):
            continue

        # ── semester header detection ────────────────────────────────────────
        sem_matches = list(SEMESTER_RE.finditer(line))
        if sem_matches:
            # Use the LAST semester pattern seen on this line
            m = sem_matches[-1]
            candidate_sem  = f"{m.group(1).capitalize()} {m.group(2)}"
            candidate_year = int(m.group(2))
            # Reject semester matches whose year is implausibly far in the past.
            # Threshold: if we've already seen a year Y and this match gives a
            # year more than 2 years earlier, it's almost certainly OCR noise
            # (e.g. 'Spring 2020490' from a garbled 'Intersession 2023' header).
            if _max_year_seen > 0 and (_max_year_seen - candidate_year) > 2:
                if debug:
                    print(f"  [SEM-SKIP] suspicious year {candidate_year} "
                          f"(max seen {_max_year_seen}): {line[:60]}",
                          file=sys.stderr)
            else:
                current_semester = candidate_sem
                _max_year_seen = max(_max_year_seen, candidate_year)
                if debug:
                    print(f"  [SEM] → {current_semester}  (line: {line[:80]})",
                          file=sys.stderr)
        elif _INTERSESSION_WORD_RE.search(line):
            # 'Intersession' keyword found but year is garbled (OCR noise).
            # Infer the best semester name from the most recent year seen.
            inferred_year = str(_max_year_seen) if _max_year_seen else '2023'
            current_semester = f"Intersession {inferred_year}"
            if debug:
                print(f"  [SEM-INFER] → {current_semester}  (line: {line[:80]})",
                      file=sys.stderr)

        if current_semester is None:
            continue

        # ── course + grade extraction ────────────────────────────────────────
        end_m    = END_RE.search(line)
        fallback = False
        if not end_m:
            # Try fallback: match just 'grade CC [CP]' at end, use CC as credit
            fb_m = END_RE_FALLBACK.search(line)
            if fb_m:
                end_m    = fb_m
                fallback = True
            else:
                if debug and COURSE_CODE_RE.search(line):
                    print(f"  [NO-GRADE] {line[:80]}", file=sys.stderr)
                continue

        if fallback:
            grade   = _normalize_grade(end_m.group(1))
            cc_raw  = end_m.group(2)
            raw_credit = cc_raw   # credit = CC when primary is unreadable
        else:
            raw_credit = end_m.group(1)
            grade      = _normalize_grade(end_m.group(2))
            cc_raw     = end_m.group(3)   # may be None

        if grade not in VALID_GRADES:
            if debug:
                print(f"  [BAD-GRADE] {grade!r}  {line[:80]}", file=sys.stderr)
            continue

        # Last course code before the grade match
        code_matches = list(COURSE_CODE_RE.finditer(line[:end_m.start()]))
        if not code_matches:
            if debug:
                print(f"  [NO-CODE]  grade={grade}  {line[:80]}", file=sys.stderr)
            continue

        course_code = _parse_course_code(code_matches[-1].group(0))
        credits     = _normalize_credit(raw_credit, cc_raw=cc_raw)

        rows.append({
            "Course_Code": course_code,
            "Credits":     credits,
            "Grade":       grade,
            "Semester":    current_semester,
        })

        if debug:
            print(f"  [ROW]  {course_code}  {credits}  {grade}  {current_semester}",
                  file=sys.stderr)

    return rows


def parse_page(img: "Image.Image", debug: bool = False) -> list[dict]:
    """
    Parse one page image.  Tries two-column split first; if the split yields
    very few rows, falls back to full-width OCR.
    """
    # Full-width OCR (always done – used as fallback)
    full_text  = _ocr(img)
    full_rows  = _parse_column(full_text, debug=debug)

    # Two-column split
    left_img, right_img = _split_columns(img)
    left_rows  = _parse_column(_ocr(left_img),  debug=debug)
    right_rows = _parse_column(_ocr(right_img), debug=debug)
    split_rows = left_rows + right_rows

    # Pick the richer result
    if len(split_rows) >= len(full_rows):
        if debug:
            print(f"  [SPLIT] Using column-split result "
                  f"({len(split_rows)} rows vs {len(full_rows)} full-width)",
                  file=sys.stderr)
        return split_rows
    else:
        if debug:
            print(f"  [SPLIT] Falling back to full-width result "
                  f"({len(full_rows)} rows vs {len(split_rows)} split)",
                  file=sys.stderr)
        return full_rows


# ── deduplication ──────────────────────────────────────────────────────────────

def _deduplicate(rows: list[dict]) -> list[dict]:
    """
    Remove exact duplicate rows (same code + credits + grade + semester).
    The audit engine handles retakes, so we keep genuine duplicates (different
    semesters or different grades for the same code).
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        key = (r["Course_Code"], r["Credits"], r["Grade"], r["Semester"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ── CSV writer ─────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Course_Code", "Credits", "Grade", "Semester"]
        )
        writer.writeheader()
        writer.writerows(rows)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert an NSU transcript (PDF/image) to audit-compatible CSV"
    )
    ap.add_argument("transcript",
                    help="Path to the transcript file (PDF, JPEG, PNG, …)")
    ap.add_argument("-o", "--output",
                    help="Output CSV path  [default: <transcript>.csv]")
    ap.add_argument("--debug", action="store_true",
                    help="Print parsing details to stderr")
    args = ap.parse_args()

    src = Path(args.transcript)
    if not src.exists():
        sys.exit(f"ERROR: File not found: {src}")

    out = Path(args.output) if args.output else src.with_suffix(".csv")

    print(f"Reading:  {src}", file=sys.stderr)
    pages = _get_page_images(src)
    print(f"  Pages:  {len(pages)}", file=sys.stderr)

    all_rows: list[dict] = []
    for idx, page in enumerate(pages, 1):
        print(f"  OCR page {idx} …", file=sys.stderr)
        rows = parse_page(page, debug=args.debug)
        print(f"    → {len(rows)} course rows extracted", file=sys.stderr)
        all_rows.extend(rows)

    all_rows = _deduplicate(all_rows)

    write_csv(all_rows, out)
    print(f"\nWritten {len(all_rows)} rows to: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
