from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=15)
    customer_context: str | None = Field(default=None, max_length=4000)
    customer_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Question must contain at least 3 non-whitespace characters.")
        return value


class Source(BaseModel):
    document_id: str
    chunk_id: str
    title: str
    url: str
    section: str
    excerpt: str
    relevance: float = Field(ge=0, le=1)
    images: list[dict[str, str]] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    status: Literal["answered", "insufficient_evidence", "needs_human"]
    sources: list[Source]
    image_references: list[dict[str, str]]
    needs_human: bool
    escalation_reason: str | None = None
    escalation_id: str | None = None


class APIError(BaseModel):
    code: str
    message: str
    request_id: str
    errors: list[dict[str, str]] | None = None


class IngestionRequest(BaseModel):
    sitemap_url: HttpUrl | None = None
    max_pages: int | None = Field(default=None, ge=1, le=1000)


class EscalationCreate(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    reason: str = Field(min_length=3, max_length=2000)
    evidence: list[dict[str, object]] = Field(default_factory=list)
    customer_context: str | None = Field(default=None, max_length=4000)
    customer_id: str | None = Field(default=None, min_length=1, max_length=200)


class ReviewedKnowledge(BaseModel):
    answer: str = Field(min_length=3, max_length=10000)
    source_url: str | None = None
    supporting_evidence: list[dict[str, object]] = Field(default_factory=list)
    reviewed_by: str = Field(min_length=1, max_length=200)
    applicability: Literal["customer_specific", "general"] = "customer_specific"
    customer_id: str | None = Field(default=None, min_length=1, max_length=200)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must include a timezone, preferably UTC.")
        if value is not None and value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future.")
        return value

    @field_validator("customer_id")
    @classmethod
    def customer_id_required_for_scoped_answer(cls, value: str | None, info):
        if info.data.get("applicability", "customer_specific") == "customer_specific" and not value:
            raise ValueError("customer_id is required for customer-specific knowledge.")
        if info.data.get("applicability") == "general" and value:
            raise ValueError("General knowledge cannot be assigned to a customer_id.")
        return value


class EscalationResolve(ReviewedKnowledge):
    pass


class ExpertKnowledgeRevision(ReviewedKnowledge):
    pass


class EvaluationCaseReview(BaseModel):
    actual_result: dict[str, object]
    passed: bool
    reviewed_by: str = Field(min_length=1, max_length=200)