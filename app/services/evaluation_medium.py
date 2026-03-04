from __future__ import annotations

import re
from typing import Optional

from app.services.embedding_service import EmbeddingService


_SENT_SPLIT = re.compile(r"[.!?]+")


def _extract_concepts(answer_key: str, n: int = 5) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(answer_key) if p and p.strip()]
    concepts: list[str] = []
    for p in parts:
        if p not in concepts:
            concepts.append(p)
        if len(concepts) >= n:
            break
    return concepts


def _iter_concepts(concepts_obj: Optional[object], answer_key: str) -> list[str]:
    if concepts_obj is None:
        return _extract_concepts(answer_key, n=5)
    if isinstance(concepts_obj, dict):
        items = concepts_obj.get("items")
        if isinstance(items, list) and all(isinstance(x, str) for x in items):
            return [x.strip() for x in items if x and x.strip()]
    if isinstance(concepts_obj, list) and all(isinstance(x, str) for x in concepts_obj):
        return [x.strip() for x in concepts_obj if x and x.strip()]
    return _extract_concepts(answer_key, n=5)


def evaluate_medium(
    student_text: str,
    answer_key: str,
    max_marks: int,
    concepts_obj: Optional[object],
    embedding: EmbeddingService,
) -> dict:
    concepts = _iter_concepts(concepts_obj, answer_key)
    if not concepts:
        return {
            "score": 0.0,
            "feedback": "No concepts available for evaluation.",
            "evaluation_details": {"matched_concepts": 0, "total_concepts": 0, "concept_similarity": {}},
        }

    concept_similarity: dict = {}
    matched_count = 0
    for c in concepts:
        sim = embedding.similarity(student_text, c)
        concept_similarity[c] = float(sim)
        if sim > 0.6:
            matched_count += 1

    score = (matched_count / len(concepts)) * float(max_marks)
    feedback = f"Matched {matched_count}/{len(concepts)} concepts."
    return {
        "score": float(score),
        "feedback": feedback,
        "evaluation_details": {
            "matched_concepts": int(matched_count),
            "total_concepts": int(len(concepts)),
            "concept_similarity": concept_similarity,
        },
    }

