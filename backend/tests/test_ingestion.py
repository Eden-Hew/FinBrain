from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, TokenizedContent, TokenVaultEntry
from app.schemas import (
    CanonicalIngestionRecord,
    ProcessingStatus,
    ProtectedSummary,
    SummaryPriority,
)
from app.services import ingestion
from app.services.summarization import _validate_summary


def _summary(text: str = "Protected record accepted.") -> ProtectedSummary:
    return ProtectedSummary(
        summary=text,
        category="customer_contact",
        action_required=True,
        priority=SummaryPriority.MEDIUM,
    )


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_unified_ingestion_sends_only_protected_content_to_enrichment(monkeypatch):
    engine, db = _database()
    captured: dict[str, str] = {}

    def summarize(text: str):
        captured["summary_input"] = text
        return _summary(), "test"

    def embed(text: str):
        captured["embedding_input"] = text
        return [1.0, 0.0], "test"

    monkeypatch.setattr(ingestion, "summarize_protected_text", summarize)
    monkeypatch.setattr(ingestion, "embed_text", embed)
    record = CanonicalIngestionRecord(
        source_record_id="whatsapp:message-1",
        source_system="whatsapp",
        record_type="customer_message",
        text="Call 012-345 6789 about the overdue invoice.",
        metadata={"sender_email": "lim.ck@example.com"},
    )

    try:
        result = ingestion.ingest_canonical_record(db, record)
        stored = db.scalar(select(TokenizedContent))
        vault_entries = db.scalars(select(TokenVaultEntry)).all()

        assert result.processing_status is ProcessingStatus.READY
        assert "012-345 6789" not in captured["summary_input"]
        assert "012-345 6789" not in captured["embedding_input"]
        assert "lim.ck@example.com" not in stored.safe_metadata["sender_email"]
        assert "PHONE_" in stored.content_text
        assert "EMAIL_" in stored.safe_metadata["sender_email"]
        assert stored.structured_summary["category"] == "customer_contact"
        assert all(b"012-345 6789" not in entry.encrypted_value for entry in vault_entries)
    finally:
        db.close()
        engine.dispose()


def test_identical_record_is_idempotent(monkeypatch):
    engine, db = _database()
    calls = {"summaries": 0}

    def summarize(_text: str):
        calls["summaries"] += 1
        return _summary(), "test"

    monkeypatch.setattr(ingestion, "summarize_protected_text", summarize)
    monkeypatch.setattr(ingestion, "embed_text", lambda _text: ([1.0], "test"))
    record = CanonicalIngestionRecord(
        source_record_id="email:message-1",
        source_system="email",
        record_type="customer_message",
        text="A protected business update.",
    )

    try:
        first = ingestion.ingest_canonical_record(db, record)
        second = ingestion.ingest_canonical_record(db, record)

        assert first.created
        assert not second.created
        assert not second.refreshed
        assert calls["summaries"] == 1
        assert len(db.scalars(select(TokenizedContent)).all()) == 1
    finally:
        db.close()
        engine.dispose()


def test_changed_record_refreshes_without_duplicate(monkeypatch):
    engine, db = _database()
    monkeypatch.setattr(
        ingestion, "summarize_protected_text", lambda text: (_summary(text), "test")
    )
    monkeypatch.setattr(ingestion, "embed_text", lambda text: ([float(len(text))], "test"))
    original = CanonicalIngestionRecord(
        source_record_id="bank:row-1",
        source_system="bank_csv",
        record_type="transaction",
        text="Payment pending.",
    )
    changed = original.model_copy(update={"text": "Payment completed."})

    try:
        ingestion.ingest_canonical_record(db, original)
        result = ingestion.ingest_canonical_record(db, changed)
        stored = db.scalars(select(TokenizedContent)).all()

        assert result.refreshed
        assert len(stored) == 1
        assert stored[0].content_text == "Payment completed."
    finally:
        db.close()
        engine.dispose()


def test_enrichment_failure_keeps_only_retryable_protected_record(monkeypatch):
    engine, db = _database()
    monkeypatch.setattr(
        ingestion,
        "summarize_protected_text",
        lambda _text: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    raw_phone = "012-345 6789"
    record = CanonicalIngestionRecord(
        source_record_id="document:1",
        source_system="document",
        record_type="note",
        text=f"Call {raw_phone} tomorrow.",
    )

    try:
        result = ingestion.ingest_canonical_record(db, record)
        stored = db.scalar(select(TokenizedContent))

        assert result.processing_status is ProcessingStatus.FAILED_ENRICHMENT
        assert stored.processing_error == "summarization_failed"
        assert stored.embedding is None
        assert stored.summary is None
        assert raw_phone not in stored.content_text
        assert "PHONE_" in stored.content_text
    finally:
        db.close()
        engine.dispose()


def test_summary_validation_rejects_unknown_tokens_and_residual_pii():
    protected = "PERSON_0011223344 has an overdue payment."
    _validate_summary(_summary("PERSON_0011223344 needs attention."), protected)

    try:
        _validate_summary(_summary("PERSON_aabbccddee needs attention."), protected)
    except ValueError as error:
        assert "unknown protected tokens" in str(error)
    else:
        raise AssertionError("unknown summary token was accepted")

    try:
        _validate_summary(_summary("Call 012-345 6789."), protected)
    except ValueError as error:
        assert "recognizable sensitive data" in str(error)
    else:
        raise AssertionError("summary PII was accepted")


def test_source_identifier_cannot_bypass_the_privacy_boundary():
    engine, db = _database()
    record = CanonicalIngestionRecord(
        source_record_id="whatsapp:012-345-6789",
        source_system="whatsapp",
        record_type="customer_message",
        text="A business update.",
    )

    try:
        try:
            ingestion.ingest_canonical_record(db, record)
        except ValueError as error:
            assert "opaque identifier" in str(error)
        else:
            raise AssertionError("PII-bearing source identifier was accepted")
        assert db.scalar(select(TokenizedContent)) is None
    finally:
        db.close()
        engine.dispose()
