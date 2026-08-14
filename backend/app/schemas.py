from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class UserRole(StrEnum):
    GENERAL_EMPLOYEE = "general_employee"
    FINANCE_OPS = "finance_ops"
    OWNER_DIRECTOR = "owner_director"
    COMPLIANCE = "compliance"


class ProcessingStatus(StrEnum):
    PROTECTED = "protected"
    READY = "ready"
    FAILED_ENRICHMENT = "failed_enrichment"


class SummaryPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CanonicalIngestionRecord(BaseModel):
    """Source-neutral record accepted by the protected ingestion boundary."""

    source_record_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9:_.-]+$")
    source_system: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    record_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_.-]+$")
    text: str = Field(min_length=1, max_length=200_000)
    occurred_at: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, metadata: dict[str, str]) -> dict[str, str]:
        if len(metadata) > 50:
            raise ValueError("metadata cannot contain more than 50 fields")
        for key, value in metadata.items():
            if (
                not key
                or len(key) > 64
                or not key[0].islower()
                or not all(
                    character.islower() or character.isdigit() or character in "_.-"
                    for character in key
                )
            ):
                raise ValueError("metadata keys must be short identifier-like strings")
            if len(value) > 4_000:
                raise ValueError("metadata values cannot exceed 4000 characters")
        return metadata


class ProtectedSummary(BaseModel):
    summary: str = Field(min_length=1, max_length=2_000)
    category: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    action_required: bool
    priority: SummaryPriority


class IngestionResult(BaseModel):
    source_record_id: str
    content_text: str
    summary: str | None
    processing_status: ProcessingStatus
    enrichment_mode: str | None
    created: bool
    refreshed: bool


class IngestionRequest(CanonicalIngestionRecord):
    """Demo request contract; role is caller-selected until authentication is implemented."""

    role: UserRole
    refresh: bool = False


class IngestionResponse(IngestionResult):
    submitted_as: UserRole
    authorization_mode: str = "demo-role"


class StructuredCsvValidationIssue(BaseModel):
    code: str
    row_number: int | None = None
    field: str | None = None


class StructuredCsvRowResult(BaseModel):
    row_number: int
    source_record_id: str
    content_text: str
    processing_status: ProcessingStatus
    enrichment_mode: str | None = None
    created: bool
    refreshed: bool


class StructuredCsvPreviewResponse(BaseModel):
    preview_digest: str
    schema_name: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    protected_preview: list[StructuredCsvRowResult] = Field(default_factory=list)
    issues: list[StructuredCsvValidationIssue] = Field(default_factory=list)


class StructuredCsvCommitResponse(BaseModel):
    batch_ref: str
    schema_name: str
    status: str
    total_rows: int
    valid_rows: int
    failed_rows: int
    protected_rows: int
    ready_rows: int
    rows: list[StructuredCsvRowResult] = Field(default_factory=list)
    issues: list[StructuredCsvValidationIssue] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    role: UserRole


class QueryCitation(BaseModel):
    citation_id: str
    source_record_id: str
    source_system: str
    record_type: str | None
    occurred_at: datetime | None
    protected_excerpt: str
    similarity: float


class CitedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    citations: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class QueryResponse(BaseModel):
    answer: str
    model_answer: str
    model_question: str
    sources_used: int
    mode: str
    insufficient_evidence: bool = False
    citations: list[QueryCitation] = Field(default_factory=list)


class AuditEntryResponse(BaseModel):
    id: int
    role: str
    token: str
    authorized: bool
    query_hash: str
    ts: datetime


class AuditResponse(BaseModel):
    entries: list[AuditEntryResponse]
    chain_valid: bool


class TelegramIntegrationStatusResponse(BaseModel):
    configured: bool
    mode: str
    status: str
    detector_ready: bool
    last_heartbeat_at: datetime | None
    last_update_at: datetime | None


class ProtectedIngestionRecordResponse(BaseModel):
    source_record_id: str
    source_system: str
    record_type: str | None
    content_excerpt: str
    summary: str | None
    structured_summary: dict | None
    processing_status: ProcessingStatus
    enrichment_mode: str | None
    occurred_at: datetime | None
    created_at: datetime
    updated_at: datetime
    safe_metadata: dict


class EmailIntegrationStatusResponse(BaseModel):
    configured: bool
    status: str
    folder_name: str
    last_uid: int
    last_sync_at: datetime | None
    failure_code: str | None


class EmailSyncResponse(BaseModel):
    examined: int
    protected: int
    ready: int
    failed: int
    last_uid: int


class ProcessAnalysisRequest(BaseModel):
    window_days: int = Field(default=30, ge=1, le=365)
    source_systems: list[str] = Field(default_factory=lambda: ["telegram", "email"])
    minimum_evidence: int = Field(default=3, ge=2, le=20)
    role: UserRole

    @field_validator("source_systems")
    @classmethod
    def validate_source_systems(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(values))
        if not cleaned or len(cleaned) > 10:
            raise ValueError("source_systems must contain between 1 and 10 values")
        if any(
            not value
            or len(value) > 64
            or not all(
                character.islower() or character.isdigit() or character in "_.-"
                for character in value
            )
            for value in cleaned
        ):
            raise ValueError("source_systems must contain identifier-like values")
        return cleaned


class RecommendationDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    problem_statement: str = Field(min_length=1, max_length=2_000)
    recommendation: str = Field(min_length=1, max_length=2_000)
    expected_benefit: str = Field(min_length=1, max_length=1_000)
    suggested_owner: str = Field(min_length=1, max_length=100)
    success_metric: str = Field(min_length=1, max_length=1_000)
    category: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_]+$")
    priority: SummaryPriority
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=2, max_length=20)


class RecommendationEvidenceResponse(BaseModel):
    citation_id: str
    source_record_id: str
    source_system: str
    record_type: str | None
    occurred_at: datetime | None
    evidence_excerpt: str
    relevance_reason: str


class RecommendationResponse(BaseModel):
    id: int
    title: str
    problem_statement: str
    recommendation: str
    expected_benefit: str
    suggested_owner: str
    success_metric: str
    category: str
    priority: SummaryPriority
    confidence: float
    status: str
    analysis_window_start: datetime
    analysis_window_end: datetime
    record_count: int
    source_systems: list[str]
    enrichment_mode: str
    evidence: list[RecommendationEvidenceResponse]
    created_at: datetime
    updated_at: datetime


class RecommendationDecisionRequest(BaseModel):
    role: UserRole
    comment: str = Field(default="", max_length=2_000)


class WorkflowAuditResponse(BaseModel):
    id: int
    event_type: str
    actor_role: str
    actor_ref: str
    resource_type: str
    resource_id: str
    event_payload: dict
    created_at: datetime


class WorkflowAuditListResponse(BaseModel):
    entries: list[WorkflowAuditResponse]
    chain_valid: bool
