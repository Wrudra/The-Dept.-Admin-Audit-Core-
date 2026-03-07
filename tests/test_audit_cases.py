"""Pytest test suite for all 300+ test-case transcript CSVs.

Design:
  - Parametrised over every CSV in Test Cases/ (by program derived from filename).
  - Runs the audit engine in --no-interact mode (NO_INTERACT=True).
  - Smoke-tests that the engine completes without exception and returns a sane result.
  - Optionally asserts a specific credit / CGPA if a companion .expected.json exists.

Running:
    pytest tests/test_audit_cases.py -x -q                    # stop on first fail
    pytest tests/test_audit_cases.py --tb=short -q            # show short traceback
    pytest tests/test_audit_cases.py -k cse_01                # one case
    pytest tests/test_audit_cases.py -n auto                  # parallel (install pytest-xdist)
"""
import json
import re
import types
from pathlib import Path

import pytest

# ── Constants ─────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
TEST_CASES  = REPO_ROOT / "Test Cases"
PROGRAM_MD  = REPO_ROOT / "program.md"


# ── Collect test CSVs ─────────────────────────────────────────────────────────

def _collect_cases():
    """Return a list of (csv_path, program) tuples for every test CSV."""
    cases = []
    for csv in sorted(TEST_CASES.glob("*.csv")):
        name = csv.stem.lower()
        if "cse" in name:
            program = "CSE"
        elif "mic" in name:
            program = "MIC"
        else:
            # stress_test_transcript.csv — try CSE
            program = "CSE"
        cases.append((csv, program))
    return cases


_CASES = _collect_cases()


# ── Parametrised test ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "csv_path, program",
    _CASES,
    ids=[c[0].stem for c in _CASES],
)
def test_audit_case(csv_path: Path, program: str) -> None:
    """Smoke-test: audit engine must complete without exception and return a dict
    with the required keys.  Optional companion .expected.json files enforce
    specific credit / CGPA values.
    """
    import audit_l1
    import audit_l2

    audit_l1.NO_INTERACT = True
    args   = types.SimpleNamespace(
        transcript=csv_path,
        program_name=program,
        program_knowledge=PROGRAM_MD,
        no_interact=True,
    )

    try:
        result = audit_l2.run_audit(args)
    finally:
        audit_l1.NO_INTERACT = False

    # ── Structural assertions ─────────────────────────────────────────────────
    required_keys = {
        "program_key", "total", "required_credits", "credit_completed",
        "cgpa", "per_course", "by_course", "prereq_failures",
        "waived_courses", "waiver_notes",
    }
    missing = required_keys - result.keys()
    assert not missing, f"Result missing keys: {missing}"

    assert isinstance(result["total"],            (int, float)), "total must be numeric"
    assert isinstance(result["cgpa"],             (int, float)), "cgpa must be numeric"
    assert 0.0 <= result["cgpa"] <= 4.0,                        "cgpa must be in [0, 4]"
    assert result["total"] >= 0,                                "total credits must be ≥ 0"
    assert result["required_credits"] > 0,                      "required_credits must be > 0"
    assert result["credit_completed"] >= 0,                     "credit_completed must be ≥ 0"

    # ── Optional expected values file ─────────────────────────────────────────
    expected_file = csv_path.with_suffix(".expected.json")
    if expected_file.exists():
        expected = json.loads(expected_file.read_text())
        if "credit_completed" in expected:
            assert result["credit_completed"] == pytest.approx(expected["credit_completed"], abs=0.1), \
                f"credit_completed mismatch: got {result['credit_completed']}, expected {expected['credit_completed']}"
        if "cgpa" in expected:
            assert float(result["cgpa"]) == pytest.approx(expected["cgpa"], abs=0.01), \
                f"CGPA mismatch: got {result['cgpa']}, expected {expected['cgpa']}"
        if "total" in expected:
            assert result["total"] == pytest.approx(expected["total"], abs=0.1), \
                f"total valid credits mismatch"
