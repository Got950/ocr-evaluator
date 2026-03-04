from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Question, Submission, User, get_db
from app.models.schemas import ErrorResponse, SubmitAnswerResponse
from app.dependencies import require_student


router = APIRouter(tags=["student"])


logger = logging.getLogger("ocr_evaluator.student")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limit_or_429(request: Request) -> None:
    settings = request.app.state.settings
    if not getattr(settings, "enable_rate_limiting", True):
        return

    hits = getattr(request.app.state, "rate_limit_hits", None)
    lock = getattr(request.app.state, "rate_limit_lock", None)
    window = int(getattr(request.app.state, "rate_limit_window_seconds", 60) or 60)
    max_hits = int(getattr(request.app.state, "rate_limit_max_per_window", 20) or 20)
    if hits is None or lock is None:
        return

    now = time.time()
    ip = _client_ip(request)
    with lock:
        arr = hits.get(ip) or []
        cutoff = now - float(window)
        arr = [t for t in arr if t >= cutoff]
        if len(arr) >= max_hits:
            raise HTTPException(status_code=429, detail={"status": "error", "message": "Rate limit exceeded"})
        arr.append(now)
        hits[ip] = arr


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
    "/student/submit-answer",
    response_model=SubmitAnswerResponse,
    responses={400: {"model": ErrorResponse}},
)
async def submit_answer(
    request: Request,
    background_tasks: BackgroundTasks,
    question_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_student),
) -> SubmitAnswerResponse:
    _rate_limit_or_429(request)
    try:
        qid = uuid.UUID(question_id)
    except Exception:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid question_id"})

    settings = request.app.state.settings
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Only PDF uploads are allowed"})

    ext = _safe_ext(file.filename or "")
    if not ext:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid PDF file extension"})

    question = await db.get(Question, qid)
    if question is None:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Question not found"})

    storage = getattr(request.app.state, "storage_service", None)
    if storage is not None:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "PDF is empty"})
        if len(file_bytes) > settings.max_upload_size_bytes:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "Upload too large"})
        s3_key = await storage.upload_file(file_bytes, f"{uuid.uuid4()}{ext}", file.content_type or "application/pdf")
        pdf_path = f"s3://{s3_key}"
    else:
        unique_name = f"{uuid.uuid4()}{ext}"
        dest = Path(settings.upload_dir) / unique_name
        try:
            await _save_upload_limited(file, dest, settings.max_upload_size_bytes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"status": "error", "message": str(e)})
        if dest.stat().st_size == 0:
            raise HTTPException(status_code=400, detail={"status": "error", "message": "PDF is empty"})
        pdf_path = str(dest)

    sub = Submission(
        question_id=question.id,
        student_image_path=pdf_path,
        status="processing",
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)

    from app.api.routes_evaluation import schedule_submission_processing

    schedule_submission_processing(request.app, background_tasks, sub.id)

    logger.info("Submission accepted: %s", str(sub.id))
    return SubmitAnswerResponse(submission_id=sub.id)
