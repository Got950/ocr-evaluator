from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
import warnings

warnings.filterwarnings("ignore", message=".*torchvision.datapoints.*")
warnings.filterwarnings("ignore", message=".*torchvision.transforms.v2.*")
warnings.filterwarnings("ignore", message=".*Some weights of.*were not initialized.*")

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.api.routes_auth import router as auth_router
from app.api.routes_evaluation import router as evaluation_router
from app.api.routes_professor import router as professor_router
from app.api.routes_student import router as student_router
from app.config import get_settings
from app.models.database import Base, engine, async_engine
from app.services.embedding_service import EmbeddingService
from app.services.evaluation_hard import HardEvaluationService
from app.services.ocr_service import OCRService
from app.services.storage_service import StorageService

import subprocess


app = FastAPI()

def _env_flag(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return bool(default)
    return v in {"1", "true", "yes", "y", "on"}


# Middleware must be configured before the app starts.
try:
    gzip_min = int((os.getenv("GZIP_MINIMUM_SIZE") or "1000").strip())
except Exception:
    gzip_min = 1000
if gzip_min > 0:
    app.add_middleware(GZipMiddleware, minimum_size=gzip_min)

trusted = (os.getenv("TRUSTED_HOSTS") or "*").strip()
hosts = [h.strip() for h in trusted.split(",") if h.strip()]
if hosts and hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

cors = (os.getenv("CORS_ORIGINS") or "").strip()
if cors:
    origins = [o.strip() for o in cors.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

app.state.enable_security_headers = _env_flag("ENABLE_SECURITY_HEADERS", default=True)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper().strip()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


logger = logging.getLogger("ocr_evaluator")

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = (request.headers.get("x-request-id") or request.headers.get("X-Request-ID") or "").strip()
    if not request_id:
        request_id = str(uuid.uuid4())

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0

    response.headers.setdefault("X-Request-ID", request_id)

    settings = getattr(request.app.state, "settings", None)
    enable_sec = (
        bool(getattr(settings, "enable_security_headers", True)) if settings is not None else bool(getattr(request.app.state, "enable_security_headers", True))
    )
    if enable_sec:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

    client_ip = getattr(getattr(request, "client", None), "host", None) or "-"
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f request_id=%s client_ip=%s",
        request.method,
        request.url.path,
        getattr(response, "status_code", "-"),
        duration_ms,
        request_id,
        client_ip,
    )
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail: Any = exc.detail
    if isinstance(detail, dict) and detail.get("status") == "error" and isinstance(detail.get("message"), str):
        payload = detail
    else:
        payload = {"status": "error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    msg = "Validation error"
    errs = exc.errors()
    if errs:
        loc = ".".join(str(x) for x in errs[0].get("loc", []) if x is not None)
        detail = errs[0].get("msg", "")
        msg = f"{loc}: {detail}".strip(": ")
    return JSONResponse(status_code=422, content={"status": "error", "message": msg})


@app.on_event("startup")
def startup() -> None:
    _configure_logging()
    settings = get_settings()
    app.state.settings = settings
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    app.state.enable_security_headers = bool(getattr(settings, "enable_security_headers", True))

    # In development, auto-run Alembic migrations.
    # In production, run `alembic upgrade head` as a separate deploy step.
    if settings.environment == "dev":
        try:
            subprocess.run(
                ["py", "-m", "alembic", "upgrade", "head"],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Alembic migrations applied")
        except Exception:
            logger.warning("Alembic migration failed, falling back to create_all")
            Base.metadata.create_all(bind=engine)
    else:
        Base.metadata.create_all(bind=engine)

    try:
        app.state.eval_semaphore = asyncio.Semaphore(int(settings.max_concurrent_evaluations))
        app.state.max_concurrent_evaluations = int(settings.max_concurrent_evaluations)
        app.state.rate_limit_hits = {}
        app.state.rate_limit_window_seconds = 60
        app.state.rate_limit_max_per_window = 20
        import threading

        app.state.rate_limit_lock = threading.Lock()

        try:
            app.state.ocr_service = OCRService.load()
            app.state.trocr_available = True
        except Exception:
            logger.critical("TrOCR failed to load, falling back to Poppler-only mode")
            app.state.ocr_service = None
            app.state.trocr_available = False

        app.state.embedding_service = EmbeddingService.load()
        app.state.hard_evaluation_service = HardEvaluationService.from_import_path(settings.hard_rubric_evaluator)

        if settings.s3_bucket:
            app.state.storage_service = StorageService.from_settings()
            logger.info("S3 storage enabled: bucket=%s", settings.s3_bucket)
        else:
            app.state.storage_service = None
    except Exception:
        logger.exception("Startup failed")
        raise

    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown() -> None:
    sem = getattr(app.state, "eval_semaphore", None)
    max_n = int(getattr(app.state, "max_concurrent_evaluations", 0) or 0)
    if sem is None or max_n <= 0:
        return

    acquired = 0
    for _ in range(max_n):
        try:
            await asyncio.wait_for(sem.acquire(), timeout=30.0)
            acquired += 1
        except Exception:
            break
    for _ in range(acquired):
        sem.release()


@app.get("/health")
async def health() -> dict:
    db_status = "ok"
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        import torch

        gpu_available = bool(torch.cuda.is_available())
    except Exception:
        gpu_available = False

    return {
        "database": db_status,
        "gpu_available": gpu_available,
        "trocr_available": bool(getattr(app.state, "trocr_available", False)),
        "ocr_model_loaded": bool(getattr(app.state, "ocr_service", None) is not None),
        "embedding_model_loaded": bool(getattr(app.state, "embedding_service", None) is not None),
        "ai_grading_enabled": bool(getattr(app.state, "settings", None) and app.state.settings.ai_grading_enabled),
    }


API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(professor_router, prefix=API_PREFIX)
app.include_router(student_router, prefix=API_PREFIX)
app.include_router(evaluation_router, prefix=API_PREFIX)

frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
