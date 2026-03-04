from __future__ import annotations

import json

from app.services.symbolic_engine import evaluate_symbolic


class Q:
    pass


def main() -> None:
    q = Q()
    q.subject_type = "symbolic"
    q.max_marks = 5
    q.answer_key = "x^2 + 2*x + 1"

    cases = [
        ("equivalent", "(x+1)^2"),
        ("not_equivalent", "x^2 + 2*x + 2"),
        ("invalid", "this is not math"),
    ]

    for name, ans in cases:
        r = evaluate_symbolic(q, ans)
        print(name)
        print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

