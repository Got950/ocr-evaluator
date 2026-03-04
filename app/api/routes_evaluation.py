from __future__ import annotations

import logging
import uuid
from typing import Optional

import anyio
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import EvaluationLog, Question, Submission, SessionLocal, get_db
from app.models.schemas import ErrorResponse, EvaluateResponse, SubmissionResponse
from app.services.evaluation_hard import HardEvaluationService
from app.services.engine_router import route_engine
from app.services.segmentation_service import segment_answers
from app.utils.text_cleaning import clean_text


router = APIRouter(tags=["evaluation"])


logger = logging.getLogger("ocr_evaluator.evaluation")


async def _process_submission(submission_id: uuid.UUID, app: object) -> None:
    """Background task — uses its own sync session (runs CPU-bound work in threads)."""
    db = SessionLocal()
    extracted: Optional[str] = None
    sem = getattr(app.state, "eval_semaphore", None)
    acquired = False
    try:
        if sem is not None:
            await sem.acquire()
            acquired = True

        sub = db.get(Submission, submission_id)
        if sub is None:
            return

        sub.status = "processing"
        sub.feedback = None
        sub.evaluation_details = None
        sub.per_question_scores = None
        sub.total_score = None
        sub.percentage = None
        sub.final_score = None
        db.commit()

        ocr = app.state.ocr_service
        embedding = app.state.embedding_service
        hard_service: Optional[HardEvaluationService] = app.state.hard_evaluation_service
        settings = app.state.settings

        extracted = await anyio.to_thread.run_sync(ocr.extract_text, sub.student_image_path)
        cleaned = clean_text(extracted)

        if not getattr(settings, "ai_grading_enabled", True):
            sub.extracted_text = extracted
            sub.status = "pending_manual_review"
            sub.feedback = "Pending manual review"
            sub.evaluation_details = {"mode": "pending_manual_review"}
            db.add(
                EvaluationLog(
                    submission_id=sub.id,
                    evaluation_snapshot={
                        "type": "pending_manual_review",
                        "ai_grading_enabled": False,
                    },
                )
            )
            db.commit()
            return

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
                q._embedding_service = embedding
                q._hard_service = hard_service
                r = await anyio.to_thread.run_sync(route_engine, q, answer)
                if (q.evaluation_level or "").lower().strip() == "medium" and q.concepts is None:
                    concept_similarity = (r.get("evaluation_details") or {}).get("concept_similarity") or {}
                    if isinstance(concept_similarity, dict):
                        q.concepts = {"items": list(concept_similarity.keys())}
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
            override_sum = 0.0
            for v in manual_override.values():
                try:
                    override_sum += float(v)
                except Exception:
                    continue
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
                    "percentage": float(percentage),
                    "manual_override": manual_override,
                    "final_score": float(final_score),
                    "evaluation_details": sub.evaluation_details,
                },
            )
        )
        db.commit()
    except Exception as e:
        logger.exception("Evaluation failed: %s", str(submission_id))
        try:
            sub = db.get(Submission, submission_id)
            if sub is not None:
                if extracted is not None:
                    sub.extracted_text = extracted
                sub.status = "failed"
                sub.feedback = str(e)
                sub.evaluation_details = None
                sub.per_question_scores = None
                sub.total_score = None
                sub.percentage = None
                sub.final_score = None
                db.add(
                    EvaluationLog(
                        submission_id=sub.id,
                        evaluation_snapshot={
                            "type": "error",
                            "error": str(e),
                            "error_type": e.__class__.__name__,
                        },
                    )
                )
                db.commit()
        finally:
            pass
    finally:
        if acquired and sem is not None:
            try:
                sem.release()
            except Exception:
                pass
        db.close()


def schedule_submission_processing(app: object, background_tasks: BackgroundTasks, submission_id: uuid.UUID) -> None:
    """Dispatch to Celery if available, otherwise use in-process BackgroundTask."""
    try:
        from app.tasks.grading_tasks import process_submission as celery_task
        celery_task.delay(str(submission_id))
        logger.info("Dispatched to Celery: %s", submission_id)
    except Exception:
        background_tasks.add_task(_process_submission, submission_id, app)
        logger.info("Dispatched to BackgroundTask (Celery unavailable): %s", submission_id)


@router.post(
    "/evaluate/{submission_id}",
    response_model=EvaluateResponse,
    responses={400: {"model": ErrorResponse}},
)
async def evaluate_submission(
    request: Request,
    submission_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> EvaluateResponse:
    try:
        sid = uuid.UUID(submission_id)
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid submission_id"})

    sub = await db.get(Submission, sid)
    if sub is None:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Submission not found"})
    q = await db.get(Question, sub.question_id)
    if q is None:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Question not found"})

    settings = request.app.state.settings
    if sub.status != "completed" and getattr(settings, "ai_grading_enabled", True):
        schedule_submission_processing(request.app, background_tasks, sub.id)

    return EvaluateResponse(
        submission_id=sub.id,
        question_id=q.id,
        evaluation_level=q.evaluation_level,  # type: ignore[arg-type]
        extracted_text=sub.extracted_text,
        score=sub.score,
        max_marks=q.max_marks,
        feedback=sub.feedback,
        submission_status=sub.status,  # type: ignore[arg-type]
        created_at=sub.created_at,
    )


@router.get("/admin/exam-status")
async def admin_exam_status(db: AsyncSession = Depends(get_db)) -> dict:
    total = (await db.execute(select(func.count(Submission.id)))).scalar() or 0
    processing = (await db.execute(select(func.count(Submission.id)).where(Submission.status == "processing"))).scalar() or 0
    completed = (await db.execute(select(func.count(Submission.id)).where(Submission.status == "completed"))).scalar() or 0
    failed = (await db.execute(select(func.count(Submission.id)).where(Submission.status == "failed"))).scalar() or 0
    pending = (await db.execute(select(func.count(Submission.id)).where(Submission.status == "pending_manual_review"))).scalar() or 0
    return {
        "total_submissions": int(total),
        "processing": int(processing),
        "completed": int(completed),
        "failed": int(failed),
        "pending_manual_review": int(pending),
    }


@router.get(
    "/submission/{submission_id}",
    responses={400: {"model": ErrorResponse}},
)
async def get_submission(submission_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        sid = uuid.UUID(submission_id)
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid submission_id"})

    sub = await db.get(Submission, sid)
    if sub is None:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Submission not found"})

    return {
        "status": "success",
        "submission_id": sub.id,
        "question_id": sub.question_id,
        "student_image_path": sub.student_image_path,
        "extracted_text": sub.extracted_text,
        "score": sub.score,
        "total_score": getattr(sub, "total_score", None),
        "percentage": getattr(sub, "percentage", None),
        "final_score": getattr(sub, "final_score", None),
        "feedback": sub.feedback,
        "evaluation_details": getattr(sub, "evaluation_details", None),
        "per_question_scores": getattr(sub, "per_question_scores", None),
        "submission_status": sub.status,
        "created_at": sub.created_at,
    }


@router.post(
    "/submission/{submission_id}/override",
    responses={400: {"model": ErrorResponse}},
)
async def override_submission_score(
    submission_id: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        sid = uuid.UUID(submission_id)
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid submission_id"})

    sub = await db.get(Submission, sid)
    if sub is None:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Submission not found"})

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid override payload"})

    normalized: dict = {}
    total = 0.0
    for k, v in payload.items():
        try:
            qn = int(k)
            sv = float(v)
        except Exception:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "Override keys/values must be numeric"})
        if qn <= 0 or sv < 0:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "Override values must be non-negative"})
        normalized[str(qn)] = float(sv)
        total += float(sv)

    sub.manual_override = normalized
    sub.final_score = float(total)
    sub.score = float(total)

    db.add(
        EvaluationLog(
            submission_id=sub.id,
            evaluation_snapshot={
                "type": "manual_override",
                "manual_override": normalized,
                "final_score": float(total),
            },
        )
    )
    await db.commit()

    return {"status": "success", "submission_id": sub.id, "manual_override": normalized, "final_score": float(total)}
