import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("El nombre está vacío")
        return cleaned


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    community_id: uuid.UUID
    filename: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    page_count: int | None = None
    created_at: datetime


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("La pregunta es demasiado corta")
        return cleaned


class Citation(BaseModel):
    document_id: uuid.UUID
    document_name: str
    page: int = Field(ge=1)
    fragment: str


class AnswerResponse(BaseModel):
    answer: str
    citations: list[Citation]
    sufficient_evidence: bool
    degraded: bool
