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


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    role: UserRole


class QueryResponse(BaseModel):
    answer: str
    model_answer: str
    model_question: str
    sources_used: int
    mode: str


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
