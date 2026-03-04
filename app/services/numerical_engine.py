from __future__ import annotations

import re
from typing import Any, Optional


_NUM_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except Exception:
        return None


def _extract_last_number(text: str) -> Optional[float]:
    if not text:
        return None
    matches = list(_NUM_RE.finditer(text))
    if not matches:
        return None
    return _safe_float(matches[-1].group(0))


def _extract_after_equals(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"=\s*(?P<num>" + _NUM_RE.pattern + r")", text)
    if not m:
        return None
    return _safe_float(m.group("num"))


def _unit_present(text: str, expected_unit: Optional[str]) -> bool:
    if not isinstance(expected_unit, str):
        return True
    unit = expected_unit.strip()
    if not unit:
        return True
    escaped = re.escape(unit)
    # "Whole-word boundary" behavior:
    # - If unit is alnum/underscore only, use \b boundaries.
    # - Otherwise, use non-word guards (works better for units like "m/s").
    if re.fullmatch(r"\w+", unit):
        pat = r"(?i)\b" + escaped + r"\b"
    else:
        pat = r"(?i)(?<!\w)" + escaped + r"(?!\w)"
    return re.search(pat, text or "") is not None


def _extract_near_unit(text: str, expected_unit: Optional[str]) -> Optional[float]:
    if not isinstance(expected_unit, str) or not expected_unit.strip():
        return None
    unit = expected_unit.strip()
    escaped = re.escape(unit)
    if re.fullmatch(r"\w+", unit):
        unit_pat = r"(?i)\b" + escaped + r"\b"
    else:
        unit_pat = r"(?i)(?<!\w)" + escaped + r"(?!\w)"

    # number before unit (e.g., "12.5 m/s")
    m = re.search(r"(?P<num>" + _NUM_RE.pattern + r")\s*" + unit_pat, text or "")
    if m:
        return _safe_float(m.group("num"))

    # unit before number (rare, but tolerate: "m/s 12.5")
    m = re.search(unit_pat + r"\s*(?P<num>" + _NUM_RE.pattern + r")", text or "")
    if m:
        return _safe_float(m.group("num"))
    return None


def _extract_from_last_two_lines(text: str) -> Optional[float]:
    if not text:
        return None
    lines = [ln for ln in (text.splitlines() or []) if ln.strip()]
    tail = "\n".join(lines[-2:]) if lines else text
    return _extract_last_number(tail)


def _extract_student_value(answer_text: str, expected_unit: Optional[str]) -> Optional[float]:
    # Prefer: after '=', near unit, in last 2 lines, else last numeric overall.
    for extractor in (
        _extract_after_equals,
        lambda t: _extract_near_unit(t, expected_unit),
        _extract_from_last_two_lines,
        _extract_last_number,
    ):
        v = extractor(answer_text or "")
        if v is not None:
            return v
    return None


def evaluate_numerical(question: Any, answer_text: str) -> dict:
    try:
        correct_value = getattr(question, "correct_numeric_answer", None)
        expected_unit = getattr(question, "expected_unit", None)
        unit_match = _unit_present(answer_text or "", expected_unit)

        student_value = _extract_student_value(answer_text or "", expected_unit)

        if correct_value is None:
            return {
                "score": 0.0,
                "feedback": "Numeric configuration missing.",
                "evaluation_details": {
                    "student_value": float(student_value) if student_value is not None else None,
                    "correct_value": None,
                    "difference": None,
                    "within_tolerance": False,
                    "within_extended_tolerance": False,
                    "unit_match": bool(unit_match),
                    "awarded_score": 0.0,
                    "config_missing": True,
                },
            }

        tol = getattr(question, "numeric_tolerance", None)
        try:
            tolerance = float(tol) if tol is not None else 0.01
        except Exception:
            tolerance = 0.01

        if student_value is None:
            return {
                "score": 0.0,
                "feedback": "No numeric value found in answer.",
                "evaluation_details": {
                    "student_value": None,
                    "correct_value": float(correct_value),
                    "difference": None,
                    "within_tolerance": False,
                    "within_extended_tolerance": False,
                    "unit_match": bool(unit_match),
                    "awarded_score": 0.0,
                    "config_missing": False,
                },
            }

        difference = abs(float(student_value) - float(correct_value))
        within_tolerance = difference <= float(tolerance)
        within_extended_tolerance = difference <= float(tolerance) * 5.0

        full_marks = float(getattr(question, "max_marks", 0) or 0)
        if within_tolerance:
            score = full_marks
            feedback = "Correct within tolerance."
        elif within_extended_tolerance:
            score = full_marks * 0.5
            feedback = "Close (within extended tolerance)."
        else:
            score = 0.0
            feedback = "Numeric value outside tolerance."

        # Unit mismatch penalty (does not fully zero score; reduces by 25%).
        if isinstance(expected_unit, str) and expected_unit.strip() and not unit_match:
            score = score * 0.75
            feedback = "Unit mismatch (score penalized)."

        return {
            "score": float(score),
            "feedback": str(feedback),
            "evaluation_details": {
                "student_value": float(student_value),
                "correct_value": float(correct_value),
                "difference": float(difference),
                "within_tolerance": bool(within_tolerance),
                "within_extended_tolerance": bool(within_extended_tolerance),
                "unit_match": bool(unit_match),
                "awarded_score": float(score),
                "config_missing": False,
            },
        }
    except Exception as e:
        expected_unit = getattr(question, "expected_unit", None)
        return {
            "score": 0.0,
            "feedback": "Numerical evaluation failed.",
            "evaluation_details": {
                "student_value": _extract_student_value(answer_text or "", expected_unit),
                "correct_value": getattr(question, "correct_numeric_answer", None),
                "difference": None,
                "within_tolerance": False,
                "within_extended_tolerance": False,
                "unit_match": bool(_unit_present(answer_text or "", expected_unit)),
                "awarded_score": 0.0,
                "config_missing": bool(getattr(question, "correct_numeric_answer", None) is None),
                "error": str(e),
            },
        }

