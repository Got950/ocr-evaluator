from __future__ import annotations

from typing import Any

from app.services.hybrid_engine import evaluate_hybrid
from app.services.numerical_engine import evaluate_numerical
from app.services.symbolic_engine import evaluate_symbolic
from app.services.evaluation_easy import evaluate_easy
from app.services.evaluation_hard import HardEvaluationService as evaluate_hard
from app.services.evaluation_medium import evaluate_medium
from app.utils.text_cleaning import clean_text


_ALLOWED_SUBJECT_TYPES = {"descriptive", "numerical", "symbolic", "mixed"}


def route_engine(question: Any, answer_text: str) -> dict:
    subject_type = (getattr(question, "subject_type", None) or "descriptive").strip().lower()
    if subject_type not in _ALLOWED_SUBJECT_TYPES:
        raise ValueError("Invalid subject_type")

    if subject_type == "symbolic":
        return evaluate_symbolic(question, answer_text)
    if subject_type == "numerical":
        return evaluate_numerical(question, answer_text)
    if subject_type == "mixed":
        return evaluate_hybrid(question, answer_text)

    evaluation_level = (getattr(question, "evaluation_level", None) or "").strip().lower()

    embedding = getattr(question, "_embedding_service", None)
    hard_service = getattr(question, "_hard_service", None)

    if evaluation_level == "easy":
        if embedding is None:
            raise ValueError("Embedding service not available")
        return evaluate_easy(answer_text, clean_text(question.answer_key), int(question.max_marks), embedding)
    if evaluation_level == "medium":
        if embedding is None:
            raise ValueError("Embedding service not available")
        return evaluate_medium(
            answer_text, clean_text(question.answer_key), int(question.max_marks), getattr(question, "concepts", None), embedding
        )
    if evaluation_level == "hard":
        if hard_service is None:
            raise ValueError("Hard evaluation is not configured")
        return hard_service.evaluate(question.answer_key, answer_text, int(question.max_marks))

    raise ValueError("Invalid evaluation level")

