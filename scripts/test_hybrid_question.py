from __future__ import annotations

import json

from app.services.embedding_service import EmbeddingService
from app.services.hybrid_engine import evaluate_hybrid


class _Q:
    pass


def main() -> None:
    q = _Q()
    q.subject_type = "mixed"
    q.correct_numeric_answer = 12.5
    q.numeric_tolerance = 0.1
    q.expected_unit = "m/s"
    q.evaluation_level = "medium"
    q.max_marks = 10
    q.answer_key = "Final velocity is 12.5 m/s."
    q.concepts = {"items": ["velocity", "formula", "distance", "time"]}

    embedding = EmbeddingService.load()
    q._embedding_service = embedding

    answer = "Using formula v = d/t we get 12.48 m/s. Therefore final velocity is 12.48 m/s."
    result = evaluate_hybrid(q, answer)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

