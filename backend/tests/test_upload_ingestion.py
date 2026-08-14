from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, StructuredIngestionBatch, TokenizedContent
from app.schemas import ProtectedSummary, SummaryPriority
from app.services import ingestion
from app.services.upload_ingestion import commit_upload, preview_upload, upload_digest

CSV = (
    b"invoice_id,customer,amount,status,assigned_owner,due_date\n"
    b'INV-1024,nur.aisyah@example.com,"RM 4,500",pending approval,,2026-08-20\n'
)


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _mock_enrichment(monkeypatch) -> None:
    monkeypatch.setattr(
        ingestion,
        "summarize_protected_text",
        lambda _text: (
            ProtectedSummary(
                summary="Protected upload accepted.",
                category="uploaded_document",
                action_required=False,
                priority=SummaryPriority.LOW,
            ),
            "test",
        ),
    )
    monkeypatch.setattr(ingestion, "embed_text", lambda _text: ([1.0], "test"))


def test_structured_preview_is_protected_and_has_no_database_side_effect():
    engine, db = _database()
    try:
        preview = preview_upload(
            CSV,
            filename="customer-register.csv",
            mime_type="text/csv",
            record_type="invoice_register",
        )
        assert preview.schema_name == "invoice_register_v1"
        assert preview.valid_rows == 1
        assert "nur.aisyah@example.com" not in preview.protected_preview[0].content_text
        assert "RM 4,500" not in preview.protected_preview[0].content_text
        assert "EMAIL_" in preview.protected_preview[0].content_text
        assert "AMOUNT_BAND_3_" in preview.protected_preview[0].content_text
        assert db.scalar(select(TokenizedContent)) is None
        assert db.scalar(select(StructuredIngestionBatch)) is None
    finally:
        db.close()
        engine.dispose()


def test_commit_rejects_changed_file_with_old_digest():
    engine, db = _database()
    try:
        try:
            commit_upload(
                db,
                CSV + b"\n",
                filename="invoices.csv",
                mime_type="text/csv",
                record_type="invoice_register",
                expected_digest=upload_digest(CSV),
            )
        except ValueError as error:
            assert str(error) == "preview_digest_mismatch"
        else:
            raise AssertionError("Modified upload was committed with a stale digest")
        assert db.scalar(select(TokenizedContent)) is None
    finally:
        db.close()
        engine.dispose()


def test_structured_commit_persists_rows_and_generic_upload_uses_canonical_service(
    monkeypatch,
):
    engine, db = _database()
    _mock_enrichment(monkeypatch)
    document = b"Call 012-345 6789 about the delayed approval."
    try:
        csv_result = commit_upload(
            db,
            CSV,
            filename="invoices.csv",
            mime_type="text/csv",
            record_type="invoice_register",
            expected_digest=upload_digest(CSV),
        )
        document_result = commit_upload(
            db,
            document,
            filename="notes.txt",
            mime_type="text/plain",
            record_type="meeting_notes",
            expected_digest=upload_digest(document),
        )
        records = db.scalars(select(TokenizedContent).order_by(TokenizedContent.id)).all()

        assert csv_result.status == "ready"
        assert document_result.status == "ready"
        assert len(records) == 2
        assert records[1].source_system == "document_upload"
        assert records[1].record_type == "meeting_notes"
        assert "012-345 6789" not in records[1].content_text
        assert "notes.txt" not in repr(records[1].safe_metadata)
    finally:
        db.close()
        engine.dispose()


def test_generic_preview_rejects_unsupported_and_exposes_only_safe_codes():
    try:
        preview_upload(
            b"binary",
            filename="archive.exe",
            mime_type="application/octet-stream",
            record_type="uploaded_document",
        )
    except ValueError as error:
        assert str(error) == "unsupported_file_type"
        assert "archive.exe" not in str(error)
    else:
        raise AssertionError("Unsupported upload was previewed")
