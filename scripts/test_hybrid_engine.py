from __future__ import annotations

import json

from app.services.hybrid_engine import evaluate_hybrid


class Q:
    pass


class HardStub:
    def evaluate(self, answer_key: str, answer_text: str, max_marks: int) -> dict:
        return {"score": float(max_marks), "feedback": "stub", "evaluation_details": {"stub": True}}


def main() -> None:
    q = Q()
    q.subject_type = "mixed"
    q.max_marks = 10
    q.answer_key = "v=12.5 m/s"
    q.evaluation_level = "hard"
    q._hard_service = HardStub()

    q.correct_numeric_answer = 12.5
    q.numeric_tolerance = 0.1
    q.expected_unit = "m/s"

    q.hybrid_numerical_weight = 2.0
    q.hybrid_descriptive_weight = 1.0

    ans = "Using formula v = d/t we get v = 12.48 m/s. Therefore final velocity is 12.48 m/s."
    r = evaluate_hybrid(q, ans)
    print("hybrid_weight_norm")
    print(json.dumps(r, indent=2, ensure_ascii=False))

    q2 = Q()
    q2.subject_type = "mixed"
    q2.max_marks = 10
    q2.answer_key = "v=12.5 m/s"
    q2.evaluation_level = "hard"
    q2._hard_service = HardStub()
    q2.correct_numeric_answer = None
    q2.numeric_tolerance = 0.1
    q2.expected_unit = "m/s"
    r2 = evaluate_hybrid(q2, ans)
    print("hybrid_missing_numeric")
    print(json.dumps(r2, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

