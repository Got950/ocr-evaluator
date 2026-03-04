from __future__ import annotations

import json

from app.services.numerical_engine import evaluate_numerical


class Q:
    pass


def main() -> None:
    q = Q()
    q.subject_type = "numerical"
    q.max_marks = 10
    q.correct_numeric_answer = 12.5
    q.numeric_tolerance = 0.1
    q.expected_unit = "m/s"

    cases = [
        ("after_equals", "We compute v = 12.48 m/s. Earlier 1 2 3."),
        ("near_unit", "Final speed is 12.48m/s (approx)."),
        ("last_two_lines", "Work...\nFinal answer:\n12.48 m/s\nthanks"),
        ("fallback_last_number", "numbers 1 2 3 12.48"),
        ("unit_mismatch_penalty", "v = 12.48 km/h"),
        ("partial_credit", "v = 12.9 m/s"),
        ("no_number", "no numeric here"),
    ]

    for name, ans in cases:
        r = evaluate_numerical(q, ans)
        print(name)
        print(json.dumps(r, indent=2, ensure_ascii=False))

    q2 = Q()
    q2.subject_type = "numerical"
    q2.max_marks = 10
    q2.correct_numeric_answer = None
    q2.numeric_tolerance = 0.1
    q2.expected_unit = "m/s"
    r = evaluate_numerical(q2, "v = 12.48 m/s")
    print("missing_config")
    print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

