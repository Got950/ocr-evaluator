from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Question, get_db
from app.models.schemas import (
    AnalyzeQuestionPaperResponse,
    CreateQuestionRequest,
    CreateQuestionResponse,
    CreateQuestionsBatchRequest,
    CreateQuestionsBatchResponse,
    ErrorResponse,
    QuestionDraft,
)
from app.services.question_paper_parser import parse_question_paper
from app.models.database import User
from app.dependencies import require_professor


router = APIRouter(tags=["professor"])


logger = logging.getLogger("ocr_evaluator.professor")


def _safe_ext(filename: str) -> str:
    base, ext = os.path.splitext(filename or "")
    ext = (ext or "").lower()
    if ext in {".pdf"}:
        return ext
    return ""


async def _save_upload_limited(file: UploadFile, dest: Path, max_bytes: int) -> None:
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Upload too large")
                f.write(chunk)
    except Exception:
        try:
            if dest.exists():
                dest.unlink()
        finally:
            raise
    finally:
        await file.close()


@router.post(
    "/professor/analyze-question-paper",
    response_model=AnalyzeQuestionPaperResponse,
    responses={400: {"model": ErrorResponse}},
)
async def analyze_question_paper(request: Request, file: UploadFile = File(...), current_user: User = Depends(require_professor)) -> AnalyzeQuestionPaperResponse:
    settings = request.app.state.settings
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Only PDF uploads are allowed"})

    ext = _safe_ext(file.filename or "")
    if not ext:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid PDF file extension"})

    storage = getattr(request.app.state, "storage_service", None)
    if storage is not None:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "PDF is empty"})
        if len(file_bytes) > settings.max_upload_size_bytes:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "Upload too large"})
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(file_bytes)
        tmp.close()
        ocr_path = tmp.name
    else:
        unique_name = f"question_paper_{uuid.uuid4()}{ext}"
        dest = Path(settings.upload_dir) / unique_name
        try:
            await _save_upload_limited(file, dest, settings.max_upload_size_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"status": "error", "message": str(e)})
        if dest.stat().st_size == 0:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "PDF is empty"})
        ocr_path = str(dest)

    ocr = request.app.state.ocr_service
    sem = getattr(request.app.state, "eval_semaphore", None)
    acquired = False
    try:
        if sem is not None:
            await sem.acquire()
            acquired = True
        extracted_text = await anyio.to_thread.run_sync(ocr.extract_text, ocr_path)
    except Exception as e:
        logger.exception("Question paper OCR failed")
        raise HTTPException(status_code=400, detail={"status": "error", "message": f"OCR failed: {e}"})
    finally:
        if acquired and sem is not None:
            try:
                sem.release()
            except Exception:
                pass
    drafts = parse_question_paper(extracted_text)

    return AnalyzeQuestionPaperResponse(
        extracted_text=extracted_text,
        questions=[
            QuestionDraft(
                number=int(d["number"]),
                question_text=str(d["question_text"]),
                max_marks_guess=d.get("max_marks_guess"),
                suggested_level="easy",
            )
            for d in drafts
        ],
    )


@router.get("/professor/questions")
async def list_questions(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_professor)) -> dict:
    result = await db.execute(select(Question).order_by(Question.created_at.asc()))
    qs = result.scalars().all()
    return {
        "status": "success",
        "questions": [
            {
                "id": str(q.id),
                "question_text": q.question_text[:100] + ("..." if len(q.question_text) > 100 else ""),
                "max_marks": q.max_marks,
                "evaluation_level": q.evaluation_level,
            }
            for q in qs
        ],
    }


@router.post(
    "/professor/create-question",
    response_model=CreateQuestionResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_question(payload: CreateQuestionRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_professor)) -> CreateQuestionResponse:
    try:
        q = Question(
            subject_type=payload.subject_type,
            correct_numeric_answer=payload.correct_numeric_answer,
            numeric_tolerance=payload.numeric_tolerance,
            expected_unit=payload.expected_unit,
            question_text=payload.question_text,
            answer_key=payload.answer_key,
            max_marks=payload.max_marks,
            evaluation_level=payload.evaluation_level,
            concepts=payload.concepts,
        )
        db.add(q)
        await db.commit()
        await db.refresh(q)
        return CreateQuestionResponse(question_id=q.id)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"status": "error", "message": str(e)})


@router.post(
    "/professor/create-questions-batch",
    response_model=CreateQuestionsBatchResponse,
    responses={400: {"model": ErrorResponse}},
)
async def create_questions_batch(
    payload: CreateQuestionsBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_professor),
) -> CreateQuestionsBatchResponse:
    try:
        ids = []
        for item in payload.items:
            q = Question(
                subject_type=item.subject_type,
                correct_numeric_answer=item.correct_numeric_answer,
                numeric_tolerance=item.numeric_tolerance,
                expected_unit=item.expected_unit,
                question_text=item.question_text,
                answer_key=item.answer_key,
                max_marks=item.max_marks,
                evaluation_level=item.evaluation_level,
                concepts=item.concepts,
            )
            db.add(q)
            await db.flush()
            ids.append(q.id)
        await db.commit()
        return CreateQuestionsBatchResponse(question_ids=ids)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail={"status": "error", "message": str(e)})
