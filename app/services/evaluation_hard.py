from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from app.models.schemas import RubricResult


class RubricEvaluator(Protocol):
    def evaluate_with_rubric(self, answer_key: str, student_answer: str, max_marks: int) -> dict[str, Any]:
        ...


def _import_from_path(import_path: str) -> Any:
    if ":" in import_path:
        module_name, attr = import_path.split(":", 1)
    elif "." in import_path:
        module_name, attr = import_path.rsplit(".", 1)
    else:
        raise ValueError("Invalid import path for HARD_RUBRIC_EVALUATOR")
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


@dataclass(frozen=True)
class HardEvaluationService:
    evaluator: RubricEvaluator

    @classmethod
    def from_import_path(cls, import_path: Optional[str]) -> Optional["HardEvaluationService"]:
        if not import_path:
            return None
        obj = _import_from_path(import_path)
        evaluator = obj() if callable(obj) else obj
        if not hasattr(evaluator, "evaluate_with_rubric"):
            raise ValueError("HARD_RUBRIC_EVALUATOR must provide evaluate_with_rubric(answer_key, student_answer, max_marks)")
        return cls(evaluator=evaluator)

    def evaluate(self, answer_key: str, student_answer: str, max_marks: int) -> dict:
        raw = self.evaluator.evaluate_with_rubric(answer_key, student_answer, max_marks)
        result = RubricResult.model_validate(raw)
        if result.total > max_marks:
            raise ValueError("Rubric total exceeds max_marks")
        return {
            "score": float(result.total),
            "feedback": str(result.feedback),
            "evaluation_details": {
                "accuracy": int(result.accuracy),
                "completeness": int(result.completeness),
                "depth": int(result.depth),
                "clarity": int(result.clarity),
            },
        }

