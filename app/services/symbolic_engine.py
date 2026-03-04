from __future__ import annotations

import re
from typing import Any

from sympy import simplify, sympify
from sympy.core.sympify import SympifyError


def _normalize_expr(expr: str) -> str:
    s = (expr or "").strip()
    s = s.replace("^", "**")
    s = "".join(s.split())
    return s


_ONLY_LETTERS = re.compile(r"^[A-Za-z_]+$")


def _candidate_from_text(raw: str) -> str:
    s = (raw or "").strip()
    if "=" in s:
        s = s.rsplit("=", 1)[-1].strip()
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines:
        s = lines[-1]
    return s


def evaluate_symbolic(question: Any, answer_text: str) -> dict:
    try:
        correct_raw = getattr(question, "answer_key", "") or ""
        student_raw = answer_text or ""

        correct_expression = _normalize_expr(str(correct_raw))
        student_candidate = _candidate_from_text(str(student_raw))
        student_expression = _normalize_expr(student_candidate)

        max_marks = float(getattr(question, "max_marks", 0) or 0)

        if not student_expression:
            return {
                "score": 0.0,
                "feedback": "Invalid expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": False,
                    "parse_error": "empty_expression",
                },
            }

        if (" " in str(student_raw)) and _ONLY_LETTERS.fullmatch(student_expression):
            return {
                "score": 0.0,
                "feedback": "Invalid expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": False,
                    "parse_error": "non_math_text",
                },
            }

        try:
            student_expr = sympify(student_expression, locals={}, evaluate=True)
            correct_expr = sympify(correct_expression, locals={}, evaluate=True)
        except SympifyError as e:
            return {
                "score": 0.0,
                "feedback": "Invalid expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": False,
                    "parse_error": str(e),
                },
            }
        except Exception as e:
            return {
                "score": 0.0,
                "feedback": "Invalid expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": False,
                    "parse_error": str(e),
                },
            }

        try:
            equivalent = bool(simplify(student_expr - correct_expr) == 0)
        except Exception as e:
            return {
                "score": 0.0,
                "feedback": "Invalid expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": False,
                    "parse_error": str(e),
                },
            }

        if equivalent:
            return {
                "score": float(max_marks),
                "feedback": "Equivalent expression.",
                "evaluation_details": {
                    "student_expression": student_expression,
                    "correct_expression": correct_expression,
                    "equivalent": True,
                },
            }

        return {
            "score": 0.0,
            "feedback": "Not equivalent.",
            "evaluation_details": {
                "student_expression": student_expression,
                "correct_expression": correct_expression,
                "equivalent": False,
            },
        }
    except Exception as e:
        return {
            "score": 0.0,
            "feedback": "Symbolic evaluation failed.",
            "evaluation_details": {
                "student_expression": _normalize_expr(str(answer_text or "")),
                "correct_expression": _normalize_expr(str(getattr(question, "answer_key", "") or "")),
                "equivalent": False,
                "error": str(e),
            },
        }
