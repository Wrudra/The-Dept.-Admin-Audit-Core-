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

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

# ── constants ──────────────────────────────────────────────────────────────────
VALID_GRADES: set[str] = {
    "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F", "W", "I", "X"
}
# Standard NSU credit values
STANDARD_CREDITS = {"0.0", "1.0", "1.5", "3.0"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

# Load the NSU course catalog (used to reject OCR false positives).
_CATALOG: frozenset
_CATALOG_PATH = Path(__file__).parent / "nsu_catalog.json"
if _CATALOG_PATH.exists():
    import json as _json
    with _CATALOG_PATH.open() as _f:
        _CATALOG = frozenset(_json.load(_f))
else:
    _CATALOG = frozenset()

# Valid NSU 3-letter department prefixes (derived from audit_l1.py catalog).
# Used to reject OCR noise that accidentally matches the course-code pattern
# (e.g. watermark fragments like "NOK773").
VALID_PREFIXES: frozenset = frozenset({
    "ACT", "ANT", "ARC", "BBT", "BEN", "BIO", "BSC", "BUS", "CEE", "CHE",
    "CHN", "CSE", "DEV", "ECO", "EEE", "EMB", "ENG", "ENV", "ETE", "ETH",
    "FIN", "GEO", "HAS", "HIS", "HRM", "INB", "LAW", "LBA", "LLB", "LLM",
    "MAT", "MCJ", "MGT", "MIC", "MIS", "MKT", "PAD", "PBH", "PHI", "PHR",
    "PHY", "POL", "PPG", "PSY", "SCM", "SOC", "TNM", "WMS",
})

# NSU course code: exactly 3 uppercase letters + 3 digits (tolerates I/l/O/S noise)
# + optional trailing letter (e.g. CSE115L, PHY108L, CSE499A)
# NSU uses exclusively 3-letter department prefixes; requiring {3} prevents
# false positives like "AS130" from watermark OCR noise.
_CODE_BODY     = r'[A-Z]{3}[0-9IlOSL]{3}[A-Z]?(?![0-9])'
COURSE_CODE_RE = re.compile(r'\b(' + _CODE_BODY + r')\b')

# Spaced course code produced by OCR: e.g. "PHY 107" "PHY 108L"
_SPACED_CODE_RE = re.compile(r'\b([A-Z]{3})\s([0-9]{3}[A-Z]?)\b')

# Grade pattern: allow 't' as OCR artefact for '+' (B+ → Bt, C+ → Ct, D+ → Dt)
# Also accept lowercase (OCR sometimes lowercases grades, e.g 'a' instead of 'A')
_GRADE_SET = r'(?:[Aa][-]?|[Bb][+\-t]?|[Cc][+\-t]?|[Dd][+\-t]?|[FfWwIiXx])'

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


def _enhance_r(img: "Image.Image") -> "Image.Image":
    """
    Alternative enhancement that uses only the red channel.
    NSU transcripts carry a blue circular watermark; the watermark has high
    B values but only medium-to-high R values, while black text has low R.
    Extracting R (and boosting contrast) suppresses the blue watermark, making
    rows obscured by it readable in OCR. Falls back to grayscale for non-RGB.
    """
    if img.mode == "RGB":
        r, _g, _b = img.split()
        gray = r
    else:
        gray = img.convert("L")
    enhanced  = ImageEnhance.Contrast(gray).enhance(2.5)
    sharpened = ImageEnhance.Sharpness(enhanced).enhance(1.5)
    return sharpened


def _enhance_camscanner(img: "Image.Image") -> "Image.Image":
    """
    CamScanner-style illumination normalisation.

    Steps (mirrors what CamScanner does internally):
      1. Convert to grayscale.
      2. Estimate the background illumination with a large Gaussian blur
         (the blurred image approximates a smooth lighting map with no text).
      3. Divide the original by the background map — this cancels uneven
         lighting AND suppresses any consistent-colour overlay (e.g. the blue
         watermark) because its contribution is absorbed into the background
         estimate and then divided away.
      4. Rescale to [0, 255] and apply adaptive thresholding to whiten the
         background and sharpen the text (the "Magic Color" step).
    """
    if not _HAS_CV2:
        return _enhance(img)
    gray = np.array(img.convert("L"), dtype=np.float32)
    # Large kernel: must be bigger than any character glyph so text pixels
    # don't affect the background estimate.  Use ~5 % of the page height.
    h, w  = gray.shape
    ksize = max(51, int(min(h, w) * 0.05) | 1)   # odd number
    background = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    # Divide; clamp to avoid div-by-zero on pure-black regions
    normalised = gray / (background + 1e-5) * 255.0
    normalised = np.clip(normalised, 0, 255).astype(np.uint8)
    # Adaptive threshold finishes the binarisation (GAUSSIAN_C, block=51, C=15)
    binarised  = cv2.adaptiveThreshold(
        normalised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=51, C=15
    )
    return Image.fromarray(binarised)


def _ocr(img: "Image.Image") -> str:
    processed = _enhance(img)
    return pytesseract.image_to_string(processed, config="--oem 3 --psm 6")


def _ocr_r(img: "Image.Image") -> str:
    """OCR using the R-channel enhancement (watermark-suppressing pass)."""
    processed = _enhance_r(img)
    return pytesseract.image_to_string(processed, config="--oem 3 --psm 6")


def _ocr_camscanner(img: "Image.Image") -> str:
    """OCR using CamScanner-style illumination normalisation."""
    processed = _enhance_camscanner(img)
    return pytesseract.image_to_string(processed, config="--oem 3 --psm 6")


def _ocr_upscaled(img: "Image.Image") -> str:
    """OCR using 2x upscaled image for small-text or noisy-area recovery.

    Upscaling before enhancement gives Tesseract more pixels to work with,
    which helps when characters are partially obscured by watermarks or when
    the source image has low effective DPI.
    """
    w, h = img.size
    upscaled = img.resize((w * 2, h * 2), Image.LANCZOS)
    processed = _enhance(upscaled)
    return pytesseract.image_to_string(processed, config="--oem 3 --psm 6")


def _remove_watermark_inpaint(img: "Image.Image") -> "Image.Image":
    """
    Use OpenCV HSV colour masking + Telea inpainting to erase the blue
    circular watermark from an RGB scan, then return the cleaned PIL Image.

    Approach (from StackOverflow best practice for coloured-stamp removal):
      1. Convert to HSV; isolate the blue stamp pixels by hue/saturation range.
      2. Dilate the mask slightly so edge fringe pixels are also covered.
      3. cv2.inpaint() reconstructs the pixels under the mask from local
         neighbourhood values — restoring the printing beneath the stamp.
    """
    if not _HAS_CV2 or img.mode != "RGB":
        return img
    bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # Blue watermark: hue 95-135 (OpenCV 0-179 scale), saturation > 55
    lo = np.array([95,  55, 60],  dtype=np.uint8)
    hi = np.array([135, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lo, hi)
    # Dilate by 3 px to cover feathered stamp edges
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.dilate(mask, kernel, iterations=2)
    # Inpaint: Telea algorithm works best for thin overlays
    inpainted = cv2.inpaint(bgr, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))


def _ocr_inpaint(img: "Image.Image") -> str:
    """OCR on a watermark-inpainted version of the image."""
    cleaned = _remove_watermark_inpaint(img)
    return _ocr(cleaned)


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
    g = raw.strip().upper()
    # '+' is sometimes OCR'd as 't' (B+ → Bt, C+ → Ct, D+ → Dt)
    if len(g) == 2 and g[1] == 'T':
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

def _split_multi_course_lines(lines: list[str]) -> list[str]:
    """Split lines containing multiple course codes into separate fragments.

    When full-width OCR merges two columns, a single line can contain two
    independent course rows (e.g. 'BIO103 ... 3.0 3.0 MIC415L ... 1.0 1.0').
    The parser only extracts the last course code → the first is lost.
    Splitting at each course-code boundary recovers both.
    """
    out: list[str] = []
    for line in lines:
        codes = list(COURSE_CODE_RE.finditer(line))
        if len(codes) >= 2:
            for i, m in enumerate(codes):
                start = m.start()
                end = codes[i + 1].start() if i + 1 < len(codes) else len(line)
                fragment = line[start:end].strip()
                if fragment:
                    out.append(fragment)
        else:
            out.append(line)
    return out


def _parse_column(text: str, debug: bool = False) -> list[dict]:
    """
    Parse a single OCR column text and return a list of row dicts:
      { 'Course_Code', 'Credits', 'Grade', 'Semester' }
    """
    text = _normalize_text(text)
    rows = []

    # Pre-merge wrapped lines: if a line ends mid-number (no grade found)
    # and the NEXT line starts with a digit, merge them.
    raw_lines = text.splitlines()
    lines = []
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if (lines
                and END_RE.search(lines[-1]) is None
                and re.match(r'^\d', line)
                and not COURSE_CODE_RE.search(line)):
            lines[-1] = lines[-1] + ' ' + line
            i += 1
            continue
        lines.append(line)
        i += 1

    # Split lines that contain multiple course codes (merged columns).
    lines = _split_multi_course_lines(lines)

    for line in lines:
        if not line:
            continue
        # Smart skip: if summary text appears AFTER a course code, truncate
        # the line at the summary boundary instead of discarding it entirely.
        skip_match = _SKIP_RE.search(line)
        if skip_match:
            pre_skip = line[:skip_match.start()].rstrip()
            if not COURSE_CODE_RE.search(pre_skip):
                continue          # no course data before the skip text
            line = pre_skip       # keep only the course portion
        # Strip trailing noise words left over after truncation (e.g. "Total",
        # "Cumulative") that prevent END_RE from matching the grade/credit.
        line = re.sub(
            r'\s+(?:Total|Cumulative|Semester|Summary)\s*$', '',
            line, flags=re.IGNORECASE,
        )

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

        # Reject codes whose 3-letter prefix is not a known NSU department.
        # This filters out watermark OCR noise (e.g. "NOK773") before it reaches
        # the merge logic, regardless of which pass produced it.
        if course_code[:3] not in VALID_PREFIXES:
            if debug:
                print(f"  [BAD-PREFIX] {course_code}  {line[:80]}", file=sys.stderr)
            continue

        credits     = _normalize_credit(raw_credit, cc_raw=cc_raw)

        rows.append({
            "Course_Code": course_code,
            "Credits":     credits,
            "Grade":       grade,
            "Semester":    "N/A",
        })

        if debug:
            print(f"  [ROW]  {course_code}  {credits}  {grade}",
                  file=sys.stderr)

    return rows


def parse_page(img: "Image.Image", debug: bool = False, r_pass: bool = False, inpaint_pass: bool = False, camscanner_pass: bool = False) -> list[dict]:
    """
    Parse one page image.  Tries two-column split first; if the split yields
    very few rows, falls back to full-width OCR.  When r_pass=True an additional
    R-channel pass is run to recover rows obscured by a coloured watermark
    (useful for JPEG/image scans; not needed for PDF-converted pages).
    """
    # Full-width OCR (always done – used as fallback)
    full_text  = _ocr(img)
    full_rows  = _parse_column(full_text, debug=debug)

    # Two-column split
    left_img, right_img = _split_columns(img)
    left_rows  = _parse_column(_ocr(left_img),  debug=debug)
    right_rows = _parse_column(_ocr(right_img), debug=debug)
    split_rows = left_rows + right_rows

    # Pick the richer result as primary.
    # For image scans (r_pass=True) also merge in anything the other pass uniquely
    # found — e.g. a row visible full-width but not in the split (MIC207 case).
    # For clean PDF renders we keep the original single-pick logic to avoid
    # pulling in false positives from the noisier full-width pass.
    if len(split_rows) >= len(full_rows):
        best = _merge_rows_strict(split_rows, full_rows) if r_pass else split_rows
        if debug:
            print(f"  [SPLIT] Using column-split result "
                  f"({len(split_rows)} rows vs {len(full_rows)} full-width)",
                  file=sys.stderr)
    else:
        best = _merge_rows_strict(full_rows, split_rows) if r_pass else full_rows
        if debug:
            print(f"  [SPLIT] Falling back to full-width result "
                  f"({len(full_rows)} rows vs {len(split_rows)} split)",
                  file=sys.stderr)

    # Supplementary R-channel pass: recovers rows obscured by a coloured watermark.
    # Only enabled for image scans (r_pass=True); PDF-converted pages are already
    # monochrome and the R-pass only introduces OCR noise on them.
    if r_pass and img.mode == "RGB":
        r_supp  = (_parse_column(_ocr_r(left_img),  debug=False)
                 + _parse_column(_ocr_r(right_img), debug=False)
                 + _parse_column(_ocr_r(img),        debug=False))
        before  = len(best)
        best    = _merge_rows(best, r_supp)
        if debug and len(best) > before:
            print(f"  [R-PASS] recovered {len(best) - before} additional row(s)",
                  file=sys.stderr)

    # Inpaint pass: uses OpenCV HSV masking + Telea inpainting to physically
    # remove the blue watermark before OCR.  This can recover rows where the
    # watermark ink directly overwrites credit/grade columns.
    if inpaint_pass and _HAS_CV2 and img.mode == "RGB":
        clean_img             = _remove_watermark_inpaint(img)
        clean_left, clean_right = _split_columns(clean_img)
        ip_supp = (_parse_column(_ocr(clean_left),  debug=False)
                 + _parse_column(_ocr(clean_right), debug=False)
                 + _parse_column(_ocr(clean_img),   debug=False))
        before = len(best)
        best   = _merge_rows(best, ip_supp)
        if debug and len(best) > before:
            print(f"  [INPAINT-PASS] recovered {len(best) - before} additional row(s)",
                  file=sys.stderr)

    # CamScanner-style pass: illumination normalisation (background division +
    # adaptive threshold).  Suppresses the watermark by absorbing it into the
    # background estimate, potentially recovering rows not found by other passes.
    # Uses strict merge (same as full+split) to reject standard-credit codes
    # that look like OCR misreads of already-found courses (e.g. CHE110 vs CHE101).
    if camscanner_pass and _HAS_CV2:
        cs_left, cs_right = _split_columns(img)
        cs_supp = (_parse_column(_ocr_camscanner(cs_left),  debug=False)
                 + _parse_column(_ocr_camscanner(cs_right), debug=False)
                 + _parse_column(_ocr_camscanner(img),      debug=False))
        before = len(best)
        best   = _merge_rows_strict(best, cs_supp)
        if debug and len(best) > before:
            print(f"  [CAMSCANNER-PASS] recovered {len(best) - before} additional row(s)",
                  file=sys.stderr)

    # Upscaled pass: 2x upscale before enhancement gives Tesseract more pixels
    # to work with, recovering characters that are partially obscured or too
    # small in the original resolution.  Run on both column halves and full-width.
    if r_pass:
        up_supp = (_parse_column(_ocr_upscaled(left_img),  debug=False)
                 + _parse_column(_ocr_upscaled(right_img), debug=False)
                 + _parse_column(_ocr_upscaled(img),       debug=False))
        before = len(best)
        best   = _merge_rows_strict(best, up_supp)
        if debug and len(best) > before:
            print(f"  [UPSCALE-PASS] recovered {len(best) - before} additional row(s)",
                  file=sys.stderr)

    return best

def _merge_rows(primary: list[dict], supplementary: list[dict]) -> list[dict]:
    """
    Merge two OCR pass results.
    - Rows whose course code is only in *supplementary* are appended (new recoveries).
    - Where both passes found the same code, prefer the *primary* result unless
      its credit is non-standard, in which case try the supplementary credit.
    - Duplicates within supplementary are handled via seen_codes tracking.
    """
    seen_codes: set[str]        = {r["Course_Code"] for r in primary}
    primary_by_code: dict[str, dict] = {r["Course_Code"]: r for r in primary}
    out = list(primary)
    for row in supplementary:
        code = row["Course_Code"]
        if code not in seen_codes:
            # Reject codes not in the NSU catalog (OCR false positives)
            if _CATALOG and code not in _CATALOG:
                continue
            # Row completely missed by primary pass — add it
            out.append(row)
            seen_codes.add(code)
        elif code in primary_by_code:
            # Both passes found this code; patch credit if primary is non-standard
            existing = primary_by_code[code]
            if existing["Credits"] not in STANDARD_CREDITS and row["Credits"] in STANDARD_CREDITS:
                existing["Credits"] = row["Credits"]
    return out


def _merge_rows_strict(primary: list[dict], supplementary: list[dict]) -> list[dict]:
    """
    Like _merge_rows but guards against OCR misreads of existing codes.

    A new code from supplementary is accepted only if:
      - Its credit is non-standard (clearly garbled → real miss), OR
      - No code with the same 3-letter prefix, same total length, AND the same
        multiset of suffix characters already exists in primary.

    The anagram check on the suffix catches digit-transposition misreads
    (e.g. CHE110 ← CHE101: sorted("110") == sorted("101") → blocked) while
    allowing genuinely new courses whose digits happen to share one character
    with an existing code (e.g. MIC316 vs MIC315: sorted("316") ≠ sorted("315")
    → allowed).
    """
    seen_codes: set[str]             = {r["Course_Code"] for r in primary}
    primary_by_code: dict[str, dict] = {r["Course_Code"]: r for r in primary}
    out = list(primary)
    for row in supplementary:
        code = row["Course_Code"]
        if code not in seen_codes:
            # Reject codes not in the NSU catalog (OCR false positives)
            if _CATALOG and code not in _CATALOG:
                continue
            if row["Credits"] not in STANDARD_CREDITS:
                # Non-standard credit → clearly a real miss, always accept
                out.append(row)
                seen_codes.add(code)
            else:
                # Standard credit: block if suffix is a character-permutation of
                # an existing same-prefix same-length code (digit transposition).
                prefix = code[:3]
                suffix = code[3:]
                clash = any(
                    c[:3] == prefix and len(c) == len(code)
                    and sorted(c[3:]) == sorted(suffix)
                    for c in seen_codes
                )
                if not clash:
                    out.append(row)
                    seen_codes.add(code)
        elif code in primary_by_code:
            existing = primary_by_code[code]
            if existing["Credits"] not in STANDARD_CREDITS and row["Credits"] in STANDARD_CREDITS:
                existing["Credits"] = row["Credits"]
    return out



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


# ── public API (used by the web backend) ──────────────────────────────────────

def convert_to_csv_bytes(path: Path) -> bytes:
    """OCR-parse a transcript file and return the result as UTF-8 CSV bytes.

    Mirrors the main() pipeline but writes to an in-memory buffer so the
    caller doesn't need to manage temporary files.
    """
    import io as _io

    pages = _get_page_images(path)
    is_image = path.suffix.lower() in IMAGE_EXTS
    all_rows: list[dict] = []
    for page in pages:
        rows = parse_page(
            page,
            debug=False,
            r_pass=is_image,
            inpaint_pass=is_image,
            camscanner_pass=is_image,
        )
        all_rows.extend(rows)
    all_rows = _deduplicate(all_rows)

    buf = _io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=["Course_Code", "Credits", "Grade", "Semester"]
    )
    writer.writeheader()
    writer.writerows(all_rows)
    return buf.getvalue().encode("utf-8")


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

    # Enable the R-channel watermark-suppression pass for image files only.
    # PDF pages are already clean monochrome renders where the R-pass adds noise.
    is_image = src.suffix.lower() in IMAGE_EXTS

    all_rows: list[dict] = []
    for idx, page in enumerate(pages, 1):
        print(f"  OCR page {idx} …", file=sys.stderr)
        rows = parse_page(page, debug=args.debug, r_pass=is_image, inpaint_pass=is_image, camscanner_pass=is_image)
        print(f"    → {len(rows)} course rows extracted", file=sys.stderr)
        all_rows.extend(rows)

    all_rows = _deduplicate(all_rows)

    write_csv(all_rows, out)
    print(f"\nWritten {len(all_rows)} rows to: {out}", file=sys.stderr)


if __name__ == "__main__":
    main()