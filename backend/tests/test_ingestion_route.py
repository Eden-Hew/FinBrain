from fastapi import HTTPException

from app.routes import ingestion as ingestion_route
from app.schemas import IngestionRequest, IngestionResult, ProcessingStatus, UserRole
from tests.auth_support import principal


def _request() -> IngestionRequest:
    return IngestionRequest(
        source_record_id="manual:record-1",
        source_system="manual",
        record_type="customer_note",
        text="Customer called about an invoice.",
        metadata={"channel": "manual_entry"},
    )


def test_authenticated_ingestion_route_passes_canonical_record_and_principal(monkeypatch):
    captured = {}

    def fake_ingest(_db, record, *, refresh):
        captured["record"] = record
        captured["refresh"] = refresh
        return IngestionResult(
            source_record_id=record.source_record_id,
            content_text="Protected customer note.",
            summary="A customer requires attention.",
            processing_status=ProcessingStatus.READY,
            enrichment_mode="offline-demo",
            created=True,
            refreshed=False,
        )

    monkeypatch.setattr(ingestion_route, "ingest_canonical_record", fake_ingest)
    response = ingestion_route.ingest(
        _request(), principal(UserRole.FINANCE_OPS), db=object()
    )

    assert captured["record"].source_system == "manual"
    assert not hasattr(captured["record"], "role")
    assert captured["refresh"] is False
    assert response.submitted_as is UserRole.FINANCE_OPS
    assert response.authorization_mode == "supabase-jwt"
    assert response.processing_status is ProcessingStatus.READY


def test_demo_ingestion_route_returns_safe_validation_error(monkeypatch):
    monkeypatch.setattr(
        ingestion_route,
        "ingest_canonical_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("source_record_id must be opaque")
        ),
    )

    try:
        ingestion_route.ingest(
            _request(), principal(UserRole.FINANCE_OPS), db=object()
        )
    except HTTPException as error:
        assert error.status_code == 422
        assert error.detail == "source_record_id must be opaque"
    else:
        raise AssertionError("ingestion validation error was not converted to HTTP 422")
