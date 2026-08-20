import hashlib
import hmac
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TokenizedContent
from app.schemas import CanonicalIngestionRecord, IngestionResult, ProcessingStatus
from app.security.detect import contains_known_pii, detect_spans
from app.security.protection import protect_metadata, protect_text
from app.security.tokenize import persist_vault_entries, tokenize_record
from app.services.embeddings import embed_text
from app.services.summarization import summarize_protected_text

logger = logging.getLogger(__name__)


def _protect_text(
    text: str, source_record_id: str, tenant_id: str, db: Session | None = None
):
    """Compatibility seam for tests and connector-specific detector injection."""
    return protect_text(
        text,
        source_record_id,
        tenant_id,
        db,
        spans=detect_spans(text),
        tokenizer=tokenize_record,
    )


def preview_canonical_record(record: CanonicalIngestionRecord) -> str:
    """Return protected text without persistence or external model calls."""
    if contains_known_pii(record.source_record_id):
        raise ValueError("source_record_id must be an opaque identifier without recognizable PII")
    protected_text, _entries = _protect_text(
        record.text, record.source_record_id, record.tenant_id
    )
    protect_metadata(record.metadata, record.source_record_id, record.tenant_id)
    return protected_text


def _content_fingerprint(record: CanonicalIngestionRecord) -> str:
    """Return a non-reversible keyed fingerprint for idempotency checks."""
    payload = json.dumps(
        {
            "metadata": record.metadata,
            "occurred_at": record.occurred_at.isoformat() if record.occurred_at else None,
            "record_type": record.record_type,
            "source_system": record.source_system,
            "text": record.text,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(
        get_settings().token_identity_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def _result(
    row: TokenizedContent,
    *,
    created: bool,
    refreshed: bool,
) -> IngestionResult:
    return IngestionResult(
        source_record_id=row.source_record_id,
        content_text=row.content_text,
        summary=row.summary,
        processing_status=ProcessingStatus(row.processing_status),
        enrichment_mode=row.enrichment_mode,
        created=created,
        refreshed=refreshed,
    )


def ingest_canonical_record(
    db: Session,
    record: CanonicalIngestionRecord,
    *,
    refresh: bool = False,
    enrich: bool = True,
) -> IngestionResult:
    """Compatibility wrapper around protected persistence and optional enrichment."""
    result = protect_canonical_record(db, record, refresh=refresh)
    if not enrich or (
        not result.created
        and not result.refreshed
        and result.processing_status == ProcessingStatus.READY
    ):
        return result
    return enrich_protected_record(
        db,
        result.source_record_id,
        created=result.created,
        refreshed=result.refreshed,
    )


def protect_canonical_record(
    db: Session,
    record: CanonicalIngestionRecord,
    *,
    refresh: bool = False,
) -> IngestionResult:
    """Protect and commit source content without making any external model call."""
    if contains_known_pii(record.source_record_id):
        raise ValueError("source_record_id must be an opaque identifier without recognizable PII")
    fingerprint = _content_fingerprint(record)
    existing = db.scalar(
        select(TokenizedContent).where(TokenizedContent.source_record_id == record.source_record_id)
    )
    if (
        existing
        and not refresh
        and existing.processing_status == ProcessingStatus.READY
        and existing.content_fingerprint in {None, fingerprint}
    ):
        return _result(existing, created=False, refreshed=False)

    protected_text, content_entries = _protect_text(
        record.text, record.source_record_id, record.tenant_id, db
    )
    protected_metadata, metadata_entries = protect_metadata(
        record.metadata, record.source_record_id, record.tenant_id, db
    )
    entries = {entry.token: entry for entry in content_entries + metadata_entries}
    persist_vault_entries(db, list(entries.values()))

    created = existing is None
    row = existing or TokenizedContent(
        source_record_id=record.source_record_id,
        tenant_id=record.tenant_id,
        content_text=protected_text,
    )
    row.content_text = protected_text
    row.embedding = None
    row.record_type = record.record_type
    row.summary = None
    row.source_system = record.source_system
    row.occurred_at = record.occurred_at
    row.content_fingerprint = fingerprint
    row.safe_metadata = protected_metadata
    row.structured_summary = None
    row.processing_status = ProcessingStatus.PROTECTED
    row.processing_error = None
    row.enrichment_mode = None
    if created:
        db.add(row)
    db.commit()

    if get_settings().customer_intelligence_enabled:
        try:
            from app.services.entity_resolution import link_record_from_known_aliases

            link_record_from_known_aliases(db, row)
        except Exception:
            db.rollback()
            logger.exception(
                "customer_identity_link_failed",
                extra={"source_record_id": row.source_record_id},
            )

    return _result(row, created=created, refreshed=not created)


def enrich_protected_record(
    db: Session,
    source_record_id: str,
    *,
    created: bool = False,
    refreshed: bool = False,
) -> IngestionResult:
    """Enrich an already-protected record; raw source content is never available here."""
    row = db.scalar(
        select(TokenizedContent).where(TokenizedContent.source_record_id == source_record_id)
    )
    if row is None:
        raise ValueError("Protected record not found")
    protected_text = row.content_text
    if contains_known_pii(protected_text):
        raise ValueError("Refusing to enrich a record containing recognized PII")

    stage = "summarization"
    try:
        summary, summary_mode = summarize_protected_text(protected_text)
        stage = "embedding"
        embedding, embedding_mode = embed_text(
            f"{protected_text}\n\nProtected summary:\n{summary.summary}"
        )
        row.summary = summary.summary
        row.structured_summary = summary.model_dump(mode="json")
        row.embedding = embedding
        row.processing_status = ProcessingStatus.READY
        row.processing_error = None
        row.enrichment_mode = (
            summary_mode
            if summary_mode == embedding_mode
            else f"summary:{summary_mode},embedding:{embedding_mode}"
        )
        db.commit()
    except Exception:
        db.rollback()
        row = db.scalar(
            select(TokenizedContent).where(
                TokenizedContent.source_record_id == source_record_id
            )
        )
        if row is None:
            raise RuntimeError("Protected record disappeared during enrichment") from None
        row.processing_status = ProcessingStatus.FAILED_ENRICHMENT
        row.processing_error = f"{stage}_failed"
        row.enrichment_mode = None
        db.commit()

    return _result(row, created=created, refreshed=refreshed)


def retry_pending_enrichment(db: Session, *, limit: int = 20) -> list[IngestionResult]:
    """Retry a bounded set of records using only their protected persisted content."""
    rows = db.scalars(
        select(TokenizedContent)
        .where(
            TokenizedContent.processing_status.in_(
                [ProcessingStatus.PROTECTED, ProcessingStatus.FAILED_ENRICHMENT]
            )
        )
        .order_by(TokenizedContent.updated_at)
        .limit(limit)
    ).all()
    return [enrich_protected_record(db, row.source_record_id) for row in rows]


def ingest_record(
    db: Session,
    source_id: str,
    source_type: str,
    raw_text: str,
    *,
    refresh: bool = False,
) -> str:
    """Compatibility wrapper; adapters should use ``ingest_canonical_record`` directly."""
    result = ingest_canonical_record(
        db,
        CanonicalIngestionRecord(
            source_record_id=source_id,
            source_system=source_type,
            record_type=source_type,
            text=raw_text,
        ),
        refresh=refresh,
    )
    return result.content_text
