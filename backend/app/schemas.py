from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import DEFAULT_TENANT_ID


class UserRole(StrEnum):
    GENERAL_EMPLOYEE = "general_employee"
    FINANCE_OPS = "finance_ops"
    OWNER_DIRECTOR = "owner_director"
    COMPLIANCE = "compliance"


class AuthMeResponse(BaseModel):
    user_id: str
    email: str | None
    role: UserRole


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
    # Defaults to the single shared tenant until every connector has real per-tenant
    # identity (Telegram/email still authenticate as one global bot/inbox — see
    # Phase 2b of the multi-tenancy retrofit).
    tenant_id: str = DEFAULT_TENANT_ID

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
    sender_identity_token: str | None = None
    sender_identity_basis: Literal["display_name", "self_identification"] | None = None
    sender_identity_confidence: float | None = Field(default=None, ge=0, le=1)


class IngestionResult(BaseModel):
    source_record_id: str
    content_text: str
    summary: str | None
    processing_status: ProcessingStatus
    enrichment_mode: str | None
    created: bool
    refreshed: bool


class IngestionRequest(CanonicalIngestionRecord):
    """Authenticated manual-ingestion request."""

    refresh: bool = False


class IngestionResponse(IngestionResult):
    submitted_as: UserRole
    authorization_mode: str = "supabase-jwt"


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


class UploadProtectedItem(BaseModel):
    row_number: int | None = None
    source_record_id: str
    content_text: str
    processing_status: ProcessingStatus
    enrichment_mode: str | None = None


class UploadPreviewResponse(BaseModel):
    preview_digest: str
    input_kind: str
    schema_name: str | None = None
    total_rows: int = 1
    valid_rows: int = 1
    invalid_rows: int = 0
    protected_preview: list[UploadProtectedItem] = Field(default_factory=list)
    issues: list[StructuredCsvValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UploadCommitResponse(BaseModel):
    preview_digest: str
    input_kind: str
    schema_name: str | None = None
    status: str
    total_rows: int
    valid_rows: int
    failed_rows: int
    protected_rows: int
    ready_rows: int
    rows: list[UploadProtectedItem] = Field(default_factory=list)
    issues: list[StructuredCsvValidationIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)
    customer_id: int | None = Field(default=None, gt=0)
    clear_customer_context: bool = False


class QueryCitation(BaseModel):
    citation_id: str
    source_record_id: str
    source_system: str
    record_type: str | None
    occurred_at: datetime | None
    protected_excerpt: str
    similarity: float
    freshness: str = "undated"
    age_days: int | None = None
    relation: str = "supporting"


class CitedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=8_000)
    citations: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False


class IntelligenceClaim(BaseModel):
    id: str = Field(pattern=r"^claim-[1-9][0-9]*$")
    statement: str = Field(min_length=1, max_length=1_000)
    citation_ids: list[str] = Field(default_factory=list, max_length=10)
    relation: str = Field(pattern=r"^(supporting|contradicting|stale|missing)$")


class IntelligenceTimelineEvent(BaseModel):
    occurred_at: datetime | None
    label: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=1_000)
    citation_ids: list[str] = Field(default_factory=list, max_length=10)


class IntelligenceAction(BaseModel):
    id: str = "recommended-action"
    title: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=1_000)
    suggested_owner: str = Field(min_length=1, max_length=100)
    priority: SummaryPriority
    citation_ids: list[str] = Field(default_factory=list, max_length=20)


class CustomerIntelligenceBrief(BaseModel):
    subject_label: str = Field(min_length=1, max_length=120)
    status: str = Field(
        pattern=r"^(healthy|needs_attention|at_risk|insufficient_evidence)$"
    )
    executive_summary: str = Field(min_length=1, max_length=8_000)
    claims: list[IntelligenceClaim] = Field(default_factory=list, max_length=5)
    timeline: list[IntelligenceTimelineEvent] = Field(default_factory=list, max_length=5)
    open_commitments: list[IntelligenceClaim] = Field(default_factory=list, max_length=3)
    risks: list[IntelligenceClaim] = Field(default_factory=list, max_length=3)
    missing_information: list[IntelligenceClaim] = Field(default_factory=list, max_length=3)
    recommended_action: IntelligenceAction | None = None


class ExposureReceipt(BaseModel):
    request_id: str
    query_hash: str
    reasoning_mode: str
    reasoning_model: str | None
    external_ai_used: bool
    privacy_preflight_passed: bool
    recognized_sensitive_fields: int
    protected_question_tokens: int
    protected_context_tokens: int
    restored_tokens: int
    withheld_tokens: int
    active_role: UserRole
    sources_supplied: int
    disclosure_session_ref: str
    single_use_grants: int
    vault_key_version: int


class QueryResponse(BaseModel):
    answer: str
    model_answer: str
    model_question: str
    query_intent: str
    sources_used: int
    mode: str
    insufficient_evidence: bool = False
    citations: list[QueryCitation] = Field(default_factory=list)
    conversation_id: str | None = None
    turn_id: int | None = None
    protected_intelligence_brief: CustomerIntelligenceBrief | None = None
    intelligence_brief: CustomerIntelligenceBrief | None = None
    exposure_receipt: ExposureReceipt | None = None
    context_customer_id: int | None = None


class CitationDetailResponse(BaseModel):
    citation: QueryCitation
    authorized_excerpt: str
    restored_tokens: int
    withheld_tokens: int
    access_explanation: str
    query_hash: str


class RoleComparisonRequest(BaseModel):
    comparison_roles: list[UserRole] = Field(min_length=1, max_length=3)


class RoleComparisonResult(BaseModel):
    role: UserRole
    answer: str
    restored_tokens: int
    withheld_tokens: int
    policy_explanations: list[str] = Field(default_factory=list)


class RoleComparisonResponse(BaseModel):
    turn_id: int
    query_hash: str
    protected_answer: str
    results: list[RoleComparisonResult]


class ConversationCreateResponse(BaseModel):
    conversation_id: str
    status: str
    expires_at: datetime


class ConversationTurnResponse(BaseModel):
    turn_id: int
    sequence_number: int
    user_role: UserRole
    protected_question: str
    protected_answer: str
    protected_brief: CustomerIntelligenceBrief | None = None
    query_intent: str
    source_systems: list[str]
    reasoning_mode: str
    insufficient_evidence: bool
    citation_source_record_ids: list[str] = Field(default_factory=list)
    created_at: datetime


class ConversationResponse(BaseModel):
    conversation_id: str
    status: str
    expires_at: datetime
    turns: list[ConversationTurnResponse] = Field(default_factory=list)


class ConversationDeleteResponse(BaseModel):
    conversation_id: str
    status: str


class AuditEntryResponse(BaseModel):
    id: int
    role: str
    token: str
    authorized: bool
    query_hash: str
    actor_ref: str
    previous_hash: str
    entry_hash: str
    ts: datetime


class AuditResponse(BaseModel):
    entries: list[AuditEntryResponse]
    chain_valid: bool


class PrivacyTokenResponse(BaseModel):
    token: str
    entity_type: str
    masked_value: str
    decrypted_value: str | None = None
    source_record_ids: list[str]


class PrivacyEraseResponse(BaseModel):
    token: str
    erased: bool


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
    origin_type: str
    origin_turn_id: int | None
    origin_query_hash: str | None
    evidence: list[RecommendationEvidenceResponse]
    created_at: datetime
    updated_at: datetime


class RecommendationDecisionRequest(BaseModel):
    comment: str = Field(default="", max_length=2_000)


class QueryRecommendationRequest(BaseModel):
    action_id: str = Field(default="recommended-action", max_length=80)
    suggested_owner: str | None = Field(default=None, min_length=1, max_length=100)


class WorkflowAuditResponse(BaseModel):
    id: int
    event_type: str
    actor_role: str
    actor_ref: str
    resource_type: str
    resource_id: str
    event_payload: dict
    previous_hash: str
    entry_hash: str
    created_at: datetime


class WorkflowAuditListResponse(BaseModel):
    entries: list[WorkflowAuditResponse]
    chain_valid: bool


class EInvoiceRecordResponse(BaseModel):
    id: int
    supplier_name: str
    supplier_tin: str | None
    buyer_name: str | None
    buyer_customer_id: int | None = None
    invoice_no: str | None
    issue_date: date | None
    due_date: date | None = None
    currency: str | None
    tax_type: str | None
    tax_rate: str | None
    total_amount: Decimal
    status: str
    paid_at: date | None = None
    created_at: datetime
    document_available: bool = False
    readiness_reason: str = ""
    uin: str | None = None


class EinvoiceDocumentUrlResponse(BaseModel):
    url: str
    expires_in: int


class InvoiceExtraction(BaseModel):
    supplier_name: str | None = None
    supplier_tin: str | None = None
    buyer_name: str | None = None
    invoice_no: str | None = None
    issue_date: str | None = None
    currency: str | None = None
    tax_type: str | None = None
    tax_rate: str | None = None
    total_amount: str | None = None


class EInvoiceCreatePayload(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=255)
    supplier_tin: str | None = Field(default=None, max_length=64)
    supplier_email: str | None = Field(default=None, max_length=255)
    buyer_name: str | None = Field(default=None, max_length=255)
    buyer_email: str | None = Field(default=None, max_length=255)
    invoice_no: str | None = Field(default=None, max_length=64)
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = Field(default="MYR", max_length=8)
    tax_type: str | None = Field(default=None, max_length=32)
    tax_rate: str | None = Field(default=None, max_length=16)
    total_amount: Decimal = Field(gt=0)


class MarkPaidPayload(BaseModel):
    paid_at: date | None = None


class EinvoiceReadinessCategory(BaseModel):
    label: Literal["critical", "warning", "passing"]
    count: int
    records: list[EInvoiceRecordResponse]


class EinvoiceReadinessResponse(BaseModel):
    score: float
    total_records: int
    passing_count: int
    critical: EinvoiceReadinessCategory
    warning: EinvoiceReadinessCategory
    passing: EinvoiceReadinessCategory


class RequestFixPayload(BaseModel):
    channel: Literal["telegram", "email"]


class EinvoiceOutreachDraftResponse(BaseModel):
    id: int
    einvoice_record_id: int
    channel: str
    draft_text: str
    status: str
    created_at: datetime
    decided_at: datetime | None


class RevenuePeriodPoint(BaseModel):
    period_label: str
    period_start: date
    total_amount: Decimal


class ARAgingBucket(BaseModel):
    label: Literal["current", "1-30", "31-60", "61-90", "90+"]
    count: int
    total_amount: Decimal


class TopCustomer(BaseModel):
    customer_id: int
    name: str
    total_amount: Decimal
    invoice_count: int


class InvoiceStatusBreakdown(BaseModel):
    label: Literal["pending", "outstanding", "paid"]
    count: int
    total_amount: Decimal


class FinanceSummaryResponse(BaseModel):
    period: Literal["month", "quarter", "year"]
    period_start: date
    period_end: date
    total_revenue: Decimal
    prior_period_revenue: Decimal
    revenue_change_pct: float | None
    outstanding_ar: Decimal
    ar_aging: list[ARAgingBucket]
    revenue_trend: list[RevenuePeriodPoint]
    top_customers: list[TopCustomer]
    status_breakdown: list[InvoiceStatusBreakdown]
    validated_invoice_count: int
    avg_days_to_pay: float | None


class CustomerAttentionSignalResponse(BaseModel):
    signal_type: str
    points: int
    label: str
    freshness: str
    confidence: float
    tokenized_content_id: int | None = None
    einvoice_record_id: int | None = None


class CustomerSummaryResponse(BaseModel):
    id: int
    name: str
    profile_status: Literal["provisional", "confirmed"] = "confirmed"
    identity_review_status: Literal["clear", "review_required"] = "clear"
    profile_origin: Literal["manual", "einvoice", "email"] = "manual"
    attention_score: int
    priority: str
    outstanding_total: Decimal
    overdue_total: Decimal
    invoice_count: int
    linked_source_count: int


class CustomerTimelineItemResponse(BaseModel):
    event_id: str
    event_type: str
    source_system: str
    occurred_at: datetime | None
    protected_summary: str
    tokenized_content_id: int | None = None
    einvoice_record_id: int | None = None
    identity_status: str = "verified"


class CustomerDetailResponse(CustomerSummaryResponse):
    attention_version: str | None = None
    attention_signals: list[CustomerAttentionSignalResponse] = Field(default_factory=list)
    timeline: list[CustomerTimelineItemResponse] = Field(default_factory=list)


class CustomerBriefingResponse(BaseModel):
    generated_at: datetime
    customers: list[CustomerSummaryResponse]


class CustomerEndpointCreateRequest(BaseModel):
    channel: Literal["email"] = "email"
    value: str = Field(min_length=3, max_length=320)


class CustomerEndpointResponse(BaseModel):
    id: int
    customer_id: int
    channel: str
    masked_value: str
    authorized_value: str | None = None
    verification_status: str
    origin: str = "manual"
    created_at: datetime


class CustomerIdentityClaimResponse(BaseModel):
    id: int
    customer_id: int
    endpoint_id: int
    masked_value: str
    authorized_value: str | None = None
    claim_basis: Literal["display_name", "self_identification"]
    confidence: float
    status: Literal["observed", "accepted", "rejected", "conflicting"]
    occurrence_count: int
    evidence_content_id: int
    last_seen_at: datetime


class CustomerIdentityClaimDecisionRequest(BaseModel):
    decision: Literal["accept_primary", "accept_alias", "reject"]


class OutreachCreateRequest(BaseModel):
    customer_endpoint_id: int
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    evidence_content_ids: list[int] = Field(default_factory=list, max_length=20)


class OutreachGenerateRequest(BaseModel):
    customer_endpoint_id: int
    turn_id: int | None = None
    instruction: str = Field(
        default="Draft a concise, professional reply that addresses the customer's request.",
        min_length=1,
        max_length=2_000,
    )
    idempotency_key: str = Field(min_length=8, max_length=100)


class OutreachUpdateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=20_000)


class OutreachActionResponse(BaseModel):
    id: str
    customer_id: int
    customer_endpoint_id: int
    channel: str
    protected_subject: str
    protected_body: str
    recipient: str | None = None
    subject: str | None = None
    body: str | None = None
    evidence_content_ids: list[int] = Field(default_factory=list)
    generation_mode: str | None = None
    status: str
    idempotency_key: str
    attempt_count: int
    failure_code: str | None
    created_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None
    replied_at: datetime | None


class OutreachStatusResponse(BaseModel):
    id: str
    status: str
    attempt_count: int
    failure_code: str | None
    sent_at: datetime | None
    replied_at: datetime | None
