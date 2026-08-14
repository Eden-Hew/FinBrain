from sqlalchemy.orm import Session

from app.integrations.structured_csv.adapter import adapt_invoice_row, batch_reference
from app.integrations.structured_csv.parser import parse_invoice_csv
from app.integrations.structured_csv.schemas import (
    SCHEMA_NAME,
    StructuredCsvBatchResult,
    StructuredCsvRowResult,
)
from app.models import StructuredIngestionBatch
from app.schemas import ProcessingStatus
from app.services.ingestion import enrich_protected_record, protect_canonical_record


def _persist_batch(db: Session, batch: StructuredIngestionBatch) -> None:
    db.add(batch)
    db.commit()


def ingest_structured_csv(
    db: Session,
    data: bytes,
    *,
    refresh: bool = False,
    origin_channel: str = "web_upload",
) -> StructuredCsvBatchResult:
    """Validate, protect every accepted row, then enrich protected rows only."""
    parsed = parse_invoice_csv(data)
    batch_ref = batch_reference(data)
    invalid_rows = max(parsed.total_rows - len(parsed.rows), 0)
    batch = db.get(StructuredIngestionBatch, batch_ref)
    if batch is None:
        batch = StructuredIngestionBatch(
            batch_ref=batch_ref,
            schema_name=SCHEMA_NAME,
            origin_channel=origin_channel,
            status="validated",
            total_rows=parsed.total_rows,
            valid_rows=len(parsed.rows),
            failed_rows=invalid_rows,
            protected_rows=0,
            ready_rows=0,
        )
    else:
        batch.schema_name = SCHEMA_NAME
        batch.origin_channel = origin_channel
        batch.total_rows = parsed.total_rows
        batch.valid_rows = len(parsed.rows)
        batch.failed_rows = invalid_rows
        batch.protected_rows = 0
        batch.ready_rows = 0
        batch.failure_code = None

    if not parsed.rows:
        batch.status = "failed"
        batch.failure_code = parsed.issues[0].code if parsed.issues else "no_valid_rows"
        _persist_batch(db, batch)
        return StructuredCsvBatchResult(
            batch_ref=batch_ref,
            schema_name=SCHEMA_NAME,
            status=batch.status,
            total_rows=parsed.total_rows,
            valid_rows=0,
            failed_rows=invalid_rows,
            protected_rows=0,
            ready_rows=0,
            issues=parsed.issues,
        )

    batch.status = "protecting"
    _persist_batch(db, batch)
    protected_results: list[StructuredCsvRowResult] = []
    protection_failures = 0
    for parsed_row in parsed.rows:
        record = adapt_invoice_row(parsed_row, batch_ref=batch_ref, origin_channel=origin_channel)
        try:
            result = protect_canonical_record(db, record, refresh=refresh)
        except Exception:
            db.rollback()
            protection_failures += 1
            continue
        protected_results.append(
            StructuredCsvRowResult(
                row_number=parsed_row.row_number,
                source_record_id=record.source_record_id,
                ingestion=result,
            )
        )

    batch = db.get(StructuredIngestionBatch, batch_ref)
    if batch is None:
        raise RuntimeError("Structured ingestion batch disappeared")
    batch.protected_rows = len(protected_results)
    batch.failed_rows = invalid_rows + protection_failures
    batch.status = "enriching" if protected_results else "failed"
    batch.failure_code = "row_protection_failed" if protection_failures else None
    _persist_batch(db, batch)

    final_results: list[StructuredCsvRowResult] = []
    ready_rows = 0
    enrichment_failures = 0
    for protected in protected_results:
        result = protected.ingestion
        if result.processing_status is not ProcessingStatus.READY:
            result = enrich_protected_record(
                db,
                protected.source_record_id,
                created=result.created,
                refreshed=result.refreshed,
            )
        if result.processing_status is ProcessingStatus.READY:
            ready_rows += 1
        else:
            enrichment_failures += 1
        final_results.append(
            StructuredCsvRowResult(
                row_number=protected.row_number,
                source_record_id=protected.source_record_id,
                ingestion=result,
            )
        )

    batch = db.get(StructuredIngestionBatch, batch_ref)
    if batch is None:
        raise RuntimeError("Structured ingestion batch disappeared")
    batch.ready_rows = ready_rows
    batch.failed_rows = invalid_rows + protection_failures + enrichment_failures
    if ready_rows == parsed.total_rows:
        batch.status = "ready"
        batch.failure_code = None
    elif ready_rows:
        batch.status = "partial"
        batch.failure_code = "some_rows_failed"
    else:
        batch.status = "failed"
        batch.failure_code = "enrichment_failed" if protected_results else "row_protection_failed"
    _persist_batch(db, batch)

    return StructuredCsvBatchResult(
        batch_ref=batch_ref,
        schema_name=SCHEMA_NAME,
        status=batch.status,
        total_rows=batch.total_rows,
        valid_rows=batch.valid_rows,
        failed_rows=batch.failed_rows,
        protected_rows=batch.protected_rows,
        ready_rows=batch.ready_rows,
        rows=final_results,
        issues=parsed.issues,
    )
