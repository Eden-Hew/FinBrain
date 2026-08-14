import json
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(UTC)


class EmbeddingType(TypeDecorator[list[float]]):
    """JSON text on SQLite and a native vector(768) on Postgres."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(768))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: list[float] | str | None, dialect: Dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return json.loads(value) if isinstance(value, str) else value
        return value if isinstance(value, str) else json.dumps(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return [float(item) for item in value]
        return [float(item) for item in json.loads(value)]


class RoleListType(TypeDecorator[list[str]]):
    """SQLite JSON locally and indexable JSONB on Postgres."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class ObjectType(TypeDecorator[dict[str, Any]]):
    """SQLite JSON locally and JSONB for queryable protected metadata on Postgres."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB(none_as_null=True))
        return dialect.type_descriptor(JSON(none_as_null=True))


class Base(DeclarativeBase):
    pass


class TokenizedContent(Base):
    """Sanitized content only; raw inbound text is never persisted."""

    __tablename__ = "tokenized_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(EmbeddingType())
    record_type: Mapped[str | None] = mapped_column(String)
    summary: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(String, default="legacy", nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_fingerprint: Mapped[str | None] = mapped_column(String)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(
        ObjectType(), default=dict, nullable=False
    )
    structured_summary: Mapped[dict[str, Any] | None] = mapped_column(ObjectType())
    processing_status: Mapped[str] = mapped_column(String, default="protected", nullable=False)
    processing_error: Mapped[str | None] = mapped_column(String)
    enrichment_mode: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TokenVaultEntry(Base):
    """Encrypted sensitive values keyed by deterministic tenant-scoped tokens."""

    __tablename__ = "token_vault"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    allowed_roles: Mapped[list[str]] = mapped_column(RoleListType(), nullable=False)
    sensitivity: Mapped[str] = mapped_column(String, default="high")
    source_record_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    event_hash: Mapped[str] = mapped_column(String, nullable=False)
    user_role: Mapped[str] = mapped_column(String, nullable=False)
    token: Mapped[str] = mapped_column(String, nullable=False)
    authorized: Mapped[bool] = mapped_column(Boolean, nullable=False)
    query_hash: Mapped[str] = mapped_column(String, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TelegramUpdateReceipt(Base):
    """Privacy-safe idempotency receipt; raw Telegram payloads are never stored."""

    __tablename__ = "telegram_update_receipts"

    update_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_ref_hash: Mapped[str | None] = mapped_column(String, unique=True)
    actor_ref: Mapped[str] = mapped_column(String, nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String)
    update_kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="received")
    failure_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IntegrationStatus(Base):
    """Operational heartbeat containing no credentials or external identities."""

    __tablename__ = "integration_status"

    integration_key: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    detector_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String)


class EmailSyncState(Base):
    """Incremental IMAP cursor containing no mailbox address or credentials."""

    __tablename__ = "email_sync_state"

    connector_key: Mapped[str] = mapped_column(String, primary_key=True)
    mailbox_ref: Mapped[str] = mapped_column(String, nullable=False)
    folder_name: Mapped[str] = mapped_column(String, nullable=False)
    last_uid: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="idle", nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmailIngestionReceipt(Base):
    """HMAC-addressed email delivery receipt; raw headers are never persisted."""

    __tablename__ = "email_ingestion_receipts"

    message_ref_hash: Mapped[str] = mapped_column(String, primary_key=True)
    source_record_id: Mapped[str | None] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="received", nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StructuredIngestionBatch(Base):
    """Opaque structured-file status; source bytes and filenames are never stored."""

    __tablename__ = "structured_ingestion_batches"

    batch_ref: Mapped[str] = mapped_column(String, primary_key=True)
    schema_name: Mapped[str] = mapped_column(String, nullable=False)
    origin_channel: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    protected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    ready_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProcessRecommendation(Base):
    __tablename__ = "process_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_owner: Mapped[str] = mapped_column(String, nullable=False)
    success_metric: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, default="proposed", nullable=False)
    analysis_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analysis_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_systems: Mapped[list[str]] = mapped_column(RoleListType(), nullable=False)
    enrichment_mode: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RecommendationEvidence(Base):
    __tablename__ = "recommendation_evidence"
    __table_args__ = (
        UniqueConstraint(
            "recommendation_id",
            "tokenized_content_id",
            name="recommendation_evidence_record_unique",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("process_recommendations.id", ondelete="CASCADE"), nullable=False
    )
    tokenized_content_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tokenized_content.id", ondelete="RESTRICT"), nullable=False
    )
    evidence_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecommendationDecision(Base):
    __tablename__ = "recommendation_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("process_recommendations.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    actor_ref: Mapped[str] = mapped_column(String, nullable=False)
    protected_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowAuditEntry(Base):
    __tablename__ = "workflow_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    event_hash: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_role: Mapped[str] = mapped_column(String, nullable=False)
    actor_ref: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(ObjectType(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
