from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.integrations.structured_csv import service
from app.integrations.structured_csv.adapter import (
    adapt_invoice_row,
    batch_reference,
    row_reference,
)
from app.integrations.structured_csv.parser import parse_invoice_csv
from app.integrations.structured_csv.schemas import ParsedInvoiceRow
from app.models import Base, StructuredIngestionBatch, TokenizedContent, TokenVaultEntry
from app.schemas import IngestionResult, ProcessingStatus, ProtectedSummary, SummaryPriority
from app.services import ingestion

HEADER = "invoice_id,customer,amount,status,assigned_owner,due_date\n"
VALID_ROW = 'INV-1024,nur.aisyah@example.com,"RM 4,500",pending approval,,2026-08-20\n'


def _settings(**updates) -> Settings:
    return Settings(_env_file=None, **updates)


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
                summary="Protected invoice accepted.",
                category="invoice",
                action_required=True,
                priority=SummaryPriority.MEDIUM,
            ),
            "test",
        ),
    )
    monkeypatch.setattr(ingestion, "embed_text", lambda _text: ([1.0, 0.0], "test"))


def test_parser_accepts_utf8_bom_windows_1252_and_header_aliases():
    bom = parse_invoice_csv((HEADER + VALID_ROW).encode("utf-8-sig"))
    windows = parse_invoice_csv(
        (
            "invoice,customer_name,amount_myr,status,owner,due\n"
            "INV-2,Jos\u00e9 Trading,380.25,refund requested,Ana,2026-08-21\n"
        ).encode("windows-1252")
    )

    assert len(bom.rows) == 1
    assert bom.rows[0].amount == Decimal("4500")
    assert len(windows.rows) == 1
    assert windows.rows[0].customer == "Jos\u00e9 Trading"
    assert windows.rows[0].status == "refund_requested"


def test_parser_reports_safe_header_and_row_validation_codes():
    duplicate_header = parse_invoice_csv(
        b"invoice_id,invoice,customer,amount,status,due_date\n"
    )
    missing_header = parse_invoice_csv(b"invoice_id,customer,amount,status,due_date\n")
    invalid_rows = parse_invoice_csv(
        (
            HEADER
            + "INV-1,Customer,not-money,pending approval,,not-a-date\n"
            + "INV-1,Customer,25,paid,,2026-08-20\n"
        ).encode()
    )

    assert [item.code for item in duplicate_header.issues] == ["duplicate_header"]
    assert [item.code for item in missing_header.issues] == ["missing_required_header"]
    assert {item.code for item in invalid_rows.issues} == {
        "invalid_amount",
        "invalid_due_date",
    }
    assert all("Customer" not in repr(item) for item in invalid_rows.issues)


def test_parser_rejects_duplicate_invoice_and_bounded_inputs():
    duplicate = parse_invoice_csv(
        (HEADER + VALID_ROW + VALID_ROW.replace("4,500", "4,600")).encode()
    )
    assert [item.code for item in duplicate.issues] == ["duplicate_invoice_id"]

    too_large = parse_invoice_csv(
        b"x" * 11, settings=_settings(structured_csv_max_file_bytes=10)
    )
    assert too_large.issues[0].code == "file_too_large"
    assert parse_invoice_csv(
        (HEADER + VALID_ROW + VALID_ROW).encode(),
        settings=_settings(structured_csv_max_rows=1),
    ).issues[0].code == "too_many_rows"
    assert parse_invoice_csv(
        (HEADER + VALID_ROW).encode(), settings=_settings(structured_csv_max_columns=2)
    ).issues[0].code == "too_many_columns"
    assert parse_invoice_csv(
        (HEADER + VALID_ROW).encode(), settings=_settings(structured_csv_max_cell_chars=5)
    ).issues[0].code == "cell_too_long"
    assert parse_invoice_csv((HEADER + "\x00").encode()).issues[0].code == "nul_byte"


def test_hmac_references_are_stable_and_row_identity_ignores_position():
    data = (HEADER + VALID_ROW).encode()
    assert batch_reference(data) == batch_reference(data)
    assert batch_reference(data) != batch_reference(data + b"\n")
    assert row_reference(" INV-1024 ") == row_reference("inv-1024")
    assert row_reference("INV-1024") != row_reference("INV-1025")


def test_adapter_uses_only_safe_derived_metadata():
    row = ParsedInvoiceRow(
        row_number=2,
        invoice_id="INV-1024",
        customer="Ahmad Rahman",
        amount=Decimal("4500"),
        status="pending_approval",
        assigned_owner="",
        due_date=__import__("datetime").date(2026, 8, 20),
    )
    record = adapt_invoice_row(row, batch_ref="a" * 64)

    assert record.source_system == "spreadsheet"
    assert record.record_type == "invoice_row"
    assert record.metadata["amount_band"] == "3"
    assert record.metadata["has_assigned_owner"] == "false"
    assert "Ahmad Rahman" not in record.metadata.values()
    assert "4500" not in record.metadata.values()


def test_service_protects_all_rows_before_any_enrichment(monkeypatch):
    engine, db = _database()
    events: list[str] = []

    def protect(_db, record, *, refresh=False):
        events.append(f"protect:{record.source_record_id}")
        return IngestionResult(
            source_record_id=record.source_record_id,
            content_text="protected",
            summary=None,
            processing_status=ProcessingStatus.PROTECTED,
            enrichment_mode=None,
            created=True,
            refreshed=refresh,
        )

    def enrich(_db, source_record_id, *, created=False, refreshed=False):
        events.append(f"enrich:{source_record_id}")
        return IngestionResult(
            source_record_id=source_record_id,
            content_text="protected",
            summary="ready",
            processing_status=ProcessingStatus.READY,
            enrichment_mode="test",
            created=created,
            refreshed=refreshed,
        )

    monkeypatch.setattr(service, "protect_canonical_record", protect)
    monkeypatch.setattr(service, "enrich_protected_record", enrich)
    data = (
        HEADER
        + VALID_ROW
        + "INV-1025,customer2@example.com,950,overdue,Owner,2026-08-22\n"
    ).encode()
    try:
        result = service.ingest_structured_csv(db, data)
        assert result.status == "ready"
        assert events[:2] == [
            f"protect:{result.rows[0].source_record_id}",
            f"protect:{result.rows[1].source_record_id}",
        ]
        assert all(item.startswith("enrich:") for item in events[2:])
    finally:
        db.close()
        engine.dispose()


def test_service_persists_protected_rows_and_reversible_amount(monkeypatch):
    engine, db = _database()
    _mock_enrichment(monkeypatch)
    data = (HEADER + VALID_ROW).encode()
    try:
        result = service.ingest_structured_csv(db, data)
        stored = db.scalar(select(TokenizedContent))
        batch = db.scalar(select(StructuredIngestionBatch))
        amount_entry = db.scalar(
            select(TokenVaultEntry).where(TokenVaultEntry.entity_type == "AMOUNT")
        )

        assert result.status == "ready"
        assert result.ready_rows == 1
        assert batch.batch_ref == result.batch_ref
        assert "nur.aisyah@example.com" not in stored.content_text
        assert "RM 4,500" not in stored.content_text
        assert "EMAIL_" in stored.content_text
        assert "AMOUNT_BAND_3_" in stored.content_text
        assert amount_entry is not None
        assert "nur.aisyah@example.com" not in repr(batch.__dict__)
    finally:
        db.close()
        engine.dispose()


def test_same_invoice_refreshes_one_record_and_failed_enrichment_is_retryable(monkeypatch):
    engine, db = _database()
    _mock_enrichment(monkeypatch)
    original = (HEADER + VALID_ROW).encode()
    changed = (HEADER + VALID_ROW.replace("4,500", "4,850")).encode()
    try:
        first = service.ingest_structured_csv(db, original)
        second = service.ingest_structured_csv(db, changed)
        rows = db.scalars(select(TokenizedContent)).all()
        assert first.rows[0].source_record_id == second.rows[0].source_record_id
        assert second.rows[0].ingestion.refreshed
        assert len(rows) == 1

        monkeypatch.setattr(
            ingestion,
            "summarize_protected_text",
            lambda _text: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        failed = service.ingest_structured_csv(db, changed, refresh=True)
        assert failed.status == "failed"
        assert failed.rows[0].ingestion.processing_status is ProcessingStatus.FAILED_ENRICHMENT
        assert db.scalar(select(TokenizedContent)).content_text.startswith("Invoice ID")
    finally:
        db.close()
        engine.dispose()
