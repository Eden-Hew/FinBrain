import hashlib
import hmac
from dataclasses import asdict
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.structured_csv.adapter import adapt_invoice_row
from app.integrations.structured_csv.parser import parse_invoice_csv
from app.integrations.structured_csv.schemas import SCHEMA_NAME
from app.integrations.structured_csv.service import ingest_structured_csv
from app.integrations.telegram.extractors import ExtractionError, extract_document
from app.schemas import (
    CanonicalIngestionRecord,
    ProcessingStatus,
    StructuredCsvValidationIssue,
    UploadCommitResponse,
    UploadPreviewResponse,
    UploadProtectedItem,
)
from app.services.ingestion import ingest_canonical_record, preview_canonical_record


def upload_digest(data: bytes) -> str:
    return hmac.new(
        get_settings().token_root_secret.encode(),
        b"web-upload-preview\x00" + data,
        hashlib.sha256,
    ).hexdigest()


def _safe_suffix(filename: str) -> str:
    if not filename or len(filename) > 255 or any(character in filename for character in "\r\n"):
        raise ExtractionError("invalid_filename")
    return PurePosixPath(filename.replace("\\", "/")).suffix.casefold()


def _document_record(
    data: bytes, *, filename: str, mime_type: str, record_type: str
) -> tuple[CanonicalIngestionRecord, str]:
    extracted = extract_document(data, filename=filename, mime_type=mime_type)
    digest = upload_digest(data)
    record = CanonicalIngestionRecord(
        source_record_id=f"document_upload:{digest[:24]}",
        source_system="document_upload",
        record_type=record_type,
        text=extracted.text,
        metadata={
            "input_kind": extracted.input_kind,
            "mime_type": extracted.mime_type,
            **({"page_count": str(extracted.page_count)} if extracted.page_count else {}),
            "origin_channel": "web_upload",
        },
    )
    return record, extracted.input_kind


def preview_upload(
    data: bytes, *, filename: str, mime_type: str, record_type: str
) -> UploadPreviewResponse:
    digest = upload_digest(data)
    if _safe_suffix(filename) == ".csv":
        parsed = parse_invoice_csv(data)
        if not parsed.rows:
            issue_code = parsed.issues[0].code if parsed.issues else "unsupported_csv_schema"
            if issue_code in {
                "unsupported_header",
                "duplicate_header",
                "missing_required_header",
            }:
                raise ExtractionError("unsupported_csv_schema")
        items: list[UploadProtectedItem] = []
        for row in parsed.rows[:10]:
            record = adapt_invoice_row(row, batch_ref=digest)
            items.append(
                UploadProtectedItem(
                    row_number=row.row_number,
                    source_record_id=record.source_record_id,
                    content_text=preview_canonical_record(record)[:1200],
                    processing_status=ProcessingStatus.PROTECTED,
                )
            )
        return UploadPreviewResponse(
            preview_digest=digest,
            input_kind="structured_csv",
            schema_name=SCHEMA_NAME,
            total_rows=parsed.total_rows,
            valid_rows=len(parsed.rows),
            invalid_rows=max(parsed.total_rows - len(parsed.rows), 0),
            protected_preview=items,
            issues=[StructuredCsvValidationIssue(**asdict(issue)) for issue in parsed.issues],
            warnings=["preview_limited_to_10_rows"] if len(parsed.rows) > 10 else [],
        )

    record, input_kind = _document_record(
        data, filename=filename, mime_type=mime_type, record_type=record_type
    )
    return UploadPreviewResponse(
        preview_digest=digest,
        input_kind=input_kind,
        protected_preview=[
            UploadProtectedItem(
                source_record_id=record.source_record_id,
                content_text=preview_canonical_record(record)[:1200],
                processing_status=ProcessingStatus.PROTECTED,
            )
        ],
        warnings=["preview_truncated"] if len(record.text) > 1200 else [],
    )


def commit_upload(
    db: Session,
    data: bytes,
    *,
    filename: str,
    mime_type: str,
    record_type: str,
    expected_digest: str,
) -> UploadCommitResponse:
    digest = upload_digest(data)
    if not hmac.compare_digest(digest, expected_digest):
        raise ValueError("preview_digest_mismatch")
    if _safe_suffix(filename) == ".csv":
        result = ingest_structured_csv(db, data)
        return UploadCommitResponse(
            preview_digest=digest,
            input_kind="structured_csv",
            schema_name=result.schema_name,
            status=result.status,
            total_rows=result.total_rows,
            valid_rows=result.valid_rows,
            failed_rows=result.failed_rows,
            protected_rows=result.protected_rows,
            ready_rows=result.ready_rows,
            rows=[
                UploadProtectedItem(
                    row_number=row.row_number,
                    source_record_id=row.source_record_id,
                    content_text=row.ingestion.content_text,
                    processing_status=row.ingestion.processing_status,
                    enrichment_mode=row.ingestion.enrichment_mode,
                )
                for row in result.rows
            ],
            issues=[StructuredCsvValidationIssue(**asdict(issue)) for issue in result.issues],
        )

    record, input_kind = _document_record(
        data, filename=filename, mime_type=mime_type, record_type=record_type
    )
    result = ingest_canonical_record(db, record)
    ready = result.processing_status is ProcessingStatus.READY
    return UploadCommitResponse(
        preview_digest=digest,
        input_kind=input_kind,
        status="ready" if ready else "failed",
        total_rows=1,
        valid_rows=1,
        failed_rows=0 if ready else 1,
        protected_rows=1,
        ready_rows=1 if ready else 0,
        rows=[
            UploadProtectedItem(
                source_record_id=result.source_record_id,
                content_text=result.content_text,
                processing_status=result.processing_status,
                enrichment_mode=result.enrichment_mode,
            )
        ],
    )
