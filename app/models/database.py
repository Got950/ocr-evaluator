from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SubjectType(str, enum.Enum):
    descriptive = "descriptive"
    numerical = "numerical"
    symbolic = "symbolic"
    mixed = "mixed"


class Base(DeclarativeBase):
    pass


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    institution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True)
    subject_type = Column(String(20), nullable=False, default="descriptive")
    correct_numeric_answer = Column(Float, nullable=True)
    numeric_tolerance = Column(Float, nullable=True, default=0.01)
    expected_unit = Column(String(50), nullable=True)
    hybrid_numerical_weight = Column(Float, nullable=True)
    hybrid_descriptive_weight = Column(Float, nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_key: Mapped[str] = mapped_column(Text, nullable=False)
    max_marks: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_level: Mapped[str] = mapped_column(String(16), nullable=False)
    concepts: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    submissions: Mapped[List["Submission"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", lazy="selectin"
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("institutions.id"), nullable=True)
    question_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("questions.id"), nullable=False)
    student_image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_details = Column(JSONB, nullable=True)
    per_question_scores = Column(JSONB, nullable=True)
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manual_override = Column(JSONB, nullable=True)
    final_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="processing")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    question: Mapped["Question"] = relationship(back_populates="submissions", lazy="joined")


class EvaluationLog(Base):
    __tablename__ = "evaluation_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("submissions.id"), nullable=False)
    evaluation_snapshot = Column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


_settings = get_settings()

_raw_url = str(_settings.database_url)

# Async engine (primary, used by the web app)
_async_url = _raw_url
if _async_url.startswith("postgresql+psycopg2://"):
    _async_url = _async_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
elif _async_url.startswith("postgresql://"):
    _async_url = _async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

async_engine = create_async_engine(
    _async_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
)
AsyncSessionLocal = sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine (used by Alembic, Celery workers, and legacy code paths)
_sync_url = _raw_url
if _sync_url.startswith("postgresql+asyncpg://"):
    _sync_url = _sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)

engine = create_engine(_sync_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_sync_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# SQL MIGRATION FOR NUMERICAL SUPPORT
# Run in PostgreSQL:
# ALTER TABLE questions ADD COLUMN IF NOT EXISTS correct_numeric_answer DOUBLE PRECISION;
# ALTER TABLE questions ADD COLUMN IF NOT EXISTS numeric_tolerance DOUBLE PRECISION DEFAULT 0.01;
# ALTER TABLE questions ADD COLUMN IF NOT EXISTS expected_unit VARCHAR(50);
# ALTER TABLE questions ADD COLUMN IF NOT EXISTS hybrid_numerical_weight DOUBLE PRECISION;
# ALTER TABLE questions ADD COLUMN IF NOT EXISTS hybrid_descriptive_weight DOUBLE PRECISION;

# SQL MIGRATION FOR STATUS LENGTH FIX
# Run in PostgreSQL:
# ALTER TABLE submissions ALTER COLUMN status TYPE VARCHAR(32);
