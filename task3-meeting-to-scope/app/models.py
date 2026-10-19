from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SourceReference(BaseModel):
    meeting_id: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    speaker: str
    quote: str = Field(min_length=1, max_length=2000)


class FeasibilityResult(BaseModel):
    classification: Literal[
        "existing_configuration",
        "existing_feature_with_limitation",
        "potential_custom_development",
        "needs_clarification",
    ] = "needs_clarification"
    rationale: str = "Not yet assessed."
    sources: list[dict[str, object]] = Field(default_factory=list)
    needs_human: bool = True


class Requirement(BaseModel):
    requirement_id: str = Field(pattern=r"^REQ-[A-Fa-f0-9]{8}$")
    description: str = Field(min_length=3, max_length=1200)
    details: str = Field(default="", max_length=2000)
    origin: Literal["explicit", "inferred"] = "explicit"
    status: Literal["confirmed", "unclear", "disputed"] = "confirmed"
    priority: Literal["must_have", "should_have", "optional", "unknown"] = "unknown"
    acceptance_criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(min_length=1)
    feasibility: FeasibilityResult = Field(default_factory=FeasibilityResult)
    change_action: Literal["none", "add", "modify", "remove"] = "none"


class TranscriptAnalysis(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    constraint_references: list[SourceReference] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    analyst_model: str = "rules-v1"


class EstimateTask(BaseModel):
    task_id: str
    requirement_id: str
    name: str
    reasoning: str
    low_hours: float = Field(ge=0)
    likely_hours: float = Field(ge=0)
    high_hours: float = Field(ge=0)
    assumptions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"

    @model_validator(mode="after")
    def validate_estimate_range(self):
        if not self.low_hours <= self.likely_hours <= self.high_hours:
            raise ValueError("Estimate must satisfy low_hours <= likely_hours <= high_hours.")
        return self


class EstimateSummary(BaseModel):
    tasks: list[EstimateTask] = Field(default_factory=list)
    low_hours: float = 0
    likely_hours: float = 0
    high_hours: float = 0
    pricing: None = None
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ScopeDocument(BaseModel):
    objective: str
    current_problem: str
    agreed_requirements: list[Requirement]
    proposed_solution: list[str]
    deliverables: list[str]
    exclusions: list[str]
    assumptions: list[str]
    dependencies: list[str]
    acceptance_criteria: list[str]
    client_responsibilities: list[str]
    open_questions_and_risks: list[str]


class ProposalDocument(BaseModel):
    executive_summary: str
    client_problem: str
    proposed_solution: list[str]
    scope_and_deliverables: list[str]
    effort_summary: str
    timeline_note: str
    pricing_assumptions: list[str]
    client_responsibilities: list[str]
    exclusions_and_dependencies: list[str]
    risks_and_open_questions: list[str]
    approval_next_steps: list[str]


class ChangeItem(BaseModel):
    kind: Literal["added", "modified", "removed", "out_of_scope", "unresolved"]
    requirement_id: str | None = None
    description: str
    reason: str
    source_references: list[SourceReference] = Field(default_factory=list)


class ChangeReport(BaseModel):
    baseline_revision_id: str | None = None
    items: list[ChangeItem] = Field(default_factory=list)
    summary: str = "No approved baseline exists; this revision cannot be compared yet."


class ProjectCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    meeting_date: date
    transcript: str = Field(min_length=20, max_length=200000)
    consent_confirmed: bool


class MeetingCreate(BaseModel):
    meeting_date: date
    transcript: str = Field(min_length=20, max_length=200000)
    consent_confirmed: bool


class RevisionReview(BaseModel):
    reviewed_by: str = Field(min_length=1, max_length=200)
    decision: Literal["approve", "request_changes"]
    note: str = Field(default="", max_length=2000)


class ProjectRevision(BaseModel):
    revision_id: str
    project_id: str
    meeting_id: str
    revision_number: int
    status: Literal["pending_review", "approved", "changes_requested"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analysis: TranscriptAnalysis
    scope: ScopeDocument
    estimate: EstimateSummary
    proposal: ProposalDocument
    change_report: ChangeReport


class KnowledgeQueryResult(BaseModel):
    answer: str = ""
    status: Literal["answered", "insufficient_evidence", "needs_human", "unavailable"] = "unavailable"
    sources: list[dict[str, object]] = Field(default_factory=list)
    needs_human: bool = True
    escalation_id: str | None = None
    error: str | None = None