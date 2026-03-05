from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


EvaluationLevel = Literal["easy", "medium", "hard"]
SubmissionStatus = Literal["processing", "completed", "failed", "pending_manual_review"]
SubjectType = Literal["descriptive", "numerical", "symbolic", "mixed"]


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str


class CreateQuestionRequest(BaseModel):
    question_text: str = Field(min_length=1)
    answer_key: str = Field(min_length=1)
    max_marks: int = Field(ge=1)
    evaluation_level: EvaluationLevel
    subject_type: Optional[str] = "descriptive"
    correct_numeric_answer: Optional[float] = None
    numeric_tolerance: Optional[float] = None
    expected_unit: Optional[str] = None
    concepts: Optional[Any] = None

    @field_validator("subject_type")
    @classmethod
    def validate_subject_type(cls, v: Any) -> Any:
        if v is None:
            return "descriptive"
        if not isinstance(v, str):
            raise ValueError("subject_type must be a string")
        s = v.strip().lower()
        if s not in {"descriptive", "numerical", "symbolic", "mixed"}:
            raise ValueError("Invalid subject_type")
        return s

    @field_validator("concepts")
    @classmethod
    def validate_concepts(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            if not all(isinstance(x, str) and x.strip() for x in v):
                raise ValueError("concepts list must contain non-empty strings")
            return {"items": [x.strip() for x in v]}
        if isinstance(v, dict):
            return v
        raise ValueError("concepts must be a list of strings, an object, or null")


class CreateQuestionResponse(BaseModel):
    status: Literal["success"] = "success"
    question_id: uuid.UUID
    subject_type: Optional[str] = "descriptive"
    correct_numeric_answer: Optional[float] = None
    numeric_tolerance: Optional[float] = None
    expected_unit: Optional[str] = None


class QuestionDraft(BaseModel):
    number: int = Field(ge=1)
    question_text: str = Field(min_length=1)
    max_marks_guess: Optional[int] = Field(default=None, ge=1)
    suggested_level: EvaluationLevel = "easy"


class AnalyzeQuestionPaperResponse(BaseModel):
    status: Literal["success"] = "success"
    extracted_text: str
    questions: List[QuestionDraft]


class CreateQuestionsBatchRequest(BaseModel):
    items: List[CreateQuestionRequest] = Field(min_length=1)


class CreateQuestionsBatchResponse(BaseModel):
    status: Literal["success"] = "success"
    question_ids: List[uuid.UUID]


class SubmitAnswerResponse(BaseModel):
    status: Literal["success"] = "success"
    submission_id: uuid.UUID


class EvaluateResponse(BaseModel):
    status: Literal["success"] = "success"
    submission_id: uuid.UUID
    question_id: uuid.UUID
    evaluation_level: EvaluationLevel
    extracted_text: Optional[str]
    score: Optional[float]
    max_marks: int
    feedback: Optional[str]
    submission_status: SubmissionStatus
    created_at: datetime


class SubmissionResponse(BaseModel):
    status: Literal["success"] = "success"
    submission_id: uuid.UUID
    question_id: uuid.UUID
    student_image_path: str
    extracted_text: Optional[str]
    score: Optional[float]
    feedback: Optional[str]
    submission_status: SubmissionStatus
    created_at: datetime


class RubricResult(BaseModel):
    accuracy: int
    completeness: int
    depth: int
    clarity: int
    total: int
    feedback: str

    @field_validator("accuracy", "completeness", "depth", "clarity", "total")
    @classmethod
    def validate_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("rubric scores must be non-negative")
        return v

