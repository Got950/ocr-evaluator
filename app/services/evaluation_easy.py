from __future__ import annotations

from app.services.embedding_service import EmbeddingService


def evaluate_easy(student_text: str, answer_key: str, max_marks: int, embedding: EmbeddingService) -> dict:
    sim = embedding.similarity(student_text, answer_key)
    raw = sim * float(max_marks)
    score = max(0.0, min(float(max_marks), raw))
    feedback = f"Similarity: {sim:.4f}"
    return {"score": float(score), "feedback": feedback, "evaluation_details": {"similarity_score": float(sim)}}

