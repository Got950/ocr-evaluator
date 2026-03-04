from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.worker import celery_app
from app.models.database import EvaluationLog, Question, Submission, SessionLocal
from app.services.evaluation_hard import HardEvaluationService
from app.services.embedding_service import EmbeddingService
from app.services.ocr_service import OCRService
from app.services.engine_router import route_engine
from app.services.segmentation_service import segment_answers
from app.utils.text_cleaning import clean_text
from app.config import get_settings

logger = logging.getLogger("ocr_evaluator.celery_task")

_ocr: Optional[OCRService] = None
_embedding: Optional[EmbeddingService] = None
_hard_service: Optional[HardEvaluationService] = None


def _load_models() -> None:
    global _ocr, _embedding, _hard_service
    if _ocr is None:
        _ocr = OCRService.load()
    if _embedding is None:
        _embedding = EmbeddingService.load()
    if _hard_service is None:
        settings = get_settings()
        _hard_service = HardEvaluationService.from_import_path(settings.hard_rubric_evaluator)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_submission(self, submission_id: str) -> dict:
    sid = uuid.UUID(submission_id)
    logger.info("Celery task started: submission=%s", submission_id)

    _load_models()
    settings = get_settings()
    db = SessionLocal()
    extracted: Optional[str] = None

    try:
        sub = db.get(Submission, sid)
        if sub is None:
            return {"status": "not_found"}

        sub.status = "processing"
        sub.feedback = None
        sub.evaluation_details = None
        sub.per_question_scores = None
        sub.total_score = None
        sub.percentage = None
        sub.final_score = None
        db.commit()

        extracted = _ocr.extract_text(sub.student_image_path)
        cleaned = clean_text(extracted)

        if not getattr(settings, "ai_grading_enabled", True):
            sub.extracted_text = extracted
            sub.status = "pending_manual_review"
            sub.feedback = "Pending manual review"
            sub.evaluation_details = {"mode": "pending_manual_review"}
            db.add(
                EvaluationLog(
                    submission_id=sub.id,
                    evaluation_snapshot={"type": "pending_manual_review", "ai_grading_enabled": False},
                )
            )
            db.commit()
            logger.info("Safe mode: submission=%s -> pending_manual_review", submission_id)
            return {"status": "pending_manual_review"}

        segments = segment_answers(cleaned)
        questions = db.query(Question).order_by(Question.created_at.asc()).all()
        if not questions:
            raise ValueError("No questions available for evaluation")

        per_question_scores: dict = {}
        total_score = 0.0
        total_max = 0.0
        for idx, q in enumerate(questions, start=1):
            answer = segments.get(idx, "")
            if not answer:
                q_score = 0.0
                q_details = {"missing": True}
            else:
                q._embedding_service = _embedding
                q._hard_service = _hard_service
                r = route_engine(q, answer)
                q_score = float(r["score"])
                q_details = r["evaluation_details"]

            per_question_scores[str(idx)] = {
                "score": float(q_score),
                "max_marks": int(q.max_marks),
                "evaluation_details": q_details,
            }
            total_score += float(q_score)
            total_max += float(q.max_marks)

        percentage = float(total_score / total_max) if total_max > 0 else 0.0

        manual_override = getattr(sub, "manual_override", None)
        final_score = float(total_score)
        if isinstance(manual_override, dict) and manual_override:
            override_sum = sum(float(v) for v in manual_override.values())
            final_score = float(override_sum)

        sub.extracted_text = extracted
        sub.per_question_scores = per_question_scores
        sub.total_score = float(total_score)
        sub.percentage = float(percentage)
        sub.final_score = float(final_score)
        sub.score = float(final_score)
        sub.feedback = f"Booklet evaluated. Total {total_score:.2f}/{total_max:.2f}."
        sub.evaluation_details = {"mode": "booklet", "segmented_questions": len(segments), "total_questions": len(questions)}
        sub.status = "completed"

        db.add(
            EvaluationLog(
                submission_id=sub.id,
                evaluation_snapshot={
                    "type": "evaluation",
                    "per_question_scores": per_question_scores,
                    "total_score": float(total_score),
                    "total_max": float(total_max),
                    "final_score": float(final_score),
                },
            )
        )
        db.commit()
        logger.info("Celery task completed: submission=%s score=%.2f", submission_id, final_score)
        return {"status": "completed", "final_score": final_score}

    except Exception as exc:
        logger.exception("Celery task failed: submission=%s", submission_id)
        try:
            sub = db.get(Submission, sid)
            if sub is not None:
                if extracted is not None:
                    sub.extracted_text = extracted
                sub.status = "failed"
                sub.feedback = str(exc)
                db.add(
                    EvaluationLog(
                        submission_id=sub.id,
                        evaluation_snapshot={"type": "error", "error": str(exc), "error_type": exc.__class__.__name__},
                    )
                )
                db.commit()
        except Exception:
            pass

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
