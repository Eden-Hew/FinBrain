from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.email_connector import service
from app.models import Base, EmailIngestionReceipt, Tenant, TokenizedContent

TENANT = "00000000-0000-0000-0000-000000000001"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Primary", slug="primary"))
    db.commit()
    return db


def test_reconcile_receipt_routes_sender_before_reply_correlation(monkeypatch):
    db = _session()
    try:
        row = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="email:reply",
            source_system="email",
            record_type="email",
            content_text="From: PERSON_aaaaaaaaaa <EMAIL_0123456789>\nReply",
            processing_status="ready",
        )
        receipt = EmailIngestionReceipt(
            message_ref_hash="receipt-reply",
            source_record_id=row.source_record_id,
            status="ready",
        )
        db.add_all([row, receipt])
        db.commit()
        calls: list[str] = []

        def route(_db, *, receipt, protected_row):
            calls.append("route")
            protected_row.safe_metadata = {"sender_email": "EMAIL_0123456789"}
            receipt.customer_id = 4
            _db.commit()
            return 4

        def correlate(_db, *, receipt, protected_row, reference_hashes):
            calls.append("correlate")
            assert protected_row.safe_metadata["sender_email"] == "EMAIL_0123456789"
            assert reference_hashes == ("reply-ref",)

        monkeypatch.setattr(service, "route_email_sender", route)
        monkeypatch.setattr(service, "correlate_reply", correlate)

        customer_id = service.reconcile_receipt(
            db,
            receipt=receipt,
            reference_hashes=("reply-ref",),
        )

        assert customer_id == 4
        assert calls == ["route", "correlate"]
    finally:
        db.close()


def test_unassigned_ready_receipt_is_retried_without_reingestion(monkeypatch):
    db = _session()
    try:
        row = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="email:previously-ingested",
            source_system="email",
            record_type="email",
            content_text="Protected reply",
            processing_status="ready",
        )
        receipt = EmailIngestionReceipt(
            message_ref_hash="receipt-previously-ingested",
            source_record_id=row.source_record_id,
            status="ready",
        )
        db.add_all([row, receipt])
        db.commit()

        def reconcile(_db, *, receipt, reference_hashes=()):
            receipt.customer_id = 4
            _db.commit()
            return 4

        monkeypatch.setattr(service, "reconcile_receipt", reconcile)

        assert service.reconcile_unassigned_receipts(db, limit=25) == 1
        db.refresh(receipt)
        assert receipt.customer_id == 4
    finally:
        db.close()
