from __future__ import annotations

from typing import Any

from app.services.evaluation_easy import evaluate_easy
from app.services.evaluation_hard import HardEvaluationService as evaluate_hard
from app.services.evaluation_medium import evaluate_medium
from app.services.numerical_engine import evaluate_numerical
from app.utils.text_cleaning import clean_text


def evaluate_hybrid(question: Any, answer_text: str) -> dict:
    try:
        numerical_weight = getattr(question, "hybrid_numerical_weight", None) or 0.5
        descriptive_weight = getattr(question, "hybrid_descriptive_weight", None) or 0.5
        try:
            numerical_weight = float(numerical_weight)
        except Exception:
            numerical_weight = 0.5
        try:
            descriptive_weight = float(descriptive_weight)
        except Exception:
            descriptive_weight = 0.5

        total = numerical_weight + descriptive_weight
        if total == 0:
            numerical_weight = 0.5
            descriptive_weight = 0.5
            total = 1.0
        if total != 1.0:
            numerical_weight = numerical_weight / total
            descriptive_weight = descriptive_weight / total

        numerical_result = evaluate_numerical(question, answer_text)

        evaluation_level = (getattr(question, "evaluation_level", None) or "").strip().lower()
        embedding = getattr(question, "_embedding_service", None)
        hard_service = getattr(question, "_hard_service", None)

        if evaluation_level == "easy":
            if embedding is None:
                raise ValueError("Embedding service not available")
            descriptive_result = evaluate_easy(
                answer_text, clean_text(question.answer_key), int(question.max_marks), embedding
            )
        elif evaluation_level == "medium":
            if embedding is None:
                raise ValueError("Embedding service not available")
            descriptive_result = evaluate_medium(
                answer_text,
                clean_text(question.answer_key),
                int(question.max_marks),
                getattr(question, "concepts", None),
                embedding,
            )
        elif evaluation_level == "hard":
            if hard_service is None:
                raise ValueError("Hard evaluation is not configured")
            descriptive_result = hard_service.evaluate(question.answer_key, answer_text, int(question.max_marks))
        else:
            raise ValueError("Invalid evaluation level")

        config_missing = bool((numerical_result.get("evaluation_details") or {}).get("config_missing"))
        if config_missing:
            numerical_component = 0.0
        else:
            numerical_component = float(numerical_result.get("score", 0.0)) * float(numerical_weight)
        descriptive_component = float(descriptive_result.get("score", 0.0)) * float(descriptive_weight)
        final_score = numerical_component + descriptive_component

        return {
            "score": float(final_score),
            "feedback": "Hybrid evaluation completed.",
            "evaluation_details": {
                "numerical": numerical_result,
                "descriptive": descriptive_result,
                "weight_distribution": {
                    "numerical_weight": float(numerical_weight),
                    "descriptive_weight": float(descriptive_weight),
                },
                "components": {
                    "numerical_component": float(numerical_component),
                    "descriptive_component": float(descriptive_component),
                },
            },
        }
    except Exception as e:
        numerical_result = evaluate_numerical(question, answer_text)
        return {
            "score": 0.0,
            "feedback": "Hybrid evaluation failed.",
            "evaluation_details": {
                "numerical": numerical_result,
                "descriptive": {
                    "score": 0.0,
                    "feedback": "Descriptive evaluation unavailable.",
                    "evaluation_details": {"error": str(e)},
                },
                "weight_distribution": {
                    "numerical_weight": float(getattr(question, "hybrid_numerical_weight", None) or 0.5),
                    "descriptive_weight": float(getattr(question, "hybrid_descriptive_weight", None) or 0.5),
                },
                "components": {"numerical_component": 0.0, "descriptive_component": 0.0},
                "error": str(e),
            },
        }

